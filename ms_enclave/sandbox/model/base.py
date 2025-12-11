"""Base data models."""

from enum import Enum
from typing import Set


class SandboxStatus(str, Enum):
    """Sandbox status enumeration."""

    INITIALIZING = 'initializing'
    RUNNING = 'running'
    IDLE = 'idle'
    BUSY = 'busy'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    ERROR = 'error'


class SandboxType(str, Enum):
    """Sandbox type enumeration."""
    DOCKER = 'docker'
    DOCKER_NOTEBOOK = 'docker_notebook'
    DUMMY = 'dummy'

    @classmethod
    def get_compatible_types(cls, sandbox_type: 'SandboxType') -> Set['SandboxType']:
        """
        Get all compatible sandbox types for a given sandbox type.

        A sandbox type is compatible with itself and all its "parent" types.
        For example, DOCKER_NOTEBOOK is compatible with both DOCKER_NOTEBOOK and DOCKER.

        Args:
            sandbox_type: The sandbox type to check compatibility for

        Returns:
            Set of compatible sandbox types
        """
        # Define inheritance hierarchy: child -> parents
        # DOCKER_NOTEBOOK inherits from DOCKER (can use DOCKER tools)
        inheritance_map = {
            cls.DOCKER: {cls.DOCKER},
            cls.DOCKER_NOTEBOOK: {cls.DOCKER_NOTEBOOK, cls.DOCKER},
        }

        return inheritance_map.get(sandbox_type, {sandbox_type})

    @classmethod
    def is_compatible(cls, sandbox_type: 'SandboxType', required_type: 'SandboxType') -> bool:
        """
        Check if a sandbox type is compatible with a required type.

        Args:
            sandbox_type: The actual sandbox type
            required_type: The required sandbox type by a tool

        Returns:
            True if sandbox_type can use tools requiring required_type
        """
        compatible_types = cls.get_compatible_types(sandbox_type)
        return required_type in compatible_types


class SandboxManagerType(str, Enum):
    """Sandbox manager type enumeration."""
    LOCAL = 'local'
    HTTP = 'http'


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
