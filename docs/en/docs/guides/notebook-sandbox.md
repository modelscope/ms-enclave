# Notebook Sandbox (Stateful Kernel)

`SandboxType.DOCKER_NOTEBOOK` starts a [Jupyter Kernel Gateway](https://jupyter-kernel-gateway.readthedocs.io/) inside the container. Multiple `notebook_executor` calls share the same Python kernel, so **variables, imports, and state persist across calls** — that's the key difference from the stateless `python_executor`.

## When to use

- Data exploration: load data once, then plot / aggregate repeatedly
- Multi-step training: load a model once, then run several inferences
- LLM agents needing multi-turn Python tool calls

## Prerequisites

- Docker daemon
- Host port 8888 available (the `jupyter-kernel-gateway` image is auto-built on first run)
- Install client deps: `pip install websocket-client requests`

## Basic example

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
        # First call: define a variable
        await sb.execute_tool('notebook_executor', {
            'code': 'x = [1, 2, 3, 4, 5]'
        })

        # Second call: x is still there
        res = await sb.execute_tool('notebook_executor', {
            'code': 'print(sum(x))'
        })
        print(res.output.strip())  # 15

        # Third call: imports persist too
        res = await sb.execute_tool('notebook_executor', {
            'code': 'import statistics; print(statistics.mean(x))'
        })
        print(res.output.strip())  # 3

asyncio.run(main())
```

## Configuration

`DockerNotebookConfig` extends `DockerSandboxConfig` with:

| Field | Default | Description |
|---|---|---|
| `image` | `jupyter-kernel-gateway` | Image name; auto-built if missing |
| `host` | `127.0.0.1` | Jupyter listen address |
| `port` | `8888` | Host-side port |
| `token` | `None` | Optional auth token |

> Because a WebSocket is required, `network_enabled` is forced to `True`, and `8888/tcp` is mapped automatically.

## Tool loading rule

`SandboxType.DOCKER_NOTEBOOK` **only** loads `notebook_executor`. Other Docker-specific tools (`python_executor` / `shell_executor` / `file_operation`) won't be enabled even if listed in `tools_config`. If you need shell/file capabilities too, use `DockerSandbox` + `python_executor` instead.

## Concurrency

Each Notebook sandbox occupies one port and one kernel. For concurrent use, create multiple instances with distinct ports:

```python
DockerNotebookConfig(port=8888, tools_config={'notebook_executor': {}})
DockerNotebookConfig(port=8889, tools_config={'notebook_executor': {}})
```

## Troubleshooting

- **`Jupyter Kernel Gateway failed to become ready within 30 seconds`**: usually a slow first-time image build. Retry after the build finishes, or pre-build an image tagged `jupyter-kernel-gateway`.
- **`websocket-client package is required`**: `pip install websocket-client`.
- **Port conflict**: change `port` to a free port.
