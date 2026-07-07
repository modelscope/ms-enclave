# 5 分钟上手

跑完这一页，你会用 `ms-enclave` 在 Docker 沙箱里执行一段 Python 代码。

> 准备：已完成 [安装](installation.md)，本机 Docker 守护进程在运行。

## 最小示例

把以下代码保存为 `hello_sandbox.py`：

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 1) 配置沙箱：指定镜像 + 启用 python_executor 工具
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
    )

    # 2) async with 自动管理生命周期（启动 → 使用 → 销毁容器）
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print("hello from ms-enclave")'
        })
        print(result.output.strip())

asyncio.run(main())
```

运行：

```bash
python hello_sandbox.py
```

预期输出（首次运行会先拉取 `python:3.11-slim`）：

```text
hello from ms-enclave
```

## 关键点回顾

- **`tools_config` 必须显式声明工具**：未声明的工具不会注册，调用会失败。
- **`execute_tool(tool_name, parameters)`**：第一个参数对应 `tools_config` 的键；第二个参数由具体工具决定（这里 `python_executor` 需要 `code`）。
- **`async with`**：退出时自动 stop + 删除容器，避免泄漏。

## 下一步

- 想理解 `Sandbox` / `Manager` / `Tool` 三个抽象 → [核心概念](concepts.md)
- 想知道还有哪些入口可选 → [使用指南概览](../guides/index.md)
- 在应用里要管理多个沙箱 → [本地管理器](../guides/local-manager.md)
- 让 LLM 自主调用工具 → [接入 LLM Agent](../guides/agent-integration.md)
