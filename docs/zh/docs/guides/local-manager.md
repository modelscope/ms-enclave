# 本地管理器（LocalSandboxManager）

`LocalSandboxManager` 在当前进程内统一管理多个沙箱，提供：

- 通过 `sandbox_id` 字符串引用沙箱（适合 Web 服务跨请求传递）
- 自动后台清理过期 / 异常沙箱
- 与 `HttpSandboxManager` 接口一致，本地与远程可无缝切换

## 适用场景

- Web 服务后端：为不同用户请求维护多个沙箱
- 长期运行的进程：避免泄漏 Docker 容器
- 需要按 ID 查询、停止沙箱的任务调度系统

## 基本示例

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType, SandboxManagerConfig

async def main():
    # 每 10 分钟扫一次过期沙箱
    manager_config = SandboxManagerConfig(cleanup_interval=600)

    async with LocalSandboxManager(config=manager_config) as manager:
        sandbox_id = await manager.create_sandbox(
            SandboxType.DOCKER,
            DockerSandboxConfig(
                image='python:3.11-slim',
                tools_config={'python_executor': {}},
            ),
        )
        print(f'Sandbox: {sandbox_id}')

        result = await manager.execute_tool(
            sandbox_id,
            'python_executor',
            {'code': 'print(40 + 2)'},
        )
        print(result.output.strip())  # 42

        # 查询活跃沙箱
        sandboxes = await manager.list_sandboxes()
        print(f'Active: {len(sandboxes)}')

asyncio.run(main())
```

## 常用 API

| 方法 | 说明 |
|---|---|
| `create_sandbox(type, config)` | 创建并启动沙箱，返回 `sandbox_id` |
| `execute_tool(id, tool_name, params)` | 在指定沙箱内执行工具 |
| `get_sandbox_info(id)` | 查询单个沙箱信息（含状态） |
| `list_sandboxes(status=None)` | 列出所有沙箱（可按状态过滤） |
| `get_sandbox_tools(id)` | 获取该沙箱已启用工具的 OpenAI schema |
| `stop_sandbox(id)` / `delete_sandbox(id)` | 显式停止/删除 |
| `get_stats()` | 返回总数、运行中数量等统计信息 |

## 自动清理机制

`LocalSandboxManager` 启动后会运行一个后台清理协程，按 `cleanup_interval` 周期扫描：

- `RUNNING` 状态超过 48 小时的沙箱会被回收
- `STOPPED` / `ERROR` 状态超过 1 小时的沙箱会被回收

无需手动触发，但你随时可以调用 `cleanup_all_sandboxes()` 强制清理。

## 何时不要用它

- 沙箱要跨多台机器调度 → 用 [`HttpSandboxManager`](../deployment/http-client.md)
- 需要预热并复用沙箱以降低启动延迟 → 见 [沙箱池](sandbox-pool.md)
- 只跑一次性脚本 → [`SandboxFactory`](sandbox-factory.md) 更直接
