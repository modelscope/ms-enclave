# Volcengine Cloud Sandbox (SandboxFusion)

`ms-enclave` supports [Volcengine SandboxFusion](https://www.volcengine.com/) — a stateless sandbox exposed as an HTTP service. Unlike the Docker sandbox, code is submitted to the remote `/run_code` endpoint, so no local Docker daemon is required.

## When to use

- You don't want to maintain a local Docker daemon
- You need quick multi-language execution (python / cpp / go / rust / java / nodejs …)
- High-concurrency scenarios that benefit from a remote cluster

## Prerequisite: start SandboxFusion

The official preset image runs out of the box:

```bash
docker run -it -p 8080:8080 \
  vemlp-cn-beijing.cr.volces.com/preset-images/code-sandbox:server-20250609
```

It listens on `http://localhost:8080` by default.

## Using through the manager (recommended)

```python
import asyncio
from ms_enclave.sandbox.manager import VolcengineSandboxManager
from ms_enclave.sandbox.model import (
    SandboxType, VolcengineSandboxConfig, VolcengineSandboxManagerConfig,
)

async def main():
    manager_config = VolcengineSandboxManagerConfig(
        base_url='http://localhost:8080',
        max_concurrency=4,
        request_timeout=30.0,
    )
    sandbox_config = VolcengineSandboxConfig(
        tools_config=['python_executor', 'shell_executor', 'multi_code_executor'],
    )

    async with VolcengineSandboxManager(config=manager_config) as manager:
        sandbox_id = await manager.create_sandbox(SandboxType.VOLCENGINE, sandbox_config)

        # 1) Python
        r = await manager.execute_tool(sandbox_id, 'python_executor', {
            'code': 'print("hello from python:", 1 + 2)',
        })
        print(r.output)

        # 2) Shell
        r = await manager.execute_tool(sandbox_id, 'shell_executor', {
            'command': 'echo hello && uname -a',
        })
        print(r.output)

        # 3) Multi-language: C++
        cpp = (
            '#include <iostream>\n'
            'int main() { std::cout << "hi from c++"; return 0; }\n'
        )
        r = await manager.execute_tool(sandbox_id, 'multi_code_executor', {
            'language': 'cpp',
            'code': cpp,
        })
        print(r.output)

asyncio.run(main())
```

## Using through SandboxFactory

For one-off scripts you can use the factory directly and put `base_url` on `VolcengineSandboxConfig`:

```python
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, VolcengineSandboxConfig

config = VolcengineSandboxConfig(
    base_url='http://localhost:8080',
    tools_config=['python_executor'],
)
async with SandboxFactory.create_sandbox(SandboxType.VOLCENGINE, config) as sb:
    res = await sb.execute_tool('python_executor', {'code': 'print(42)'})
    print(res.output)
```

## Key configuration

`VolcengineSandboxManagerConfig`:

| Field | Default | Description |
|---|---|---|
| `base_url` | Required | SandboxFusion service URL |
| `api_key` | None | Optional `Authorization` header |
| `request_timeout` | 30.0 | Per-request timeout (seconds) |
| `verify_ssl` | True | Verify SSL certs |
| `run_code_path` | `/run_code` | Endpoint path |
| `max_concurrency` | 16 | Max concurrent requests per manager |
| `extra_headers` | None | Custom HTTP headers |
| `dataset_language_map` | None | Language renames, e.g. `{"r": "R"}` |

## Differences vs. Docker sandbox

| Feature | DOCKER | VOLCENGINE |
|---|---|---|
| Needs local Docker | ✅ | ❌ |
| State persistence | While the container lives | **Stateless**, each call is independent |
| File operations | `file_operation` supported | Only code execution |
| Multi-language | Requires `multi_code_executor` + specific image | Native |
| Resource limits | CPU/memory/network controllable | Decided by the remote service |

> Because the Volcengine sandbox is stateless, **don't rely on variables, files, or imports persisting across calls**.
