"""Response data models."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from .base import ExecutionStatus, SandboxStatus


class SandboxInfo(BaseModel):
    """Information about a sandbox instance."""

    id: str = Field(..., description='Sandbox identifier')
    status: SandboxStatus = Field(..., description='Current status')
    type: str = Field(..., description="Sandbox type (e.g., 'docker')")
    config: Dict[str, Any] = Field(default_factory=dict, description='Sandbox configuration')
    created_at: datetime = Field(default_factory=datetime.now, description='Creation timestamp')
    updated_at: datetime = Field(default_factory=datetime.now, description='Last update timestamp')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')
    available_tools: Dict[str, Any] = Field(default_factory=dict, description='Available tools')


class ExecutionResult(BaseModel):
    """Base class for execution results."""

    status: ExecutionStatus = Field(..., description='Execution status')
    execution_time: Optional[float] = Field(None, description='Execution time in seconds')
    timestamp: datetime = Field(default_factory=datetime.now, description='Execution timestamp')


class ToolResult(ExecutionResult):
    """Result of tool execution."""

    tool_name: str = Field(..., description='Name of tool executed')
    output: Any = Field(None, description='Tool execution result')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')
    error: Optional[str] = Field(None, description='Error message if failed')


class CommandResult(ExecutionResult):
    """Command execution result."""

    command: Union[str, List[str]] = Field(..., description='Executed command')
    exit_code: int = Field(..., description='Exit code of the command')
    stdout: Optional[str] = Field(None, description='Standard output')
    stderr: Optional[str] = Field(None, description='Standard error output')


class HealthCheckResult(BaseModel):
    """Health check result."""

    healthy: bool = Field(..., description='Health status')
    version: str = Field(..., description='System version')
    uptime: float = Field(..., description='System uptime in seconds')
    active_sandboxes: int = Field(..., description='Number of active sandboxes')
    system_info: Dict[str, Any] = Field(default_factory=dict, description='System information')
