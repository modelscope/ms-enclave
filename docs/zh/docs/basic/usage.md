# 基础使用与场景示例

`ms-enclave` 提供了多种使用模式以适应不同的集成需求，从轻量级的单次执行到复杂的集群管理。

## 1. 典型使用场景

### 1.1 快速开始：SandboxFactory (最轻量)

如果您只需要临时运行一段代码，不需要复杂的管理功能，可以直接使用 `SandboxFactory`。这是最轻量的方式，适合脚本或一次性任务。

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def demo_sandbox_factory():
    # 配置沙箱，启用 python_executor 工具
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}}
    )

    # 使用 async with 自动管理生命周期（创建 -> 启动 -> 使用 -> 停止 -> 清理）
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        result = await sandbox.execute_tool('python_executor', {
            'code': 'import sys; print(f"Python {sys.version}")'
        })
        print(f"[SandboxFactory] Output: {result.output.strip()}")

# asyncio.run(demo_sandbox_factory())
```

### 1.2 统一管理入口：SandboxManagerFactory

如果您希望代码能够灵活切换本地或远程模式，或者统一管理配置，可以使用工厂模式。

- 传入 `base_url` 时自动创建 HTTP 管理器。
- 传入 `manager_type=SandboxManagerType.LOCAL` 时创建本地管理器。

```python
from ms_enclave.sandbox.manager import SandboxManagerFactory, SandboxManagerType
from ms_enclave.sandbox.model import SandboxManagerConfig

async def demo_manager_factory():
    # 示例：创建本地管理器
    cfg = SandboxManagerConfig(cleanup_interval=600)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, config=cfg
    ) as manager:
        print(f"[ManagerFactory] Created manager: {type(manager).__name__}")
```

### 1.3 本地编排：LocalSandboxManager (多任务并行)

适合在同一进程内需要创建、管理多个沙箱，并需要后台自动清理机制的场景。

```python
from ms_enclave.sandbox.manager import LocalSandboxManager

async def demo_local_manager():
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(tools_config={'shell_executor': {}})
        # 创建沙箱
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
        
        # 执行工具
        res = await manager.execute_tool(
            sandbox_id, 'shell_executor', {'command': 'echo "Hello Local Manager"'}
        )
        print(f"[LocalManager] Output: {res.output.strip()}")

        # 获取列表
        sandboxes = await manager.list_sandboxes()
        print(f"[LocalManager] Active sandboxes: {len(sandboxes)}")
```

### 1.4 远程管理：HttpSandboxManager (分布式/隔离)

当沙箱服务运行在独立服务器上时使用。

> **前提**：需要先启动服务器 `ms-enclave server`。

```python
from ms_enclave.sandbox.manager import HttpSandboxManager

async def demo_http_manager():
    # 假设服务运行在本地 8000 端口
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

### 1.5 高性能模式：Sandbox Pool (预热复用)

通过预热沙箱池来减少容器启动时间，提高并发吞吐量。支持 FIFO 排队。

```python
async def demo_sandbox_pool():
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        # 初始化池，预热 2 个沙箱
        print("[Pool] Initializing pool...")
        await manager.initialize_pool(pool_size=2, sandbox_type=SandboxType.DOCKER, config=config)

        # 借用沙箱执行任务，完成后自动归还
        result = await manager.execute_tool_in_pool(
            'python_executor', 
            {'code': 'print("Executed in pool")'},
            timeout=30 # 等待空闲沙箱的超时时间
        )
        print(f"[Pool] Output: {result.output.strip()}")
        
        stats = await manager.get_stats()
        print(f"[Pool] Stats: {stats}")
```

## 2. 高级功能

### 2.1 在 Sandbox 中安装额外依赖

由于沙箱通常是隔离的，如果需要第三方库，可以通过 `file_operation` 写入 `requirements.txt` 并执行安装命令。

```python
async def demo_install_dependencies():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}, 'file_operation': {}, 'shell_executor': {}}
    )
    
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print("[Deps] Installing dependencies...")
        # 1. 写入 requirements.txt
        await sandbox.execute_tool('file_operation', {
            'operation': 'write', 
            'file_path': '/sandbox/requirements.txt', 
            'content': 'numpy' # 示例依赖
        })
        
        # 2. 执行安装命令
        install_res = await sandbox.execute_command('pip install -r /sandbox/requirements.txt')
        if install_res.exit_code != 0:
            print(f"[Deps] Install failed: {install_res.stderr}")
            return

        # 3. 验证安装
        res = await sandbox.execute_tool('python_executor', {
            'code': 'import numpy; print(f"Numpy version: {numpy.__version__}")'
        })
        print(f"[Deps] Result: {res.output.strip()}")
```

### 2.2 读写宿主机文件 (挂载 Volume)

通过 Docker 挂载，可以让沙箱读写宿主机上的文件。这对于处理大文件或持久化数据非常有用。

```python
import os

async def demo_host_volume():
    # 在宿主机创建一个临时目录用于测试
    host_dir = os.path.abspath("./temp_sandbox_data")
    os.makedirs(host_dir, exist_ok=True)
    with open(os.path.join(host_dir, "host_file.txt"), "w") as f:
        f.write("Hello from Host")

    # 配置挂载：宿主机路径 -> 容器内路径
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'shell_executor': {}},
        volumes={host_dir: {'bind': '/sandbox/data', 'mode': 'rw'}}
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 读取宿主机文件
        res = await sandbox.execute_tool('shell_executor', {
            'command': 'cat /sandbox/data/host_file.txt'
        })
        print(f"[Volume] Read from host: {res.output.strip()}")
        
        # 写入文件回宿主机
        await sandbox.execute_tool('shell_executor', {
            'command': 'echo "Response from Sandbox" > /sandbox/data/sandbox_file.txt'
        })
    
    # 验证宿主机上的文件
    with open(os.path.join(host_dir, "sandbox_file.txt"), "r") as f:
        print(f"[Volume] Read from sandbox write: {f.read().strip()}")
    
    # 清理
    import shutil
    shutil.rmtree(host_dir)
```

## 3. 工具使用详解

以下是常用工具的参数示例。请确保在 `tools_config` 中启用了对应工具。

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
        # 1. Python Executor
        # 参数: code (str)
        py_res = await sb.execute_tool('python_executor', {'code': 'print(1+1)'})
        print(f"[Tool] Python: {py_res.output.strip()}")

        # 2. Shell Executor
        # 参数: command (str), timeout (int, optional)
        sh_res = await sb.execute_tool('shell_executor', {'command': 'date'})
        print(f"[Tool] Shell: {sh_res.output.strip()}")

        # 3. File Operation
        # 写入
        await sb.execute_tool('file_operation', {
            'operation': 'write', 'file_path': '/sandbox/test.txt', 'content': 'content'
        })
        # 读取
        read_res = await sb.execute_tool('file_operation', {
            'operation': 'read', 'file_path': '/sandbox/test.txt'
        })
        print(f"[Tool] File Read: {read_res.output}")
```

## 4. 手动生命周期管理

如果不使用 `async with` 上下文管理器，您需要手动处理启动和释放资源，这在某些异步流控制复杂的场景（如长期持有的连接）中很有用。

```python
async def demo_manual_lifecycle():
    config = DockerSandboxConfig(tools_config={'shell_executor': {}})
    
    # 1. 创建实例
    sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)
    
    try:
        # 2. 显式启动
        await sandbox.start()
        print("[Manual] Sandbox started")
        
        # 3. 执行操作
        res = await sandbox.execute_tool('shell_executor', {'command': 'echo manual'})
        print(f"[Manual] Output: {res.output.strip()}")
        
    finally:
        # 4. 显式停止
        await sandbox.stop()
        print("[Manual] Cleanup done")
```
