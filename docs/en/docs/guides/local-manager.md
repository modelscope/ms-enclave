# Local Manager (LocalSandboxManager)

`LocalSandboxManager` manages multiple sandboxes inside a single process. It provides:

- References by `sandbox_id` string (useful for passing across requests in a web service)
- Background cleanup of stale / errored sandboxes
- The same interface as `HttpSandboxManager` — switching between local and remote requires no business-code change

## When to use

- Web service backends maintaining one sandbox per user / session
- Long-running processes that must not leak Docker containers
- Task schedulers that need to query / stop sandboxes by ID

## Basic example

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType, SandboxManagerConfig

async def main():
    # Sweep expired sandboxes every 10 minutes
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

        sandboxes = await manager.list_sandboxes()
        print(f'Active: {len(sandboxes)}')

asyncio.run(main())
```

## Common API

| Method | Description |
|---|---|
| `create_sandbox(type, config)` | Create and start a sandbox; returns `sandbox_id` |
| `execute_tool(id, tool_name, params)` | Execute a tool in the named sandbox |
| `get_sandbox_info(id)` | Query a single sandbox (status etc.) |
| `list_sandboxes(status=None)` | List sandboxes, optionally filtered by status |
| `get_sandbox_tools(id)` | Get the OpenAI-style schema of enabled tools |
| `stop_sandbox(id)` / `delete_sandbox(id)` | Explicit stop / delete |
| `get_stats()` | Return totals, running counts, etc. |

## Background cleanup

Once started, `LocalSandboxManager` runs a background cleanup coroutine on `cleanup_interval`:

- Sandboxes in `RUNNING` for more than 48h are reclaimed
- Sandboxes in `STOPPED` / `ERROR` for more than 1h are reclaimed

You can also call `cleanup_all_sandboxes()` to force a sweep.

## When not to use

- Sandboxes scheduled across multiple machines → use [`HttpSandboxManager`](../deployment/http-client.md)
- Need to warm up & reuse sandboxes → see [Sandbox pool](sandbox-pool.md)
- Just running a one-off script → [`SandboxFactory`](sandbox-factory.md) is simpler
