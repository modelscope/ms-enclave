"""File operation tool for reading and writing files."""

import io
import os
import tarfile
from typing import TYPE_CHECKING, Literal, Optional

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox


@register_tool('file_operation')
class FileOperation(SandboxTool):

    _name = 'file_operation'
    _sandbox_type = SandboxType.DOCKER
    _description = 'Perform file operations like read, write, delete, and list files'
    _parameters = ToolParams(
        type='object',
        properties={
            'operation': {
                'type': 'string',
                'description': 'Type of file operation to perform',
                'enum': ['create', 'read', 'write', 'delete', 'list', 'exists']
            },
            'file_path': {
                'type': 'string',
                'description': 'Path to the file or directory'
            },
            'content': {
                'type': 'string',
                'description': 'Content to write to file (only for write operation)'
            },
            'encoding': {
                'type': 'string',
                'description': 'File encoding',
                'default': 'utf-8'
            }
        },
        required=['operation', 'file_path']
    )

    async def execute(
        self,
        sandbox_context: 'Sandbox',
        operation: str,
        file_path: str,
        content: Optional[str] = None,
        encoding: str = 'utf-8'
    ) -> ToolResult:
        """Perform file operations in the Docker container."""

        if not file_path.strip():
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No file path provided'
            )

        try:
            if operation == 'read':
                return await self._read_file(sandbox_context, file_path, encoding)
            elif operation == 'write':
                if content is None:
                    return ToolResult(
                        tool_name=self.name,
                        status=ExecutionStatus.ERROR,
                        output='',
                        error='Content is required for write operation'
                    )
                return await self._write_file(sandbox_context, file_path, content, encoding)
            elif operation == 'delete':
                return await self._delete_file(sandbox_context, file_path)
            elif operation == 'list':
                return await self._list_directory(sandbox_context, file_path)
            elif operation == 'exists':
                return await self._check_exists(sandbox_context, file_path)
            elif operation == 'create':
                if content is None:
                    content = ''
                return await self._write_file(sandbox_context, file_path, content, encoding)
            else:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output='',
                    error=f'Unknown operation: {operation}'
                )

        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Operation failed: {str(e)}'
            )

    async def _read_file(self, sandbox_context: 'Sandbox', file_path: str, encoding: str) -> ToolResult:
        """Read file content from the container."""
        try:
            # Use cat command to read file content
            result = await sandbox_context.execute_command(f'cat "{file_path}"')

            if result.exit_code == 0:
                return ToolResult(tool_name=self.name, status=ExecutionStatus.SUCCESS, output=result.stdout, error=None)
            else:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output='',
                    error=result.stderr or f'Failed to read file: {file_path}'
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Read failed: {str(e)}'
            )

    async def _write_file(self, sandbox_context: 'Sandbox', file_path: str, content: str, encoding: str) -> ToolResult:
        """Write content to a file in the container."""
        try:
            # Create directory if it doesn't exist
            dir_path = os.path.dirname(file_path)
            if dir_path:
                await sandbox_context.execute_command(f'mkdir -p "{dir_path}"')

            # Write file using tar archive (similar to python_executor)
            await self._write_file_to_container(sandbox_context, file_path, content)

            return ToolResult(
                tool_name=self.name,
                status=ExecutionStatus.SUCCESS,
                output=f'File written successfully: {file_path}',
                error=None
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Write failed: {str(e)}'
            )

    async def _delete_file(self, sandbox_context: 'Sandbox', file_path: str) -> ToolResult:
        """Delete a file or directory from the container."""
        try:
            result = await sandbox_context.execute_command(f'rm -rf "{file_path}"')

            if result.exit_code == 0:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.SUCCESS,
                    output=f'Successfully deleted: {file_path}',
                    error=None
                )
            else:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output='',
                    error=result.stderr or f'Failed to delete: {file_path}'
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Delete failed: {str(e)}'
            )

    async def _list_directory(self, sandbox_context: 'Sandbox', dir_path: str) -> ToolResult:
        """List contents of a directory."""
        try:
            result = await sandbox_context.execute_command(f'ls -la "{dir_path}"')

            if result.exit_code == 0:
                return ToolResult(tool_name=self.name, status=ExecutionStatus.SUCCESS, output=result.stdout, error=None)
            else:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output='',
                    error=result.stderr or f'Failed to list directory: {dir_path}'
                )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'List failed: {str(e)}'
            )

    async def _check_exists(self, sandbox_context: 'Sandbox', file_path: str) -> ToolResult:
        """Check if a file or directory exists."""
        try:
            result = await sandbox_context.execute_command(f'test -e "{file_path}"')

            exists = result.exit_code == 0
            return ToolResult(
                tool_name=self.name,
                status=ExecutionStatus.SUCCESS,
                output=f'{"exists" if exists else "does not exist"}',
                error=None
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Exists check failed: {str(e)}'
            )

    async def _write_file_to_container(self, sandbox_context: 'Sandbox', file_path: str, content: str) -> None:
        """Write content to a file in the container using tar archive."""
        # Create a tar archive in memory
        tar_stream = io.BytesIO()
        tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

        # Add file to tar
        file_data = content.encode('utf-8')
        tarinfo = tarfile.TarInfo(name=os.path.basename(file_path))
        tarinfo.size = len(file_data)
        tar.addfile(tarinfo, io.BytesIO(file_data))
        tar.close()

        # Write to container
        tar_stream.seek(0)
        sandbox_context.container.put_archive(os.path.dirname(file_path), tar_stream.getvalue())
