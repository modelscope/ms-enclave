# 直接使用沙箱（SandboxFactory）

`SandboxFactory` 是最轻量的入口，直接创建沙箱实例并由调用方负责生命周期。适合：

- 一次性脚本
- 单元测试（每个用例创建干净环境）
- 快速实验或精细控制底层 API

## 推荐写法：`async with` 上下文

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}, 'file_operation': {}},
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        result = await sandbox.execute_tool('python_executor', {
            'code': 'import sys; print(sys.version)'
        })
        print(result.output.strip())

asyncio.run(main())
```

退出 `async with` 时会自动 `stop` 并清理 Docker 容器。

## 关键点

1. **`tools_config` 必须显式声明要启用的工具**，未声明的工具即使已注册也不会加载。
2. `execute_tool(tool_name, parameters)` 是与沙箱交互的主要方式，`tool_name` 必须匹配 `tools_config` 的键。
3. 返回值是 `ToolResult`，含 `status`、`output`、`error` 等字段。

## 手动管理生命周期

如果业务流程跨多个异步上下文（例如长连接），可以不使用 `async with`，显式控制 `start/stop`：

```python
async def manual_lifecycle():
    config = DockerSandboxConfig(tools_config={'shell_executor': {}})
    sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)
    try:
        await sandbox.start()
        result = await sandbox.execute_tool('shell_executor', {'command': 'echo hi'})
        print(result.output.strip())
    finally:
        await sandbox.stop()  # 务必在 finally 中释放
```

> **注意**：手动模式下若忘记 `stop()`，Docker 容器会残留。生产环境推荐用 `LocalSandboxManager`，它自带后台清理。
