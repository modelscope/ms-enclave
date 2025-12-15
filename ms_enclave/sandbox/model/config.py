"""Configuration data models."""

from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class SandboxManagerConfig(BaseModel):
    """Sandbox manager configuration."""

    base_url: Optional[str] = Field(None, description='Base URL for HTTP manager')
    timeout: Optional[int] = Field(default=None, description='Request timeout in seconds')
    api_key: Optional[str] = Field(None, description='API key for authentication')
    cleanup_interval: Optional[int] = Field(default=None, description='Cleanup interval in seconds')
    pool_size: int = Field(default=0, description='Sandbox pool size (0 = disabled)')
    sandbox_config: Optional[Union['SandboxConfig',
                                   Dict[str, Any]]] = Field(None, description='Default sandbox configuration for pool')

    @field_validator('pool_size')
    def validate_pool_size(cls, v):
        """Validate pool size."""
        if v < 0:
            raise ValueError('Pool size must be non-negative')
        return v

    @field_validator('cleanup_interval', mode='after')
    def validate_cleanup_interval(cls, v):
        """Validate cleanup interval.
        None is allowed (means no cleanup interval). Otherwise, must be positive.
        """
        if v is not None and v <= 0:
            raise ValueError('Cleanup interval must be positive or None')
        return v


class SandboxConfig(BaseModel):
    """Base sandbox configuration."""

    timeout: int = Field(default=30, description='Default timeout in seconds')
    tools_config: Union[List[str], Dict[str, Dict[
        str, Any]]] = Field(default_factory=dict, description='Configuration for tools within the sandbox')
    working_dir: str = Field(default='/sandbox', description='Default working directory')
    env_vars: Dict[str, str] = Field(default_factory=dict, description='Environment variables')
    resource_limits: Dict[str, Any] = Field(default_factory=dict, description='Resource limits')

    @model_validator(mode='after')
    def _normalize_tools_config(self) -> 'SandboxConfig':
        """
        Ensure tools_config is a dict. If provided as a List, convert each list element
        to a key in the dict with an empty dict as its value (e.g., ['tool1', 'tool2'] -> {'tool1': {}, 'tool2': {}}).
        """
        if isinstance(self.tools_config, list):
            self.tools_config = {_tool: {} for _tool in self.tools_config}
        return self


class DockerSandboxConfig(SandboxConfig):
    """Docker-specific sandbox configuration."""

    image: str = Field('python:3.11-slim', description='Docker image name')
    command: Optional[Union[str, List[str]]] = Field(None, description='Container command')
    volumes: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Volume mounts. Format: { host_path: {'bind': container_path, 'mode': 'rw|ro'} }"
    )
    ports: Dict[str, Union[int, str, Tuple[str, int]]] = Field(default_factory=dict, description='Port mappings')
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
