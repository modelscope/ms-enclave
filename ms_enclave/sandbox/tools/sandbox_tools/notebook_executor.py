"""Notebook code execution tool for Jupyter kernels."""

import json
import time
import uuid
from typing import TYPE_CHECKING, Optional

from ms_enclave.sandbox.model import CommandResult, ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams
from ms_enclave.utils import get_logger

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox

logger = get_logger()


@register_tool('notebook_executor')
class NotebookExecutor(SandboxTool):

    _name = 'notebook_executor'
    _sandbox_types = [SandboxType.DOCKER_NOTEBOOK]
    _description = 'Execute Python code in a Jupyter kernel environment'
    _parameters = ToolParams(
        type='object',
        properties={
            'code': {
                'type': 'string',
                'description': 'Python code to execute in the notebook kernel'
            },
            'timeout': {
                'type': 'integer',
                'description': 'Execution timeout in seconds',
                'default': 30
            }
        },
        required=['code']
    )

    async def execute(self, sandbox_context: 'Sandbox', code: str, timeout: Optional[int] = 30) -> ToolResult:
        """Execute Python code in the Jupyter kernel."""

        if not code.strip():
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No code provided')

        try:
            # Execute code using the sandbox's Jupyter kernel
            result = await self._execute_in_kernel(sandbox_context, code, timeout)

            if result.status == ExecutionStatus.TIMEOUT:
                status = ExecutionStatus.TIMEOUT
            elif result.exit_code == 0:
                status = ExecutionStatus.SUCCESS
            else:
                status = ExecutionStatus.ERROR

            return ToolResult(
                tool_name=self.name,
                status=status,
                output=result.stdout,
                error=result.stderr if result.stderr else None
            )

        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Execution failed: {str(e)}'
            )

    async def _execute_in_kernel(self, sandbox_context: 'Sandbox', code: str, timeout: Optional[int]):
        """Execute code in the Jupyter kernel via websocket."""

        # Check if sandbox has the required Jupyter components
        if not hasattr(sandbox_context, 'ws') or not hasattr(sandbox_context, 'kernel_id'):
            raise RuntimeError('Sandbox does not have Jupyter kernel setup')

        if not sandbox_context.ws or not sandbox_context.kernel_id:
            raise RuntimeError('Jupyter kernel is not ready')

        # Send execute request
        msg_id = self._send_execute_request(sandbox_context, code)

        outputs = []
        result = None
        error_occurred = False
        timed_out = False
        error_msg = ''
        actual_timeout = timeout or 30
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed >= actual_timeout:
                error_occurred = True
                timed_out = True
                error_msg = f'Execution timed out after {actual_timeout} seconds'
                logger.error(error_msg)
                await self._interrupt_kernel(sandbox_context)
                self._drain_execution_messages(sandbox_context, msg_id)
                break

            try:
                # Set a short timeout for recv to allow periodic timeout check
                sandbox_context.ws.settimeout(min(1, actual_timeout - elapsed))
                msg = json.loads(sandbox_context.ws.recv())
                parent_msg_id = msg.get('parent_header', {}).get('msg_id')

                # Skip unrelated messages
                if parent_msg_id != msg_id:
                    continue

                msg_type = msg.get('msg_type') or msg.get('header', {}).get('msg_type', '')
                msg_content = msg.get('content', {})

                if msg_type == 'stream':
                    outputs.append(msg_content['text'])
                elif msg_type == 'execute_result':
                    result = msg_content['data'].get('text/plain', '')
                elif msg_type == 'error':
                    error_occurred = True
                    error_msg = '\n'.join(msg_content.get('traceback', []))
                    outputs.append(error_msg)
                elif msg_type == 'status' and msg_content.get('execution_state') == 'idle':
                    break

            except Exception as e:
                if type(e).__name__ == 'WebSocketTimeoutException':
                    continue
                logger.error(f'Error receiving message: {e}')
                error_occurred = True
                error_msg = str(e)
                break

        output_text = ''.join(outputs)
        if result:
            output_text += f'\nResult: {result}'
        if error_msg and error_msg not in output_text:
            output_text += f'\n{error_msg}'

        return CommandResult(
            status=ExecutionStatus.TIMEOUT if timed_out else
            (ExecutionStatus.SUCCESS if not error_occurred else ExecutionStatus.ERROR),
            command=code,
            exit_code=1 if error_occurred else 0,
            stdout=output_text if not error_occurred else '',
            stderr=output_text if error_occurred else ''
        )

    async def _interrupt_kernel(self, sandbox_context: 'Sandbox') -> None:
        if not getattr(sandbox_context, 'base_url', None) or not getattr(sandbox_context, 'kernel_id', None):
            return

        def _post_interrupt():
            import requests
            url = f'{sandbox_context.base_url}/api/kernels/{sandbox_context.kernel_id}/interrupt'
            return requests.post(url, timeout=5)

        try:
            import asyncio
            response = await asyncio.to_thread(_post_interrupt)
            if response.status_code not in (200, 204):
                logger.warning(f'Kernel interrupt returned HTTP {response.status_code}: {response.text}')
        except Exception as e:
            logger.warning(f'Failed to interrupt notebook kernel after timeout: {e}')

    def _drain_execution_messages(self, sandbox_context: 'Sandbox', msg_id: str, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                remaining = max(0.1, min(0.5, deadline - time.time()))
                sandbox_context.ws.settimeout(remaining)
                msg = json.loads(sandbox_context.ws.recv())
            except Exception as e:
                if type(e).__name__ == 'WebSocketTimeoutException':
                    continue
                logger.debug(f'Error draining notebook timeout messages: {e}')
                return

            if msg.get('parent_header', {}).get('msg_id') != msg_id:
                continue

            msg_type = msg.get('msg_type') or msg.get('header', {}).get('msg_type', '')
            msg_content = msg.get('content', {})
            if msg_type == 'status' and msg_content.get('execution_state') == 'idle':
                return

    def _send_execute_request(self, sandbox_context: 'Sandbox', code: str) -> str:
        """Send code execution request to kernel."""
        # Generate a unique message ID
        msg_id = str(uuid.uuid4())

        # Create execute request
        execute_request = {
            'header': {
                'msg_id': msg_id,
                'username': 'anonymous',
                'session': str(uuid.uuid4()),
                'msg_type': 'execute_request',
                'version': '5.0',
            },
            'parent_header': {},
            'metadata': {},
            'content': {
                'code': code,
                'silent': False,
                'store_history': True,
                'user_expressions': {},
                'allow_stdin': False,
            },
        }

        sandbox_context.ws.send(json.dumps(execute_request))
        return msg_id
