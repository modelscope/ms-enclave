# 快速上手

`ms-enclave` 提供了两种主要的使用方式来满足不同的集成需求：

1. **SandboxFactory**：直接创建沙箱实例。最轻量，适合脚本、测试或一次性任务。
2. **SandboxManagerFactory**：通过管理器编排沙箱。适合构建服务、后台应用，提供生命周期管理、池化预热和自动清理功能。

下面将分别演示这两种方法。

## 方式一：轻量级脚本

这种方式直接实例化沙箱对象，使用 `async with` 语法确保上下文退出时销毁容器。

### 适用场景

- **单次任务**: 跑完即走的脚本。
- **单元测试**: 每个测试用例创建一个全新干净的环境。
- **简单实验**: 快速验证代码或工具功能。
- **精细控制**: 需要直接访问沙箱对象底层方法的情况。

### 代码示例

将以下代码保存为 `quickstart_script.py`：

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 1. 配置沙箱
    # 指定镜像和需要启用的工具（如 python_executor, file_operation）
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},  # 启用代码执行工具
            'file_operation': {},   # 启用文件操作工具
        }
    )

    print("正在启动沙箱...")
    # 2. 创建并启动沙箱
    # 使用 async with 自动管理生命周期（结束时自动销毁容器）
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print(f"沙箱已就绪 ID: {sandbox.id}")

        # 3. 写入文件
        # 调用 file_operation 工具
        print("正在写入文件...")
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/hello.txt',
            'content': 'Hello from ms-enclave!'
        })
        
        # 4. 执行 Python 代码
        # 调用 python_executor 工具读取刚才写入的文件
        print("正在执行代码...")
        result = await sandbox.execute_tool('python_executor', {
            'code': """
print('正在读取文件...')
with open('/sandbox/hello.txt', 'r') as f:
    content = f.read()
print(f'文件内容: {content}')
"""
        })
        
        # 5. 查看输出
        print("执行结果:", result.output)

if __name__ == '__main__':
    asyncio.run(main())
```

### 代码详解

1. **`SandboxFactory`**: 它是最底层的工厂类，用于直接创建沙箱实例。
   - `create_sandbox` 返回一个实现了异步上下文管理器协议的对象 (`AsyncContextManager`)。
2. **`DockerSandboxConfig`**: 
   - `image`: 指定 Docker 镜像，确保环境一致性。
   - `tools_config`: **关键点**。只有在这里显式启用的工具，才能在沙箱中使用。
3. **`execute_tool`**:
   - 这是与沙箱交互的主要方式。
   - 第一个参数是工具名称（如 `'python_executor'`），这个名字必须对应 `tools_config` 中的键。
   - 第二个参数是传递给工具的参数字典（如 `code`, `file_path` 等），由具体的工具定义。
4. **生命周期**:
   - `async with` 块结束时，会自动调用沙箱的 `stop()` 方法，停止并删除 Docker 容器，防止资源泄漏。


### 运行

```bash
python quickstart_script.py
```

> **注意**：首次运行时需要拉取 Docker 镜像（如 `python:3.11-slim`），可能需要一些时间。

输出示例：
```text
正在启动沙箱...
沙箱已就绪 ID: u53rksn7
正在写入文件...
正在执行代码...
[INFO:ms_enclave] [📦 u53rksn7] 正在读取文件...
[INFO:ms_enclave] [📦 u53rksn7] 文件内容: Hello from ms-enclave!
执行结果: 正在读取文件...
文件内容: Hello from ms-enclave!
```

---

## 方式二：应用集成

在开发 Web 服务或长期运行的应用时，推荐使用管理器（Manager）。它不仅能在本地运行（`LocalSandboxManager`），还可以无缝切换到远程 HTTP 模式，并提供沙箱池等高级功能。

### 适用场景

- **Web 服务后端**: 为多个用户请求同时提供沙箱环境。
- **长期运行的进程**: 需要自动清理过期沙箱，防止资源泄露。
- **性能敏感**: 利用沙箱池（Pool）技术预热容器，减少启动延迟。
- **分布式部署**: 将沙箱运行在远程服务器上，通过 HTTP 调用。

### 代码示例

将以下代码保存为 `quickstart_app.py`：

```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType, SandboxManagerConfig, SandboxManagerType

async def main():
    # 1. 配置管理器
    # 如需使用远程服务，可配置 base_url；这里演示本地模式
    manager_config = SandboxManagerConfig(cleanup_interval=600)  # 每10分钟后台清理一次过期沙箱

    print("正在初始化管理器...")
    # 2. 创建管理器
    # 显式指定 Local 类型，或者不传参也会默认使用 Local
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, 
        config=manager_config
    ) as manager:
        
        # 3. 配置沙箱
        sb_config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # 4. 通过管理器创建沙箱
        # 管理器会跟踪这个沙箱的状态，并返回 sandbox_id
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, sb_config)
        print(f"沙箱已创建 ID: {sandbox_id}")

        # 5. 执行工具
        # 所有的操作都通过 manager 代理进行，需传入 sandbox_id
        print("正在执行代码...")
        result = await manager.execute_tool(
            sandbox_id, 
            'python_executor', 
            {'code': 'import sys; print(f"Python Version: {sys.version}")'}
        )
        print(f"输出结果:\n{result.output.strip()}")

        # 6. 获取沙箱列表
        # 查看当前管理器纳管的所有沙箱
        sandboxes = await manager.list_sandboxes()
        print(f"当前活跃沙箱数: {len(sandboxes)}")

if __name__ == '__main__':
    asyncio.run(main())
```

### 代码详解

1. **`SandboxManagerFactory`**: 它是管理器的入口。
   - 如果提供了 `base_url`（如 `http://localhost:8000`），它会创建一个连接远程服务的 `HttpSandboxManager`。
   - 否则，它创建运行在当前进程内的 `LocalSandboxManager`。
   - 这使得你的业务代码可以在本地开发和分布式部署之间无缝切换。

2. **管理器操作 (`manager`)**:
   - `create_sandbox`: 不同于 `SandboxFactory`，这里返回的是 `sandbox_id` 字符串，而不是对象。
   - `execute_tool`: 需要传入 `sandbox_id` 来指定目标沙箱。
   - `list_sandboxes`: 方便监控系统内所有沙箱的状态。

3. **资源清理**:
   - `LocalSandboxManager` 包含一个后台任务，会自动清理状态异常或长期闲置（默认 48小时）的沙箱，增强了系统的健壮性。

### 运行

```bash
python quickstart_app.py
```

输出示例：
```text
正在初始化管理器...
[INFO:ms_enclave] Local sandbox manager started
[INFO:ms_enclave] Created and started sandbox 98to5a2p of type docker
沙箱已创建 ID: 98to5a2p
正在执行代码...
[INFO:ms_enclave] [📦 98to5a2p] Python Version: 3.11.14 (main, Nov 18 2025, 04:42:43) [GCC 14.2.0]
输出结果:
Python Version: 3.11.14 (main, Nov 18 2025, 04:42:43) [GCC 14.2.0]
当前活跃沙箱数: 1
[INFO:ms_enclave] Cleaning up 1 sandboxes
[INFO:ms_enclave] Deleted sandbox 98to5a2p
[INFO:ms_enclave] Local sandbox manager stopped
```

## 总结

- **做实验、写脚本、单元测试** -> 推荐 **SandboxFactory**。
- **写后端服务、任务调度、生产环境** -> 推荐 **SandboxManagerFactory**。
