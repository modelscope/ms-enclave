# 5-Minute Quickstart

By the end of this page you'll have used `ms-enclave` to run a snippet of Python inside a Docker sandbox.

> Prerequisites: [installation](installation.md) done, Docker daemon running.

## Minimal example

Save the following as `hello_sandbox.py`:

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 1) Configure: pick an image, enable python_executor
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
    )

    # 2) async with auto-manages lifecycle (start → use → destroy container)
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print("hello from ms-enclave")'
        })
        print(result.output.strip())

asyncio.run(main())
```

Run:

```bash
python hello_sandbox.py
```

Expected output (first run will pull `python:3.11-slim`):

```text
hello from ms-enclave
```

## Key points

- **`tools_config` must declare each tool** — undeclared tools won't be registered and calls will fail.
- **`execute_tool(tool_name, parameters)`**: the first arg maps to a key in `tools_config`; the second is tool-specific (`python_executor` takes `code`).
- **`async with`**: on exit, the container is automatically stopped and removed — no leaks.

## Next

- Understand the `Sandbox` / `Manager` / `Tool` abstractions → [Core Concepts](concepts.md)
- See all available entry points → [Usage Guides Overview](../guides/index.md)
- Manage many sandboxes in one app → [Local Manager](../guides/local-manager.md)
- Let an LLM choose the tools → [LLM Agent integration](../guides/agent-integration.md)
