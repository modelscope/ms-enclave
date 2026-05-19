# HTTP 客户端（HttpSandboxManager）

`HttpSandboxManager` 是 `LocalSandboxManager` 的远程版本，封装了对 [HTTP 服务](http-server.md) 的 REST 调用。API 形态与本地完全一致——这意味着业务代码在本地与远程之间切换无需修改。

## 基本用法

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as manager:
        sandbox_id = await manager.create_sandbox(
            SandboxType.DOCKER,
            DockerSandboxConfig(
                image='python:3.11-slim',
                tools_config={'python_executor': {}},
            ),
        )
        result = await manager.execute_tool(
            sandbox_id, 'python_executor',
            {'code': 'import platform; print(platform.node())'},
        )
        print(result.output.strip())
        await manager.delete_sandbox(sandbox_id)

asyncio.run(main())
```

## 带鉴权

服务端如启用了 `api_key`，客户端要带上：

```python
HttpSandboxManager(base_url='http://server:8000', api_key='your-secret-key')
```

## 用工厂统一切换本地 / 远程

`SandboxManagerFactory` 根据 `base_url` 是否提供自动选择：

```python
from ms_enclave.sandbox.manager import SandboxManagerFactory

# 本地（开发）
async with SandboxManagerFactory.create_manager() as manager:
    ...

# 远程（生产）
async with SandboxManagerFactory.create_manager(base_url='http://server:8000') as manager:
    ...
```

业务代码相同，部署模式自由切换。

## 超时与重试

`HttpSandboxManager` 接受 `timeout` 参数（秒，应用于单次 HTTP 请求）。长任务（大镜像拉取、容器冷启动）请把超时调大：

```python
HttpSandboxManager(base_url='...', timeout=120)
```

服务端镜像拉取慢导致超时时，可以提前在服务端 `docker pull` 好镜像。

## 注意事项

- 客户端不感知服务端是否启用了沙箱池；要使用池，请在服务端通过 `POST /pool/initialize` 初始化后用 `execute_tool_in_pool` 调用。
- 网络抖动场景建议自行加重试（如 `tenacity`），SDK 不内置重试。
