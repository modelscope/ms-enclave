# 沙箱池（Sandbox Pool）

容器冷启动通常需要数百毫秒到数秒。对于高并发服务，提前预热若干沙箱组成"池"，可以将单次执行时间显著降低。

## 工作原理

`LocalSandboxManager` 内置 FIFO 池：

1. `initialize_pool(pool_size, ...)` 预先创建并启动指定数量的沙箱
2. `execute_tool_in_pool(...)` 从池中借一个空闲沙箱执行，完成后自动归还
3. 当池中无空闲沙箱时，调用方按 `timeout` 等待

## 完整示例

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}},
        )

        # 预热 2 个沙箱
        await manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config,
        )

        # 借用执行，自动归还
        result = await manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("from pool")'},
            timeout=30,  # 等空闲沙箱的超时
        )
        print(result.output.strip())

        print(await manager.get_stats())

asyncio.run(main())
```

## 调优建议

- **池大小**：根据并发峰值估算。一般为"预期 QPS × 单次执行平均耗时（秒）"的上取整。
- **沙箱镜像**：预热阶段会拉取并启动镜像，启动时间随镜像体积上升。生产环境建议预先构建瘦身镜像。
- **池满时的行为**：`timeout` 为 `None` 时会一直等待；为正数时超时会抛 `TimeoutError`。Web 服务务必设置合理 timeout。
- **复用后的副作用**：同一沙箱可能被多次借出。若工具会修改文件系统/环境变量，记得在执行末尾清理，或改用一次性 `SandboxFactory`。

## HTTP 服务端的池

服务端也支持池，对应端点为 `POST /pool/initialize` 和 `POST /pool/execute`。详见 [HTTP 服务](../deployment/http-server.md)。
