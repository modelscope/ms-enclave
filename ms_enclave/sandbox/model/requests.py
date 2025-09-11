"""Request data models."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ExecuteCodeRequest(BaseModel):
    """Request model for code execution."""

    code: str = Field(..., description='Code to execute')
    language: str = Field(default='python', description='Programming language')
    timeout: Optional[int] = Field(None, description='Execution timeout in seconds')
    working_dir: Optional[str] = Field(None, description='Working directory')
    env: Dict[str, str] = Field(default_factory=dict, description='Environment variables')
    capture_output: bool = Field(True, description='Whether to capture stdout/stderr')


class ExecuteCommandRequest(BaseModel):
    """Request model for shell command execution."""

    command: Union[str, List[str]] = Field(..., description='Command to execute')
    timeout: Optional[int] = Field(None, description='Execution timeout in seconds')
    working_dir: Optional[str] = Field(None, description='Working directory')
    env: Dict[str, str] = Field(default_factory=dict, description='Environment variables')
    shell: bool = Field(True, description='Execute in shell')


class FileOperationRequest(BaseModel):
    """Base request model for file operations."""

    path: str = Field(..., description='File path')


class ReadFileRequest(FileOperationRequest):
    """Request model for reading files."""

    encoding: Optional[str] = Field('utf-8', description='File encoding')
    binary: bool = Field(False, description='Read as binary')


class WriteFileRequest(FileOperationRequest):
    """Request model for writing files."""

    content: Union[str, bytes] = Field(..., description='File content')
    encoding: Optional[str] = Field('utf-8', description='File encoding')
    binary: bool = Field(False, description='Write as binary')
    create_dirs: bool = Field(True, description='Create parent directories if needed')


class ToolExecutionRequest(BaseModel):
    """Request model for tool execution."""

    sandbox_id: str = Field(..., description='Sandbox identifier')
    tool_name: str = Field(..., description='Name of tool to execute')
    parameters: Dict[str, Any] = Field(default_factory=dict, description='Tool parameters')
    timeout: Optional[int] = Field(None, description='Execution timeout in seconds')
