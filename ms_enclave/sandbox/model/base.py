"""Base data models."""

from enum import Enum


class SandboxStatus(str, Enum):
    """Sandbox status enumeration."""

    INITIALIZING = 'initializing'
    RUNNING = 'running'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    ERROR = 'error'
    CLEANUP = 'cleanup'


class SandboxType(str, Enum):
    """Sandbox type enumeration."""
    DOCKER = 'docker'
    DUMMY = 'dummy'


class ToolType(str, Enum):
    """Tool type enumeration."""
    SANDBOX = 'sandbox'
    FUNCTION = 'function'
    EXTERNAL = 'external'


class ExecutionStatus(str, Enum):
    """Execution status enumeration."""

    SUCCESS = 'success'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    CANCELLED = 'cancelled'
