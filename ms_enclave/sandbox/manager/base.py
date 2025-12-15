"""Base sandbox manager interface."""

import asyncio
from abc import ABC, abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional, Union

from ..model import (
    SandboxConfig,
    SandboxInfo,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxStatus,
    SandboxType,
    ToolResult,
)

if TYPE_CHECKING:
    from ..boxes import Sandbox


class SandboxManager(ABC):
    """Abstract base class for sandbox managers."""

    def __init__(self, config: Optional[SandboxManagerConfig] = None, **kwargs):
        """Initialize the sandbox manager.

        Args:
            config: Sandbox manager configuration
        """
        self.config = config or SandboxManagerConfig()
        self._running = False
        self._sandboxes: Dict[str, 'Sandbox'] = {}
        self._sandbox_pool: Deque[str] = deque()
        self._pool_lock = asyncio.Lock()
        self._pool_initialized = False

    @abstractmethod
    async def start(self) -> None:
        """Start the sandbox manager."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the sandbox manager."""
        pass

    @abstractmethod
    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None
    ) -> str:
        """Create a new sandbox.

        Args:
            sandbox_type: Type of sandbox to create
            config: Sandbox configuration
            sandbox_id: Optional sandbox ID

        Returns:
            Sandbox ID

        Raises:
            ValueError: If sandbox type is not supported
            RuntimeError: If sandbox creation fails
        """
        pass

    @abstractmethod
    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Get sandbox information.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            Sandbox information or None if not found
        """
        pass

    @abstractmethod
    async def list_sandboxes(self, status_filter: Optional[SandboxStatus] = None) -> List[SandboxInfo]:
        """List all sandboxes.

        Args:
            status_filter: Optional status filter

        Returns:
            List of sandbox information
        """
        pass

    @abstractmethod
    async def stop_sandbox(self, sandbox_id: str) -> bool:
        """Stop a sandbox.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if stopped successfully, False if not found
        """
        pass

    @abstractmethod
    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Delete a sandbox.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if deleted successfully, False if not found
        """
        pass

    @abstractmethod
    async def execute_tool(self, sandbox_id: str, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute tool in sandbox.

        Args:
            sandbox_id: Sandbox ID
            tool_name: Tool name to execute
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            ValueError: If sandbox or tool not found
        """
        pass

    @abstractmethod
    async def get_sandbox_tools(self, sandbox_id: str) -> Dict[str, Any]:
        """Get available tools for a sandbox.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            Dictionary of available tool types, e.g., {"tool_name": tool_schema}

        Raises:
            ValueError: If sandbox not found
        """
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics.

        Returns:
            Statistics dictionary
        """
        pass

    @abstractmethod
    async def cleanup_all_sandboxes(self) -> None:
        """Clean up all sandboxes."""
        pass

    @abstractmethod
    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict]] = None
    ) -> List[str]:
        """Initialize sandbox pool.

        Args:
            pool_size: Number of sandboxes in pool (uses config if not provided)
            sandbox_type: Type of sandbox to create
            config: Sandbox configuration (uses config.sandbox_config if not provided)

        Returns:
            List of created sandbox IDs
        """
        pass

    @abstractmethod
    async def execute_tool_in_pool(
        self, tool_name: str, parameters: Dict[str, Any], timeout: Optional[float] = None
    ) -> ToolResult:
        """Execute tool using an available sandbox from the pool.

        Uses FIFO queue to get an idle sandbox, marks it as busy during execution,
        then returns it to the pool as idle.

        Args:
            tool_name: Tool name to execute
            parameters: Tool parameters
            timeout: Optional timeout for waiting for available sandbox

        Returns:
            Tool execution result

        Raises:
            ValueError: If pool is empty or no sandbox available
            TimeoutError: If timeout waiting for available sandbox
        """
        pass

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


class SandboxManagerFactory:
    """Factory for creating sandbox managers."""

    _registry: Dict[SandboxManagerType, type] = {}

    @classmethod
    def register(cls, manager_type: SandboxManagerType, manager_class: type) -> None:
        """Register a sandbox manager class.

        Args:
            manager_type: Manager type to register
            manager_class: Manager class to register
        """
        cls._registry[manager_type] = manager_class

    @classmethod
    def create_manager(
        cls,
        manager_type: Optional[SandboxManagerType] = None,
        config: Optional[SandboxManagerConfig] = None,
        **kwargs
    ) -> SandboxManager:
        """Create a sandbox manager instance.

        Args:
            manager_type: Type of manager to create
            config: Manager configuration
            **kwargs: Additional manager-specific parameters

        Returns:
            Sandbox manager instance

        Raises:
            ValueError: If manager type is not registered
        """
        if not manager_type:
            api_url = config.base_url if config else kwargs.get('base_url')
            if api_url:
                manager_type = SandboxManagerType.HTTP
            else:
                manager_type = SandboxManagerType.LOCAL

        if manager_type not in cls._registry:
            raise ValueError(
                f"Sandbox manager type '{manager_type}' not registered. "
                f'Available types: {list(cls._registry.keys())}'
            )

        manager_class = cls._registry[manager_type]
        return manager_class(config=config, **kwargs)

    @classmethod
    def get_registered_types(cls) -> List[SandboxManagerType]:
        """Get list of registered manager types.

        Returns:
            List of registered manager types
        """
        return list(cls._registry.keys())


def register_manager(manager_type: SandboxManagerType):
    """Decorator to register a sandbox manager class.

    Args:
        manager_type: Manager type to register

    Returns:
        Decorator function
    """

    def decorator(manager_class: type) -> type:
        SandboxManagerFactory.register(manager_type, manager_class)
        return manager_class

    return decorator
