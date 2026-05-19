# Basic Usage and Scenarios

`ms-enclave` supports several usage modes from lightweight one-offs to manager-driven orchestration.

## 1. Typical Scenarios

### 1.1 Quick Start: SandboxFactory (lightest)

Use `SandboxFactory` to run temporary code without heavy management overhead.

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def demo_sandbox_factory():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}}
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        result = await sandbox.execute_tool('python_executor', {
            'code': 'import sys; print(f"Python {sys.version}")'
        })
        print(f"[SandboxFactory] Output: {result.output.strip()}")

# asyncio.run(demo_sandbox_factory())
```

### 1.2 Unified entry: SandboxManagerFactory

Create a local or HTTP manager by config.

```python
from ms_enclave.sandbox.manager import SandboxManagerFactory, SandboxManagerType
from ms_enclave.sandbox.model import SandboxManagerConfig

async def demo_manager_factory():
    cfg = SandboxManagerConfig(cleanup_interval=600)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, config=cfg
    ) as manager:
        print(f"[ManagerFactory] Created manager: {type(manager).__name__}")
```

### 1.3 Local orchestration: LocalSandboxManager

Create, manage, and auto-clean multiple sandboxes within the same process.

```python
from ms_enclave.sandbox.manager import LocalSandboxManager

async def demo_local_manager():
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(tools_config={'shell_executor': {}})
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
        
        res = await manager.execute_tool(
            sandbox_id, 'shell_executor', {'command': 'echo "Hello Local Manager"'}
        )
        print(f"[LocalManager] Output: {res.output.strip()}")

        sandboxes = await manager.list_sandboxes()
        print(f"[LocalManager] Active sandboxes: {len(sandboxes)}")
```

### 1.4 Remote management: HttpSandboxManager

Operate sandboxes hosted by a remote ms-enclave server.

```python
from ms_enclave.sandbox.manager import HttpSandboxManager

async def demo_http_manager():
    try:
        async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as manager:
            config = DockerSandboxConfig(tools_config={'python_executor': {}})
            sid = await manager.create_sandbox(SandboxType.DOCKER, config)
            res = await manager.execute_tool(sid, 'python_executor', {'code': 'print("Remote Hello")'})
            print(f"[HttpManager] Output: {res.output.strip()}")
            await manager.delete_sandbox(sid)
    except Exception as e:
        print(f"[HttpManager] Skipped: Server might not be running. {e}")
```

### 1.5 High-throughput: Sandbox Pool (prewarm & reuse)

Prewarm sandbox pool to reduce cold-start latency; FIFO queueing supported.

```python
async def demo_sandbox_pool():
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        print("[Pool] Initializing pool...")
        await manager.initialize_pool(pool_size=2, sandbox_type=SandboxType.DOCKER, config=config)

        result = await manager.execute_tool_in_pool(
            'python_executor', 
            {'code': 'print("Executed in pool")'},
            timeout=30
        )
        print(f"[Pool] Output: {result.output.strip()}")
        
        stats = await manager.get_stats()
        print(f"[Pool] Stats: {stats}")
```

## 2. Advanced

### 2.1 Install extra dependencies in sandbox

Write `requirements.txt` via `file_operation` and install with pip.

```python
async def demo_install_dependencies():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}, 'file_operation': {}, 'shell_executor': {}}
    )
    
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print("[Deps] Installing dependencies...")
        await sandbox.execute_tool('file_operation', {
            'operation': 'write', 
            'file_path': '/sandbox/requirements.txt', 
            'content': 'numpy'
        })
        
        install_res = await sandbox.execute_command('pip install -r /sandbox/requirements.txt')
        if install_res.exit_code != 0:
            print(f"[Deps] Install failed: {install_res.stderr}")
            return

        res = await sandbox.execute_tool('python_executor', {
            'code': 'import numpy; print(f"Numpy version: {numpy.__version__}")'
        })
        print(f"[Deps] Result: {res.output.strip()}")
```

### 2.2 Read/write host files (volumes)

Mount a host directory for large files or persistence.

```python
import os

async def demo_host_volume():
    host_dir = os.path.abspath("./temp_sandbox_data")
    os.makedirs(host_dir, exist_ok=True)
    with open(os.path.join(host_dir, "host_file.txt"), "w") as f:
        f.write("Hello from Host")

    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'shell_executor': {}},
        volumes={host_dir: {'bind': '/sandbox/data', 'mode': 'rw'}}
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        res = await sandbox.execute_tool('shell_executor', {
            'command': 'cat /sandbox/data/host_file.txt'
        })
        print(f"[Volume] Read from host: {res.output.strip()}")
        
        await sandbox.execute_tool('shell_executor', {
            'command': 'echo "Response from Sandbox" > /sandbox/data/sandbox_file.txt'
        })
    
    with open(os.path.join(host_dir, "sandbox_file.txt"), "r") as f:
        print(f"[Volume] Read from sandbox write: {f.read().strip()}")
    
    import shutil
    shutil.rmtree(host_dir)
```

## 3. Tools usage details

Ensure the corresponding tools are enabled in `tools_config`.

```python
async def demo_tools_usage():
    config = DockerSandboxConfig(
        tools_config={
            'python_executor': {}, 
            'shell_executor': {}, 
            'file_operation': {}
        }
    )
    
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sb:
        py_res = await sb.execute_tool('python_executor', {'code': 'print(1+1)'})
        print(f"[Tool] Python: {py_res.output.strip()}")

        sh_res = await sb.execute_tool('shell_executor', {'command': 'date'})
        print(f"[Tool] Shell: {sh_res.output.strip()}")

        await sb.execute_tool('file_operation', {
            'operation': 'write', 'file_path': '/sandbox/test.txt', 'content': 'content'
        })
        read_res = await sb.execute_tool('file_operation', {
            'operation': 'read', 'file_path': '/sandbox/test.txt'
        })
        print(f"[Tool] File Read: {read_res.output}")
```

## 4. Manual lifecycle management

If not using `async with`, manage start/stop explicitly.

```python
async def demo_manual_lifecycle():
    config = DockerSandboxConfig(tools_config={'shell_executor': {}})
    
    sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)
    
    try:
        await sandbox.start()
        print("[Manual] Sandbox started")
        
        res = await sandbox.execute_tool('shell_executor', {'command': 'echo manual'})
        print(f"[Manual] Output: {res.output.strip()}")
        
    finally:
        await sandbox.stop()
        print("[Manual] Cleanup done")
```
