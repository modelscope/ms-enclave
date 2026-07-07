# Notebook 沙箱（保持变量状态）

`SandboxType.DOCKER_NOTEBOOK` 在容器内启动一个 [Jupyter Kernel Gateway](https://jupyter-kernel-gateway.readthedocs.io/) 实例，让多次 `notebook_executor` 调用共享同一个 Python 内核。**变量、import、状态都会在调用之间保留**——这是它与无状态 `python_executor` 的核心区别。

## 适用场景

- 数据探索：先读数据，再多次绘图 / 统计
- 多步训练：加载模型一次，然后多次推理
- LLM Agent 的多轮 Python 工具调用

## 前置依赖

- Docker 守护进程
- 宿主机 8888 端口可用（首次运行会自动构建 `jupyter-kernel-gateway` 镜像）
- 安装客户端额外依赖：`pip install websocket-client requests`

## 基本示例

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerNotebookConfig, SandboxType

async def main():
    config = DockerNotebookConfig(
        tools_config={'notebook_executor': {}},
        port=8888,
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER_NOTEBOOK, config) as sb:
        # 第一次调用：定义变量
        await sb.execute_tool('notebook_executor', {
            'code': 'x = [1, 2, 3, 4, 5]'
        })

        # 第二次调用：x 仍然存在
        res = await sb.execute_tool('notebook_executor', {
            'code': 'print(sum(x))'
        })
        print(res.output.strip())  # 15

        # 第三次调用：可以继续 import 并使用
        res = await sb.execute_tool('notebook_executor', {
            'code': 'import statistics; print(statistics.mean(x))'
        })
        print(res.output.strip())  # 3

asyncio.run(main())
```

## 配置项

`DockerNotebookConfig` 继承自 `DockerSandboxConfig`，额外字段：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `image` | `jupyter-kernel-gateway` | 镜像名；不存在时框架会自动 build |
| `host` | `127.0.0.1` | Jupyter 服务监听地址 |
| `port` | `8888` | 暴露到宿主机的端口 |
| `token` | `None` | 可选鉴权 token |

> 因为要建立 WebSocket，`network_enabled` 强制为 `True`，且自动加上 `8888/tcp` 端口映射。

## 工具加载规则

`SandboxType.DOCKER_NOTEBOOK` **只**加载 `notebook_executor`，其他 Docker 专属工具（`python_executor` / `shell_executor` / `file_operation`）即使写在 `tools_config` 里也不会启用。如果同时需要 Shell/文件能力，请用 `DockerSandbox` + `python_executor`。

## 与多并发使用

每个 Notebook 沙箱占一个端口、一个内核。多并发请用多个沙箱实例，并显式分配不同端口：

```python
DockerNotebookConfig(port=8888, tools_config={'notebook_executor': {}})
DockerNotebookConfig(port=8889, tools_config={'notebook_executor': {}})
```

## 故障排查

- **`Jupyter Kernel Gateway failed to become ready within 30 seconds`**：镜像首次构建较慢，等首次跑过后再试；或自己提前构建好 `jupyter-kernel-gateway` 镜像。
- **`websocket-client package is required`**：`pip install websocket-client`。
- **端口冲突**：把 `port` 改成空闲端口。
