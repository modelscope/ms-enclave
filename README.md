<p align="center">
    <br>
    <img src="doc/asset/image/logo.png"/>
    <br>
<p>

<p align="center">
  <a href="README_zh.md">中文</a> &nbsp ｜ &nbsp English &nbsp
</p>

<p align="center">
<img src="https://img.shields.io/badge/python-%E2%89%A53.10-5be.svg">
<a href="https://badge.fury.io/py/ms-enclave"><img src="https://badge.fury.io/py/ms-enclave.svg" alt="PyPI version" height="18"></a>
<a href="https://pypi.org/project/ms-enclave"><img alt="PyPI - Downloads" src="https://static.pepy.tech/badge/ms-enclave"></a>
<a href="https://github.com/modelscope/ms-enclave/pulls"><img src="https://img.shields.io/badge/PR-welcome-55EB99.svg"></a>
<p>

## Introduction

ms-enclave is a modular and stable sandbox runtime environment that provides a secure isolated execution environment for applications. It implements strong isolation through Docker containers, equipped with local/HTTP managers and an extensible tool system, helping you execute code safely and efficiently in a controlled environment.

- 🔒 Secure Isolation: Complete isolation and resource limits based on Docker
- 🧩 Modular: Both sandboxes and tools are extensible (registered factory)
- ⚡ Stable Performance: Clean implementation, fast startup, with lifecycle management
- 🌐 Remote Management: Built-in FastAPI service, supports HTTP management
- 🔧 Tool System: Standardized tools enabled by sandbox type (OpenAI-style schema)

## System Requirements

- Python >= 3.10
- Operating System: Linux, macOS, or Windows with Docker support
- Docker daemon available on local machine (Notebook sandbox requires port 8888 open)

## Installation

### Install from PyPI

```bash
pip install ms-enclave
# If Docker support is needed, install extra dependencies
pip install 'ms-enclave[docker]'
```

### Install from Source

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
# If Docker support is needed, install extra dependencies
pip install -e '.[docker]'
```

## Quick Start: Minimal Viable Example (SandboxFactory)

> Tools need to be explicitly enabled in the configured tools_config, otherwise they won't be registered.

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
        # 1) Write file
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

## Typical Usage Patterns & Examples

- Direct use of SandboxFactory: Create/destroy sandboxes within a single process, most lightweight; suitable for scripts or one-time tasks
- Using LocalSandboxManager: Uniformly orchestrate lifecycle/cleanup of multiple sandboxes on local machine; suitable for service-oriented, multi-task parallel scenarios
- Using HttpSandboxManager: Manage sandboxes uniformly through remote HTTP service; suitable for cross-machine/distributed or stronger isolation deployments

### 0) Manager Factory: SandboxManagerFactory (Automatic Local/HTTP selection)

When to use:
- You want a single entry point that chooses Local or HTTP manager automatically.
- You prefer central registration and discovery of available manager types.

Key points:
- If manager_type is provided, it is used directly.
- If base_url is provided (in config or kwargs), HTTP manager is created.
- Otherwise, Local manager is created by default.

Example: implicit selection by base_url
```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory

async def main():
    async with SandboxManagerFactory.create_manager(base_url='http://127.0.0.1:8000') as m:
        # Use exactly like HttpSandboxManager
        # e.g., create a DOCKER sandbox and execute a tool
        # ... your code ...
        pass

asyncio.run(main())
```

Example: explicit selection + custom config
```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import SandboxManagerConfig, SandboxManagerType

async def main():
    cfg = SandboxManagerConfig(cleanup_interval=600)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, config=cfg
    ) as m:
        # Use exactly like LocalSandboxManager
        # ... your code ...
        pass

asyncio.run(main())
```

Discover registered manager types:
```python
from ms_enclave.sandbox.manager import SandboxManagerFactory
print(SandboxManagerFactory.get_registered_types())
```

### 1) Direct Sandbox Creation: SandboxFactory (Lightweight, Temporary)

Use Cases:

- Temporarily run a piece of code in scripts or microservices
- Fine-grained control over sandbox lifecycle (cleanup on context exit)

Example (Docker sandbox + Python execution):

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

### 2) Local Unified Orchestration: LocalSandboxManager (Multiple Sandboxes, Lifecycle Management)

Use Cases:

- Need to create/manage multiple sandboxes within the same process (create, query, stop, periodic cleanup)
- Want unified status view, statistics, and health checks

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

### 3) Remote Unified Management: HttpSandboxManager (Cross-machine/Isolated Deployment)

Use Cases:

- Run sandbox service on a separate host/container, invoke remotely via HTTP
- Multiple applications share a secure controlled sandbox cluster

Start the service first (choose one):

```bash
# Method A: Command line
ms-enclave server --host 0.0.0.0 --port 8000

# Method B: Python startup
python -c "from ms_enclave.sandbox import create_server; create_server().run(host='0.0.0.0', port=8000)"
```

Client example:

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

### 4) Pooled Sandboxes: Pre-warmed workers (Sandbox Pool)

Why:
- Amortize container startup by keeping a fixed-size pool of ready sandboxes.
- Each execution borrows a sandbox and returns it; requests queue FIFO when all are busy.

Local pool example:

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with LocalSandboxManager() as m:
        cfg = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        # Create a pool of 2 pre-warmed sandboxes
        await m.initialize_pool(pool_size=2, sandbox_type=SandboxType.DOCKER, config=cfg)

        # Execute multiple tasks; sandboxes are reused and queued FIFO when busy
        tasks = [
            m.execute_tool_in_pool('python_executor', {'code': f'print("task {i}")', 'timeout': 30})
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        print([r.output.strip() for r in results])

        # Pool stats
        stats = await m.get_stats()
        print('pool_size =', stats['pool_size'])

asyncio.run(main())
```

HTTP pool example:

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as m:
        cfg = DockerSandboxConfig(image='python:3.11-slim', tools_config={'python_executor': {}})
        await m.initialize_pool(pool_size=2, sandbox_type=SandboxType.DOCKER, config=cfg)

        r = await m.execute_tool_in_pool('python_executor', {'code': 'print("hello from pool")', 'timeout': 30})
        print(r.output)

asyncio.run(main())
```

Notes:
- Waiting timeout: `await m.execute_tool_in_pool(..., timeout=1.0)` raises `TimeoutError` if no sandbox is available in time.
- FIFO behavior: pool borrows/returns in FIFO order under load.
- Errors: even if a tool execution fails, the sandbox is returned to the pool.

---

## Sandbox Types & Tool Support

Current built-in sandbox types:

- DOCKER (General container execution)
  - Supported tools:
    - python_executor (Execute Python code)
    - shell_executor (Execute Shell commands)
    - file_operation (Read/write/delete/list files)
    - multi_code_executor (Multi-language code execution, supports python, cpp, csharp, go, java, nodejs, ts, rust, php, bash, pytest, jest, go_test, lua, r, perl, d_ut, ruby, scala, julia, kotlin_script, verilog, lean, swift, racket) Requires specifying image `volcengine/sandbox-fusion:server-20250609`
  - Features: Configurable memory/CPU limits, volume mounts, network toggle, privileged mode, port mapping

- DOCKER_NOTEBOOK (Jupyter Kernel Gateway environment)
  - Supported tools:
    - notebook_executor (Execute code through Jupyter kernel, supports saving code context)
  - Note: This type only loads notebook_executor; other DOCKER-specific tools won't be enabled in this sandbox
  - Dependencies: Requires port 8888 exposed, network enabled

Tool loading rules:

- Tools are only initialized and available when explicitly declared in `tools_config`
- Tools validate `required_sandbox_type`, automatically ignored if mismatched

Example:

```python
DockerSandboxConfig(tools_config={'python_executor': {}, 'shell_executor': {}, 'file_operation': {}})
DockerNotebookConfig(tools_config={'notebook_executor': {}})
```

---

## Common Configuration Options

- `image`: Docker image name (e.g., `python:3.11-slim` or `jupyter-kernel-gateway`)
- `memory_limit`: Memory limit (e.g., `512m`/`1g`)
- `cpu_limit`: CPU limit (float, >0)
- `volumes`: Volume mounts, formatted as `{host_path: {"bind": "/container/path", "mode": "rw"}}`
- `ports`: Port mapping, formatted as `{ "8888/tcp": ("127.0.0.1", 8888) }`
- `network_enabled`: Whether to enable network (Notebook sandbox requires True)
- `remove_on_exit`: Whether to delete container on exit (default True)

Manager Config (SandboxManagerConfig):
- `base_url`: If set, HttpSandboxManager is selected automatically
- `cleanup_interval`: Background cleanup interval in seconds (local manager)

**Example of Installing Additional Dependencies in Sandbox**
```python
async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
    # 1) Write a file
    requirements_file = '/sandbox/requirements.txt'
    await sandbox.execute_tool('file_operation', {
        'operation': 'write', 'file_path': f'{requirements_file}', 'content': 'numpy\npandas\nmodelscope\n'
    })
    # 2) Execute Python code
    result = await sandbox.execute_tool('python_executor', {
        'code': f"print('Hello from sandbox!')\nprint(open(f'{requirements_file}').read())"
    })
    print(result.output)

    # 3) Execute CLI
    result_cli = await sandbox.execute_command(f'pip install -r {requirements_file}')
    print(result_cli.stdout, flush=True)
```

**Example of Reading/Writing Host Files in Sandbox**
```python
async with LocalSandboxManager() as manager:
    # Create sandbox
    config = DockerSandboxConfig(
        # image='python-sandbox',
        image='python:3.11-slim',
        tools_config={'python_executor': {}, 'file_operation': {}},
        volumes={'~/Code/ms-enclave/output': {'bind': '/sandbox/data', 'mode': 'rw'}}
    )
    sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

    # Write file
    result = await manager.execute_tool(
        sandbox_id, 'file_operation', {'operation': 'write', 'file_path': '/sandbox/data/hello.txt', 'content': 'Hello, Sandbox!'}
    )
    print(result.model_dump())
```

---

## Error Handling & Debugging

```python
result = await sandbox.execute_tool('python_executor', {'code': 'print(1/0)'})
if result.error:
    print('Error message:', result.error)
else:
    print('Output:', result.output)
```

---

## Development & Testing

```bash
# Clone repository
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave

# Create virtual environment
conda create -n ms-enclave python=3.10 -y
conda activate ms-enclave

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run examples (provided in repository)
python examples/sandbox_usage_examples.py
python examples/local_manager_example.py
python examples/server_manager_example.py
```

---

## Contributing

We welcome contributions! Please check [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Contribution Steps

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Develop and add tests
4. Run tests locally: `pytest`
5. Commit changes: `git commit -m 'Add amazing feature'`
6. Push branch: `git push origin feature/amazing-feature`
7. Submit Pull Request

## License

This project is licensed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.
