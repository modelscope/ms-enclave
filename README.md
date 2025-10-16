# ms-enclave

A modular and stable sandbox runtime environment

## Overview

ms-enclave is a modular and stable sandbox runtime environment that provides a secure isolated execution environment for applications. It achieves strong isolation through Docker containers, with accompanying local/HTTP managers and an extensible tool system, enabling you to safely and efficiently execute code in a controlled environment.

- 🔒 Secure Isolation: Full isolation and resource limitation based on Docker
- 🧩 Modular: Extensible sandbox and tools (registration factory)
- ⚡ Stable Performance: Simple implementation, fast startup, lifecycle management
- 🌐 Remote Management: Built-in FastAPI service, supports HTTP management
- 🔧 Tool System: Standardized tools enabled by sandbox type (OpenAI-style schema)

## System Requirements

- Python >= 3.10
- Operating System: Linux, macOS, or Windows with Docker support
- Docker daemon running locally (Notebook sandbox requires port 8888 open)

## Installation

### Install from PyPI

```bash
pip install ms-enclave
```

### Install from Source

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
```

## Quick Start: Minimal Example (SandboxFactory)

> Tools need to be explicitly enabled in the tools_config setting, otherwise they won't be registered.

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        memory_limit='512m',
        tools_config={
            'python_executor': {},
            'file_operation': {},
            'shell_executor': {}
        }
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 1) Write a file
        await sandbox.execute_tool('file_operation', {
            'operation': 'write', 'file_path': '/sandbox/hello.txt', 'content': 'hi from enclave'
        })
        # 2) Execute Python code
        result = await sandbox.execute_tool('python_executor', {
            'code': "print('Hello from sandbox!')\nprint(open('/sandbox/hello.txt').read())"
        })
        print(result.output)

asyncio.run(main())
```

---

## Typical Usage Scenarios and Examples

- Directly using SandboxFactory: Create/destroy sandboxes in a single process—lightweight; suitable for scripts or one-off tasks
- Using LocalSandboxManager: Manage the lifecycle/cleanup of multiple sandboxes locally; suitable for service-oriented or multi-task parallel scenarios
- Using HttpSandboxManager: Unified sandbox management through remote HTTP services; suitable for cross-machine/distributed or more isolated deployments

### 1) Direct Sandbox Creation: SandboxFactory (Lightweight, Temporary)

Usage Scenarios:

- Temporarily execute code in scripts or microservices
- Fine-grained control over sandbox lifecycle (cleanup upon context exit)

Example (Docker Sandbox + Python Execution):

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    cfg = DockerSandboxConfig(
        tools_config={'python_executor': {}}
    )
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, cfg) as sb:
        r = await sb.execute_tool('python_executor', {
            'code': 'import platform; print(platform.python_version())'
        })
        print(r.output)

asyncio.run(main())
```

### 2) Local Unified Management: LocalSandboxManager (Multi-Sandbox, Lifecycle Management)

Usage Scenarios:

- Create/manage multiple sandboxes within the same process (creation, query, stop, periodic cleanup)
- Unified view for monitoring stats and health

Example:

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with LocalSandboxManager() as manager:
        cfg = DockerSandboxConfig(tools_config={'shell_executor': {}})
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, cfg)

        # Execute command
        res = await manager.execute_tool(sandbox_id, 'shell_executor', {'command': 'echo hello'})
        print(res.output.strip())  # hello

        # View list
        infos = await manager.list_sandboxes()
        print([i.id for i in infos])

        # Stop and delete
        await manager.stop_sandbox(sandbox_id)
        await manager.delete_sandbox(sandbox_id)

asyncio.run(main())
```

### 3) Remote Unified Management: HttpSandboxManager (Cross-Machine/Isolated Deployment)

Usage Scenarios:

- Run sandbox services on dedicated hosts/containers, invoke remotely via HTTP
- Share a secure controlled sandbox cluster among multiple applications

Start the service (choose one):

```bash
# Option A: Command line
ms-enclave server --host 0.0.0.0 --port 8000

# Option B: Python script
python -c "from ms_enclave.sandbox import create_server; create_server().run(host='0.0.0.0', port=8000)"
```

Client Example:

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as m:
        cfg = DockerSandboxConfig(tools_config={'python_executor': {}})
        sid = await m.create_sandbox(SandboxType.DOCKER, cfg)
        r = await m.execute_tool(sid, 'python_executor', {'code': 'print("Hello remote")'})
        print(r.output)
        await m.delete_sandbox(sid)

asyncio.run(main())
```

---

## Sandbox Types and Tool Support

Currently Supported Sandbox Types:

- DOCKER (General-purpose container execution)
  - Supported tools:
    - python_executor (execute Python code)
    - shell_executor (execute Shell commands)
    - file_operation (read/write/delete/list files)
  - Features: Configurable memory/CPU limits, volume mounts, network toggling, privileged mode, port mapping

- DOCKER_NOTEBOOK (Jupyter Kernel Gateway environment)
  - Supported tools:
    - notebook_executor (execute code via Jupyter Kernel, supports context saving)
  - Note: This type only loads notebook_executor; other DOCKER-specific tools won't be enabled in this sandbox.
  - Dependencies: Requires port 8888 exposed and network enabled

Tool Loading Rules:

- Tools are initialized and made available only when explicitly declared in `tools_config`.
- Tools validate `required_sandbox_type`; unmatched types will be ignored automatically.

Example:

```python
DockerSandboxConfig(tools_config={'python_executor': {}, 'shell_executor': {}, 'file_operation': {}})
DockerNotebookConfig(tools_config={'notebook_executor': {}})
```

---

## Common Configuration Options

- `image`: Docker image name (e.g., `python:3.11-slim` or `jupyter-kernel-gateway`)
- `memory_limit`: Memory limit (e.g., `512m` / `1g`)
- `cpu_limit`: CPU limit (float > 0)
- `volumes`: Volume mounts, e.g., `{host_path: {"bind": "/container/path", "mode": "rw"}}`
- `ports`: Port mappings, e.g., `{ "8888/tcp": ("127.0.0.1", 8888) }`
- `network_enabled`: Enable network (Notebook sandbox requires True)
- `remove_on_exit`: Automatically remove container on exit (default True)

---

## Error Handling and Debugging

```python
result = await sandbox.execute_tool('python_executor', {'code': 'print(1/0)'})
if result.error:
    print('Error:', result.error)
else:
    print('Output:', result.output)
```

---

## Development and Testing

```bash
# Clone the repository
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave

# Setup virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run examples (provided in the repository)
python examples/sandbox_usage_examples.py
python examples/local_manager_example.py
python examples/server_manager_example.py
```

---

## Available Tools

- `python_executor`: Execute Python code (DOCKER)
- `shell_executor`: Execute Shell commands (DOCKER)
- `file_operation`: Read/Write/Delete/List files (DOCKER)
- `notebook_executor`: Execute via Jupyter Kernel (DOCKER_NOTEBOOK)
- You can also register custom tools via the Tool factory (`@register_tool`).

---

## Contribution

We welcome contributions! Please check [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Steps to Contribute

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Develop and add tests
4. Run local tests: `pytest`
5. Commit changes: `git commit -m 'Add amazing feature'`
6. Push the branch: `git push origin feature/amazing-feature`
7. Submit a Pull Request

## License

This project is licensed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.
