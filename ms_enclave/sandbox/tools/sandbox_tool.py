from typing import Any, List, Optional

from ..model import SandboxType
from .base import Tool
from .tool_info import ToolParams


class SandboxTool(Tool):
    """Built-in tool class"""

    _name: Optional[str] = None
    _description: Optional[str] = None
    _parameters: Optional[ToolParams] = None
    _sandbox_types: Optional[List[SandboxType]] = None

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[ToolParams] = None,
        sandbox: Optional[Any] = None,
        sandbox_types: Optional[List[SandboxType]] = None,
        **kwargs,
    ):
        """
        Initialize the tool.

        Note: Once the sandbox is set, it does not change.
        """
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
            **kwargs,
        )
        self._sandbox = sandbox
        self._name = name or self.__class__._name
        self._description = description or self.__class__._description
        self._parameters = parameters or self.__class__._parameters
        self._sandbox_types = sandbox_types if sandbox_types is not None else self.__class__._sandbox_types

    @property
    def required_sandbox_types(self) -> Optional[List[SandboxType]]:
        """Get the list of sandbox types this tool can run in."""
        return list(self._sandbox_types) if self._sandbox_types is not None else None
