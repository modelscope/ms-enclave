# Using a Sandbox Directly (SandboxFactory)

`SandboxFactory` is the lightest entry point. It creates a sandbox instance and leaves lifecycle to the caller. Use it for:

- One-off scripts
- Unit tests (a clean environment per case)
- Quick experiments or fine-grained control over low-level APIs

## Recommended: `async with`

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

Exiting the `async with` block automatically stops and removes the Docker container.

## Key points

1. **Tools must be declared in `tools_config`.** Even registered tools won't load otherwise.
2. `execute_tool(tool_name, parameters)` is the primary way to interact with a sandbox. `tool_name` must match a key in `tools_config`.
3. The return value is a `ToolResult` with `status`, `output`, `error` fields.

## Manual lifecycle

If your flow spans multiple async contexts (e.g., long-lived connections), control `start/stop` explicitly:

```python
async def manual_lifecycle():
    config = DockerSandboxConfig(tools_config={'shell_executor': {}})
    sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)
    try:
        await sandbox.start()
        result = await sandbox.execute_tool('shell_executor', {'command': 'echo hi'})
        print(result.output.strip())
    finally:
        await sandbox.stop()  # always release in finally
```

> **Warning**: forgetting `stop()` leaks Docker containers. Prefer `LocalSandboxManager` in production — it ships with background cleanup.
