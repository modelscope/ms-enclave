# Copyright (c) Alibaba, Inc. and its affiliates.
"""Modern agent sandbox system.

A modular, extensible sandbox system for safe code execution with Docker isolation,
FastAPI-based client/server architecture, and comprehensive tool support.
"""

from .boxes import DockerSandbox, Sandbox, SandboxFactory
from .manager import HttpSandboxManager, LocalSandboxManager

# Import main components
from .model import (
    DockerSandboxConfig,
    ExecuteCodeRequest,
    ExecuteCommandRequest,
    ExecutionStatus,
    HealthCheckResult,
    ReadFileRequest,
    SandboxConfig,
    SandboxInfo,
    SandboxStatus,
    ToolExecutionRequest,
    ToolResult,
    WriteFileRequest,
)
from .server.server import SandboxServer, create_server
from .tools import PythonExecutor, Tool, ToolFactory
