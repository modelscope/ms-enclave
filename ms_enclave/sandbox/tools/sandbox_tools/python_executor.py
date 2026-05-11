"""Python code execution tool."""

import os
import uuid
from typing import TYPE_CHECKING, Optional

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import DockerSandbox, VolcengineSandbox


@register_tool('python_executor')
class PythonExecutor(SandboxTool):

    _name = 'python_executor'
    _sandbox_types = [SandboxType.DOCKER, SandboxType.VOLCENGINE]
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

    async def execute(self, sandbox_context: 'DockerSandbox', code: str, timeout: Optional[int] = 30) -> ToolResult:
        """Execute Python code by writing to a temporary file and executing it."""

        if not code.strip():
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No code provided')

        # Stateless remote sandbox (e.g. VolcEngine/SandboxFusion): just POST /run_code.
        sbx_type = getattr(sandbox_context, 'sandbox_type', None)
        if sbx_type == SandboxType.VOLCENGINE:
            try:
                volcengine: 'VolcengineSandbox' = sandbox_context  # type: ignore[assignment]
                resp = await volcengine.run_code(code, language='python', timeout=timeout)
                return volcengine.build_tool_result(self.name, resp)
            except Exception as e:
                return ToolResult(
                    tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Execution failed: {str(e)}'
                )

        script_basename = f'exec_script_{uuid.uuid4().hex}.py'
        script_path = f'/tmp/{script_basename}'

        try:

            # Write script to container to avoid long code errors
            await self._write_file_to_container(sandbox_context, script_path, code)

            # Execute using python
            command = f'python {script_path}'
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

    async def _write_file_to_container(self, sandbox_context: 'DockerSandbox', file_path: str, content: str) -> None:
        """Write content to a file in the container."""
        import io
        import tarfile

        # Create a tar archive in memory using context managers
        with io.BytesIO() as tar_stream:
            with tarfile.TarFile(fileobj=tar_stream, mode='w') as tar:
                file_data = content.encode('utf-8')
                tarinfo = tarfile.TarInfo(name=os.path.basename(file_path))
                tarinfo.size = len(file_data)
                tar.addfile(tarinfo, io.BytesIO(file_data))

                # Reset stream position and put archive into container
                tar_stream.seek(0)
                sandbox_context.container.put_archive(os.path.dirname(file_path), tar_stream.getvalue())
