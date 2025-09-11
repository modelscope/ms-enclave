"""Shell command execution tool."""

from typing import TYPE_CHECKING, Optional

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox


@register_tool('shell_executor')
class ShellExecutor(SandboxTool):

    _name = 'shell_executor'
    _sandbox_type = SandboxType.DOCKER
    _description = 'Execute shell commands in an isolated environment'
    _parameters = ToolParams(
        type='object',
        properties={
            'command': {
                'type': 'string',
                'description': 'Shell command to execute'
            },
            'timeout': {
                'type': 'integer',
                'description': 'Execution timeout in seconds',
                'default': 30
            }
        },
        required=['command']
    )

    async def execute(self, sandbox_context: 'Sandbox', command: str, timeout: Optional[int] = 30) -> ToolResult:
        """Execute shell command in the Docker container."""

        if not command.strip():
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No command provided')

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
