# Quickstart

`ms-enclave` offers two primary usage patterns to fit different integration needs:

1. SandboxFactory: create a sandbox instance directly — minimal overhead, ideal for scripts, tests, or one-off tasks.
2. SandboxManagerFactory: orchestrate sandboxes via a manager — suitable for services and background apps, with lifecycle management, pool prewarm, and auto-cleanup.

Both approaches are shown below.

## Option 1: Lightweight script

Create a sandbox instance and use `async with` to ensure cleanup on exit.

### When to use

- Single-run jobs and quick scripts
- Unit tests requiring a fresh, clean environment per case
- Small experiments
- Need direct access to low-level sandbox methods

### Example

Save as `quickstart_script.py`:

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 1) Configure sandbox and enable tools
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},
            'file_operation': {},
        }
    )

    print("Starting sandbox...")
    # 2) Create and start sandbox
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print(f"Sandbox ready ID: {sandbox.id}")

        # 3) Write a file
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/hello.txt',
            'content': 'Hello from ms-enclave!'
        })
        
        # 4) Execute Python code
        result = await sandbox.execute_tool('python_executor', {
            'code': """
print('Reading file...')
with open('/sandbox/hello.txt', 'r') as f:
    content = f.read()
print(f'Content: {content}')
"""
        })
        
        # 5) Check output
        print("Execution result:", result.output)

if __name__ == '__main__':
    asyncio.run(main())
```

### Notes

1. `SandboxFactory` returns an async context manager for the sandbox.
2. `DockerSandboxConfig`:
   - `image`: Docker image to ensure consistent environment.
   - `tools_config`: only tools explicitly enabled here can be used inside the sandbox.
3. `execute_tool(name, params)`: call tool by name with its parameters.
4. Lifecycle: `async with` guarantees `stop()` and container cleanup.

### Run

```bash
python quickstart_script.py
```

The first run may pull `python:3.11-slim`, which can take a while.

---

## Option 2: Application integration (Manager)

For web services or long-running apps, use a manager. It supports local mode and seamless switch to remote HTTP mode, plus pool prewarming.

### When to use

- Backend services serving concurrent requests
- Long-running processes with auto-cleanups
- Performance-sensitive scenarios (pool prewarming)
- Distributed deployments (remote HTTP server)

### Example

Save as `quickstart_app.py`:

```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType, SandboxManagerConfig, SandboxManagerType

async def main():
    # 1) Manager config
    manager_config = SandboxManagerConfig(cleanup_interval=600)

    print("Initializing manager...")
    # 2) Create local manager (or set base_url for HTTP mode)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, 
        config=manager_config
    ) as manager:
        
        # 3) Sandbox config
        sb_config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # 4) Create sandbox and get id
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, sb_config)
        print(f"Sandbox ID: {sandbox_id}")

        # 5) Execute a tool via manager
        result = await manager.execute_tool(
            sandbox_id, 
            'python_executor', 
            {'code': 'import sys; print(f"Python Version: {sys.version}")'}
        )
        print(f"Output:\n{result.output.strip()}")

        # 6) List sandboxes
        sandboxes = await manager.list_sandboxes()
        print(f"Active sandboxes: {len(sandboxes)}")

if __name__ == '__main__':
    asyncio.run(main())
```

### Notes

- `SandboxManagerFactory` creates a local or HTTP manager depending on `manager_type` or `base_url`.
- Manager API returns `sandbox_id` (string) instead of sandbox object.
- `LocalSandboxManager` includes a background cleaner for stale/errored sandboxes.

### Run

```bash
python quickstart_app.py
```
