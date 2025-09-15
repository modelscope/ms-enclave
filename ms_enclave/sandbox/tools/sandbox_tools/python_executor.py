"""Python code execution tool."""

import os
from typing import TYPE_CHECKING, Any, Dict, Optional

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
        """Execute Python code using IPython in the Docker container."""

        import uuid
        script_basename = f"exec_script_{uuid.uuid4().hex}.py"
        script_path = f"/tmp/{script_basename}"

        if not code.strip():
            return ToolResult(tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No code provided')

        try:
            # Create a temporary Python script
            script_content = self._create_execution_script(code)

            # Write script to container
            await self._write_file_to_container(sandbox_context, script_path, script_content)

            # Execute using IPython
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
        finally:
            # Clean up the script file in the container
            try:
                await sandbox_context.execute_command(f'rm -f {script_path}', timeout=5)
            except Exception:
                pass

    def _create_execution_script(self, code: str) -> str:
        """Create a Python script that captures output and errors."""
        script = f'''
import sys
import io
import traceback
import json
from contextlib import redirect_stdout, redirect_stderr

# Capture stdout and stderr
stdout_capture = io.StringIO()
stderr_capture = io.StringIO()

_execution_result = {{
    "status": "success",
    "output": "",
    "error": None
}}

try:
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        # Execute the user code
        exec("""
{code}
""")

    _execution_result["output"] = stdout_capture.getvalue()
    stderr_content = stderr_capture.getvalue()
    if stderr_content:
        _execution_result["error"] = stderr_content

except Exception as e:
    _execution_result["status"] = "error"
    _execution_result["output"] = stdout_capture.getvalue()
    _execution_result["error"] = f"{{type(e).__name__}}: {{str(e)}}\\n{{traceback.format_exc()}}"

# Print result as JSON for easy parsing
print("=== EXECUTION_RESULT ===")
print(json.dumps(_execution_result, ensure_ascii=False, indent=2))
'''
        return script

    async def _write_file_to_container(self, sandbox_context, file_path: str, content: str) -> None:
        """Write content to a file in the container."""
        import io
        import tarfile

        # Create a tar archive in memory using context managers
        tar_stream = io.BytesIO()
        with tarfile.TarFile(fileobj=tar_stream, mode='w') as tar:
            file_data = content.encode('utf-8')
            tarinfo = tarfile.TarInfo(name=os.path.basename(file_path))
            tarinfo.size = len(file_data)
            tar.addfile(tarinfo, io.BytesIO(file_data))

        # Write to container
        tar_stream.seek(0)
        sandbox_context.container.put_archive(os.path.dirname(file_path), tar_stream.getvalue())
