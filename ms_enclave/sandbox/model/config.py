"""Configuration data models."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SandboxConfig(BaseModel):
    """Base sandbox configuration."""

    timeout: int = Field(default=30, description='Default timeout in seconds')
    tools_config: Dict[str, Dict[
        str, Any]] = Field(default_factory=dict, description='Configuration for tools within the sandbox')
    working_dir: str = Field(default='/sandbox', description='Default working directory')
    env_vars: Dict[str, str] = Field(default_factory=dict, description='Environment variables')
    resource_limits: Dict[str, Any] = Field(default_factory=dict, description='Resource limits')


class DockerSandboxConfig(SandboxConfig):
    """Docker-specific sandbox configuration."""

    image: str = Field('python:3.11-slim', description='Docker image name')
    command: Optional[Union[str, List[str]]] = Field(None, description='Container command')
    volumes: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Volume mounts. Format: { host_path: {'bind': container_path, 'mode': 'rw|ro'} }"
    )
    ports: Dict[str, str] = Field(default_factory=dict, description='Port mappings')
    network: Optional[str] = Field('bridge', description='Network name')
    memory_limit: str = Field(default='1g', description='Memory limit')
    cpu_limit: float = Field(default=1.0, description='CPU limit')
    network_enabled: bool = Field(default=True, description='Enable network access')
    privileged: bool = Field(default=False, description='Run in privileged mode')
    remove_on_exit: bool = Field(default=True, description='Remove container on exit')

    @field_validator('memory_limit')
    def validate_memory_limit(cls, v):
        """Validate memory limit format."""
        if not isinstance(v, str):
            raise ValueError('Memory limit must be a string')
        # Basic validation for memory format (e.g., '512m', '1g', '2G')
        import re
        if not re.match(r'^\d+[kmgKMG]?$', v):
            raise ValueError('Invalid memory limit format')
        return v

    @field_validator('cpu_limit')
    def validate_cpu_limit(cls, v):
        """Validate CPU limit."""
        if v <= 0:
            raise ValueError('CPU limit must be positive')
        return v


class DockerNotebookConfig(DockerSandboxConfig):
    """Docker Notebook-specific sandbox configuration."""

    image: str = Field('jupyter-kernel-gateway', description='Docker image name for Jupyter Notebook')
    host: str = Field('127.0.0.1', description='Host for Jupyter Notebook')
    port: int = Field(8888, description='Port for Jupyter Notebook')
    token: Optional[str] = Field(None, description='Token for Jupyter Notebook access')


class ToolConfig(BaseModel):
    """Tool configuration."""

    enabled: bool = Field(default=True, description='Whether tool is enabled')
    timeout: int = Field(default=30, description='Tool execution timeout')
    parameters: Dict[str, Any] = Field(default_factory=dict, description='Tool parameters')
    restrictions: Dict[str, Any] = Field(default_factory=dict, description='Tool restrictions')


class PythonExecutorConfig(ToolConfig):
    """Python executor configuration."""

    python_path: str = Field(default='python3', description='Python executable path')
    allowed_modules: Optional[List[str]] = Field(None, description='Allowed modules (None = all)')
    blocked_modules: List[str] = Field(default_factory=list, description='Blocked modules')
    max_output_size: int = Field(default=1024 * 1024, description='Maximum output size in bytes')


class ShellExecutorConfig(ToolConfig):
    """Shell executor configuration."""

    shell_path: str = Field(default='/bin/bash', description='Shell executable path')
    allowed_commands: Optional[List[str]] = Field(None, description='Allowed commands (None = all)')
    blocked_commands: List[str] = Field(default_factory=list, description='Blocked commands')
    max_output_size: int = Field(default=1024 * 1024, description='Maximum output size in bytes')


class FileOperationConfig(ToolConfig):
    """File operation configuration."""

    allowed_paths: Optional[List[str]] = Field(None, description='Allowed paths (None = all)')
    blocked_paths: List[str] = Field(default_factory=list, description='Blocked paths')
    max_file_size: int = Field(default=10 * 1024 * 1024, description='Maximum file size in bytes')
    allowed_extensions: Optional[List[str]] = Field(None, description='Allowed file extensions')
