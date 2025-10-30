"""File operation tool for reading and writing files."""

import io
import os
import tarfile
import uuid
from typing import TYPE_CHECKING, Literal, Optional

from ms_enclave.sandbox.model import ExecutionStatus, SandboxType, ToolResult
from ms_enclave.sandbox.tools.base import register_tool
from ms_enclave.sandbox.tools.sandbox_tool import SandboxTool
from ms_enclave.sandbox.tools.tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox


@register_tool('file_operation')
class FileOperation(SandboxTool):
    """Tool for performing file operations within Docker containers.

    Supports read, write, create, delete, list, and exists operations.
    Uses temporary files and copy strategy to avoid permission issues
    with mounted directories.
    """

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
        """Perform file operations in the Docker container.

        Args:
            sandbox_context: The sandbox instance to execute operations in
            operation: Type of operation (read, write, create, delete, list, exists)
            file_path: Path to the file or directory
            content: Content to write (required for write/create operations)
            encoding: File encoding for read/write operations

        Returns:
            ToolResult with operation status and output/error information
        """

        # Validate file path is provided and not empty
        if not file_path.strip():
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error='No file path provided'
            )

        try:
            # Route to appropriate operation handler
            if operation == 'read':
                return await self._read_file(sandbox_context, file_path, encoding)
            elif operation == 'write':
                # Write operation requires content parameter
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
                # Create operation with empty content if none provided
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
            # Catch-all error handler for unexpected exceptions
            return ToolResult(
                tool_name=self.name, status=ExecutionStatus.ERROR, output='', error=f'Operation failed: {str(e)}'
            )

    async def _read_file(self, sandbox_context: 'Sandbox', file_path: str, encoding: str) -> ToolResult:
        """Read file content from the container using cat command.

        Args:
            sandbox_context: Sandbox instance
            file_path: Path to file to read
            encoding: File encoding (currently not used by cat command)

        Returns:
            ToolResult with file content or error message
        """
        try:
            # Use cat command to read file content - handles most file types well
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
        """Write content to a file in the container using temp file strategy.

        This method uses a two-step process to avoid permission issues:
        1. Write content to a temporary file in /tmp (always writable)
        2. Copy the temp file to the target location using cp command
        3. Clean up the temporary file

        Args:
            sandbox_context: Sandbox instance
            file_path: Target file path to write to
            content: Content to write to file
            encoding: File encoding for content

        Returns:
            ToolResult indicating success or failure
        """
        try:
            # Create target directory structure if it doesn't exist
            dir_path = os.path.dirname(file_path)
            if dir_path:
                await sandbox_context.execute_command(f'mkdir -p "{dir_path}"')

            # Generate unique temporary file name to avoid conflicts
            temp_file = f'/tmp/file_op_{uuid.uuid4().hex}'

            # Step 1: Write content to temporary location using tar archive
            await self._write_file_to_container(sandbox_context, temp_file, content, encoding)

            # Step 2: Copy from temp to target location using cp command
            # This handles permission issues better than direct tar extraction
            copy_result = await sandbox_context.execute_command(f'cp "{temp_file}" "{file_path}"')

            # Step 3: Clean up temporary file regardless of copy result
            await sandbox_context.execute_command(f'rm -f "{temp_file}"')

            # Check if copy operation succeeded
            if copy_result.exit_code != 0:
                return ToolResult(
                    tool_name=self.name,
                    status=ExecutionStatus.ERROR,
                    output='',
                    error=f'Failed to copy file to target location: {copy_result.stderr or "Unknown error"}'
                )

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
        """Delete a file or directory from the container.

        Uses 'rm -rf' to handle both files and directories recursively.

        Args:
            sandbox_context: Sandbox instance
            file_path: Path to file or directory to delete

        Returns:
            ToolResult indicating success or failure
        """
        try:
            # Use rm -rf to handle both files and directories
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
        """List contents of a directory with detailed information.

        Uses 'ls -la' to show permissions, ownership, size, and timestamps.

        Args:
            sandbox_context: Sandbox instance
            dir_path: Path to directory to list

        Returns:
            ToolResult with directory listing or error message
        """
        try:
            # Use ls -la for detailed directory listing
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
        """Check if a file or directory exists.

        Uses 'test -e' command which returns exit code 0 if path exists.

        Args:
            sandbox_context: Sandbox instance
            file_path: Path to check for existence

        Returns:
            ToolResult with existence status message
        """
        try:
            # Use test -e to check existence (works for files and directories)
            result = await sandbox_context.execute_command(f'test -e "{file_path}"')

            # test command returns 0 if path exists, non-zero otherwise
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

    async def _write_file_to_container(
        self, sandbox_context: 'Sandbox', file_path: str, content: str, encoding: str
    ) -> None:
        """Write content to a file in the container using tar archive method.

        This is a low-level method that creates a tar archive containing the file
        and extracts it to the container. Used internally by _write_file.

        Args:
            sandbox_context: Sandbox instance with container access
            file_path: Target file path in container
            content: File content as string
            encoding: Text encoding for content conversion

        Raises:
            Exception: If tar creation or container extraction fails
        """
        # Create a tar archive in memory to transfer file content
        tar_stream = io.BytesIO()
        tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

        # Encode content using specified encoding and create tar entry
        file_data = content.encode(encoding)
        tarinfo = tarfile.TarInfo(name=os.path.basename(file_path))
        tarinfo.size = len(file_data)
        tar.addfile(tarinfo, io.BytesIO(file_data))
        tar.close()

        # Extract tar archive to container filesystem
        # Note: This writes to the directory containing the target file
        tar_stream.seek(0)
        sandbox_context.container.put_archive(os.path.dirname(file_path) or '/', tar_stream.getvalue())
