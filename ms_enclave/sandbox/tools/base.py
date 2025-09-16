"""Base tool interface and factory."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional, Type

from ..model import SandboxType, ToolResult
from .tool_info import ToolParams

if TYPE_CHECKING:
    from ms_enclave.sandbox.boxes import Sandbox


class Tool(ABC):
    """Abstract base class for all tools."""

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[ToolParams] = None,
        enabled: bool = True,
        timeout: Optional[int] = None,
        **kwargs,
    ):
        self._name = name or self.__class__.__name__
        self._description = description
        self._parameters = parameters
        self.enabled = enabled
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> Optional[str]:
        return self._description

    @property
    def parameters(self) -> Optional[ToolParams]:
        return self._parameters

    @property
    def schema(self) -> Dict:
        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': self._description,
                'parameters': self._parameters.model_dump(exclude_none=True) if self._parameters else {},
            },
        }

    @property
    @abstractmethod
    def required_sandbox_type(self) -> Optional[SandboxType]:
        """Get the required sandbox type for this tool."""
        pass

    @abstractmethod
    async def execute(self, sandbox_context: 'Sandbox', **kwargs) -> ToolResult:
        """Execute the tool with given sandbox context and parameters."""
        pass


class ToolFactory:
    """Factory for creating tool instances."""

    _tools: Dict[str, Type[Tool]] = {}

    @classmethod
    def register_tool(cls, tool_name: str, tool_class: Type[Tool]):
        cls._tools[tool_name] = tool_class

    @classmethod
    def create_tool(cls, tool_name: str, **kwargs) -> Tool:
        if tool_name not in cls._tools:
            raise ValueError(f'Tool name {tool_name} is not registered')

        tool_class = cls._tools[tool_name]
        return tool_class(**kwargs)

    @classmethod
    def get_available_tools(cls) -> list[str]:
        return list(cls._tools.keys())


def register_tool(tool_name: str):

    def decorator(tool_class: Type[Tool]):
        ToolFactory.register_tool(tool_name, tool_class)
        return tool_class

    return decorator
