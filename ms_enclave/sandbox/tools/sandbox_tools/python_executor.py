"""Python code execution tool."""

from typing import TYPE_CHECKING, Optional

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox


@register_tool('python_executor')
class PythonExecutor(SandboxTool):

    _name = 'python_executor'
    _sandbox_type = SandboxType.DOCKER
    _description = 'Execute Python code in an isolated environment using IPython'
    _parameters = ToolParams(
        type='object',
        properties={
            'code': {
                'type': 'string',
                'description': 'Python code to execute'
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
        """Execute Python code using python -c command in the Docker container."""

        if not code.strip():
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No code provided')

        try:
            # Execute using python -c command directly
            command = ['python', '-c', code]
            result = await sandbox_context.execute_command(command, timeout=timeout)

            if result.exit_code == 0:
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
