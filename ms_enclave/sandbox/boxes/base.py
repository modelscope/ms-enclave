"""Base sandbox interface and factory."""

import abc
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, Union

import shortuuid as uuid

from ms_enclave.utils import get_logger

from ..model import (
    CommandResult,
    DockerNotebookConfig,
    DockerSandboxConfig,
    SandboxConfig,
    SandboxInfo,
    SandboxStatus,
    SandboxType,
    ToolResult,
)
from ..tools import Tool, ToolFactory

logger = get_logger()


class Sandbox(abc.ABC):
    """Abstract base class for all sandbox implementations."""

    def __init__(self, config: SandboxConfig, sandbox_id: Optional[str] = None):
        """Initialize sandbox.

        Args:
            config: Sandbox configuration
            sandbox_id: Optional sandbox ID (will be generated if not provided)
        """
        self.id = sandbox_id or str(uuid.uuid())
        self.config = config
        self.status = SandboxStatus.INITIALIZING
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.metadata: Dict[str, Any] = {}
        self._tools: Dict[str, Tool] = {}

    @property
    @abc.abstractmethod
    def sandbox_type(self) -> SandboxType:
        """Return the sandbox type identifier."""
        pass

    @abc.abstractmethod
    async def start(self) -> None:
        """Start the sandbox environment."""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the sandbox environment."""
        pass

    @abc.abstractmethod
    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        pass

    async def initialize_tools(self) -> None:
        """Initialize sandbox tools."""
        for tool_name, config in self.config.tools_config.items():
            try:
                tool = ToolFactory.create_tool(tool_name, **config)
                if tool.enabled:
                    # Check if tool is compatible with this sandbox
                    if (tool.required_sandbox_type is None or tool.required_sandbox_type == self.sandbox_type):
                        self._tools[tool_name] = tool
                    else:
                        logger.warning(
                            f'Tool {tool_name} requires {tool.required_sandbox_type} but sandbox is {self.sandbox_type}'
                        )
            except Exception as e:
                logger.error(f'Failed to initialize tool {tool_name}: {e}')

    def get_available_tools(self) -> Dict[str, Any]:
        """Get list of available tools."""
        return {tool.name: tool.schema for tool in self._tools.values() if tool.enabled}

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get tool instance by type.

        Args:
            tool_name: Tool name

        Returns:
            Tool instance or None if not available
        """
        return self._tools.get(tool_name)

    def add_tool(self, tool: Tool) -> None:
        """Add a tool to the sandbox.

        Args:
            tool: Tool instance to add
        """
        if tool.name in self._tools:
            logger.warning(f'Tool {tool.name} is already added to the sandbox')
            return
        if tool.enabled:
            if (tool.required_sandbox_type is None or tool.required_sandbox_type == self.sandbox_type):
                self._tools[tool.name] = tool
            else:
                logger.warning(
                    f'Tool {tool.name} requires {tool.required_sandbox_type} but sandbox is {self.sandbox_type}'
                )
        else:
            logger.warning(f'Tool {tool.name} is not enabled and cannot be added')

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute a tool with given parameters.

        Args:
            tool_name: Tool name
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool is not found or not enabled
            TimeoutError: If tool execution exceeds timeout
            Exception: For other execution errors
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f'Tool {tool_name} is not available')
        if not tool.enabled:
            raise ValueError(f'Tool {tool_name} is not enabled')

        result = await tool.execute(sandbox_context=self, **parameters)
        return result

    async def execute_command(self, command: Union[str, List[str]], timeout: Optional[int] = None) -> CommandResult:
        """Execute a command in the sandbox environment.

        Args:
            command: Command to execute
            timeout: Optional execution timeout in seconds
        """
        raise NotImplementedError('execute_command must be implemented by subclasses')

    @abc.abstractmethod
    async def get_execution_context(self) -> Any:
        """Get the execution context for tools (e.g., container, process, etc.)."""
        pass

    def update_status(self, status: SandboxStatus) -> None:
        """Update sandbox status.

        Args:
            status: New status
        """
        self.status = status
        self.updated_at = datetime.now()

    def get_info(self) -> SandboxInfo:
        """Get sandbox information.

        Returns:
            Sandbox information
        """
        return SandboxInfo(
            id=self.id,
            status=self.status,
            type=self.sandbox_type,
            config=self.config.model_dump(exclude_none=True),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata,
            available_tools=self.get_available_tools()
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


class SandboxFactory:
    """Factory for creating sandbox instances."""

    _sandboxes: Dict[SandboxType, Type[Sandbox]] = {}

    @classmethod
    def register_sandbox(cls, sandbox_type: SandboxType, sandbox_class: Type[Sandbox]):
        """Register a sandbox class.

        Args:
            sandbox_type: Sandbox type identifier
            sandbox_class: Sandbox class
        """
        cls._sandboxes[sandbox_type] = sandbox_class

    @classmethod
    def create_sandbox(
        cls,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None
    ) -> Sandbox:
        """Create a sandbox instance.

        Args:
            sandbox_type: Sandbox type
            config: Sandbox configuration
            sandbox_id: Optional sandbox ID

        Returns:
            Sandbox instance

        Raises:
            ValueError: If sandbox type is not registered
        """
        if sandbox_type not in cls._sandboxes:
            raise ValueError(f'Sandbox type {sandbox_type} is not registered')

        # Parse config based on sandbox type
        if not config:
            if sandbox_type == SandboxType.DOCKER:
                config = DockerSandboxConfig()
            elif sandbox_type == SandboxType.DOCKER_NOTEBOOK:
                config = DockerNotebookConfig()
            else:
                config = SandboxConfig()
        elif isinstance(config, dict):
            if sandbox_type == SandboxType.DOCKER:
                config = DockerSandboxConfig(**config)
            elif sandbox_type == SandboxType.DOCKER_NOTEBOOK:
                config = DockerNotebookConfig(**config)
            else:
                config = SandboxConfig(**config)

        sandbox_class = cls._sandboxes[sandbox_type]
        return sandbox_class(config, sandbox_id)

    @classmethod
    def get_available_types(cls) -> List[SandboxType]:
        """Get list of available sandbox types.

        Returns:
            List of available sandbox types
        """
        return list(cls._sandboxes.keys())


def register_sandbox(sandbox_type: SandboxType):
    """Decorator for registering sandboxes.

    Args:
        sandbox_type: Sandbox type identifier
    """

    def decorator(sandbox_class: Type[Sandbox]):
        SandboxFactory.register_sandbox(sandbox_type, sandbox_class)
        return sandbox_class

    return decorator
