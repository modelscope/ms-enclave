# Core Concepts

ms-enclave uses a modular, layered architecture decoupling runtime management, tool execution, and lifecycle maintenance. Understanding the following concepts and their relationships helps you build efficient Agent systems.

## Architecture Overview

Relationship between core components:

```ascii
+------------------+           +----------------------+
|   User / Client  | --------> |    SandboxManager    |
+------------------+           | (Local / HTTP Proxy) |
                              +----------+-----------+
                                         |
                                         | 1. Manage
                                         |
                                         v
+----------------------+       +----------------------+
|    SandboxFactory    | ----> |       Sandbox        | <---+
+----------------------+  2.   | (Docker / Notebook)  |     |
                        Create+----------+-----------+     |
                                         |                 | 4.
                                         | 3. Run          | Execute
                                         v                 |
                              +----------------------+     |
                              |    Runtime Envrion   |     |
                              |  (Container / Kernel)|     |
                              +----------------------+     |
                                         |                 |
+----------------------+       +----------+-----------+     |
|      ToolFactory     | ----> |         Tool         | ----+
+----------------------+  2.   | (Python/Shell/File)  |
                        Create+----------------------+
```

## 1. Sandbox System

A sandbox is an isolated environment for secure code execution.

### Sandbox (base class)
`Sandbox` is the central ABC defining standard behaviors.

- Purpose: Encapsulates runtime details (e.g., Docker API) and provides unified interfaces: `start`, `stop`, `execute_command`.
- Lifecycle states:
  - `CREATED`, `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `ERROR`.

### SandboxFactory

- Purpose: Factory pattern that creates sandbox instances by `SandboxType`.
- Extensibility: Register new implementations via `@register_sandbox` without modifying the factory itself.

### Implementations & Configs

- DockerSandbox (`docker`):
  - Docker-based sandbox with filesystem and network isolation.
  - Key config (`DockerSandboxConfig`): `image`, `cpu_limit`, `memory_limit`, `auto_remove`, `volumes`.
- DockerNotebook (`docker_notebook`):
  - Extends DockerSandbox with Jupyter Kernel Gateway for interactive Python via HTTP/WebSocket.
  - Inherits Docker config and adds kernel port settings.

## 2. Tool System

Tools are the capability surface exposed to the LLM for interacting with the sandbox.

### Tool (base class)

- Purpose: Implements concrete operations via `execute(sandbox_context, **kwargs)`.
- Schema: `schema` follows OpenAI Function Calling style for discoverability.

### ToolFactory

- Purpose: Central registry/creator for tools.
- Register with `@register_tool("name")`. Enable tools with `tools_config` when creating a sandbox.

### Common Tools

- PythonExecutor: Execute Python snippets in the sandbox (non-interactive, or interactive in Notebook sandbox).
- ShellExecutor: Run Bash commands.
- FileOperation: `read_file`, `write_file`, `list_dir`, etc.

## 3. Management Layer

Managers orchestrate sandbox lifecycle and are the main integration point for apps.

### SandboxManager (concept)
Defines standard management interfaces: `create_sandbox`, `get_sandbox`, `stop_sandbox`, etc.

### LocalSandboxManager

- Location: `ms_enclave.manager.local_manager`
- Runs in-process and manages sandbox objects directly.
- Features: background auto-cleanup for `RUNNING` > 48h and `ERROR/STOPPED` > 1h sandboxes.

### HttpSandboxManager

- Location: `ms_enclave.manager.http_manager`
- Client proxy talking to the remote FastAPI server.
- API shape mirrors local manager for easy switching between local and remote modes.
