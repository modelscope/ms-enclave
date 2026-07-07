# Sandbox Pool

Container cold-start usually takes hundreds of milliseconds to several seconds. For high-concurrency services, pre-warming a pool of sandboxes can drastically reduce per-call latency.

## How it works

`LocalSandboxManager` has a built-in FIFO pool:

1. `initialize_pool(pool_size, ...)` pre-creates and starts the given number of sandboxes
2. `execute_tool_in_pool(...)` borrows an idle sandbox, runs the tool, then returns it to the pool
3. When the pool is empty, callers wait up to `timeout` for a free sandbox

## Full example

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

        # Pre-warm 2 sandboxes
        await manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config,
        )

        # Borrow and auto-return
        result = await manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("from pool")'},
            timeout=30,  # wait timeout for an idle sandbox
        )
        print(result.output.strip())

        print(await manager.get_stats())

asyncio.run(main())
```

## Tuning tips

- **Pool size**: estimate from peak concurrency. Roughly "expected QPS × average execution seconds", rounded up.
- **Image**: pool warm-up pulls + starts the image. Build a slim, custom image for production.
- **Behavior when the pool is exhausted**: `timeout=None` waits forever; a positive number raises `TimeoutError` on timeout. Web services should always set a reasonable timeout.
- **Side effects across reuses**: the same sandbox may be lent out repeatedly. If your tool mutates the filesystem or env vars, clean up at the end of each execution, or use one-shot `SandboxFactory` instead.

## Server-side pool

The HTTP server also exposes pool endpoints (`POST /pool/initialize`, `POST /pool/execute`). See [HTTP server](../deployment/http-server.md).
