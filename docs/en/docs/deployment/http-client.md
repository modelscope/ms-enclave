# HTTP Client (HttpSandboxManager)

`HttpSandboxManager` is the remote counterpart of `LocalSandboxManager`. It wraps REST calls to the [HTTP server](http-server.md). Its API is identical to the local manager — switching between local and remote is a one-line change.

## Basic usage

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as manager:
        sandbox_id = await manager.create_sandbox(
            SandboxType.DOCKER,
            DockerSandboxConfig(
                image='python:3.11-slim',
                tools_config={'python_executor': {}},
            ),
        )
        result = await manager.execute_tool(
            sandbox_id, 'python_executor',
            {'code': 'import platform; print(platform.node())'},
        )
        print(result.output.strip())
        await manager.delete_sandbox(sandbox_id)

asyncio.run(main())
```

## With auth

If the server has `api_key` enabled, the client must pass it:

```python
HttpSandboxManager(base_url='http://server:8000', api_key='your-secret-key')
```

## Unified factory: local vs. remote

`SandboxManagerFactory` switches based on whether `base_url` is provided:

```python
from ms_enclave.sandbox.manager import SandboxManagerFactory

# Local (dev)
async with SandboxManagerFactory.create_manager() as manager:
    ...

# Remote (production)
async with SandboxManagerFactory.create_manager(base_url='http://server:8000') as manager:
    ...
```

Business code stays the same; deployment mode can change freely.

## Timeouts & retries

`HttpSandboxManager` accepts a `timeout` argument (seconds, per HTTP request). For long-running tasks (large image pulls, container cold starts), increase it:

```python
HttpSandboxManager(base_url='...', timeout=120)
```

If image pulls on the server side are too slow, `docker pull` the image ahead of time.

## Notes

- The client doesn't know whether the server has a pool enabled. To use the pool, call `POST /pool/initialize` on the server first, then use `execute_tool_in_pool`.
- Retries are not built in; add your own (e.g. `tenacity`) for flaky networks.
