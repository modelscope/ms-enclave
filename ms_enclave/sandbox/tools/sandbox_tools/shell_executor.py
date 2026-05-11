"""Shell command execution tool."""

from typing import TYPE_CHECKING, List, Optional, Union

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox, VolcengineSandbox


@register_tool('shell_executor')
class ShellExecutor(SandboxTool):

    _name = 'shell_executor'
    _sandbox_types = [SandboxType.DOCKER, SandboxType.VOLCENGINE]
    _description = 'Execute shell commands in an isolated environment'
    _parameters = ToolParams(
        type='object',
        properties={
            'command': {
                'anyOf': [{
                    'type': 'string',
                    'description': 'Shell command to execute'
                }, {
                    'type': 'array',
                    'items': {
                        'type': 'string'
                    },
                    'description': 'List of shell command arguments to execute'
                }]
            },
            'timeout': {
                'type': 'integer',
                'description': 'Execution timeout in seconds',
                'default': 30
            }
        },
        required=['command']
    )

    async def execute(
        self, sandbox_context: 'Sandbox', command: Union[str, List[str]], timeout: Optional[int] = 30
    ) -> ToolResult:
        """Execute shell command in the Docker container."""

        if not command or (isinstance(command, str) and not command.strip()):
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No command provided')

        # Stateless remote sandbox: route through /run_code with bash language.
        sbx_type = getattr(sandbox_context, 'sandbox_type', None)
        if sbx_type == SandboxType.VOLCENGINE:
            try:
                volcengine: 'VolcengineSandbox' = sandbox_context  # type: ignore[assignment]
                cmd_str = command if isinstance(command, str) else ' '.join(command)
                resp = await volcengine.run_code(cmd_str, language='bash', timeout=timeout)
                return volcengine.build_tool_result(self.name, resp)
            except Exception as e:
                return ToolResult(
                    tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Execution failed: {str(e)}'
                )

        try:
            result = await sandbox_context.execute_command(command, timeout=timeout)

            if result.exit_code == 0:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.SUCCESS,
                    output=result.stdout,
                    error=result.stderr if result.stderr else None
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output=result.stdout,
                    error=result.stderr if result.stderr else f'Command failed with exit code {result.exit_code}'
                )

        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Execution failed: {str(e)}'
            )
