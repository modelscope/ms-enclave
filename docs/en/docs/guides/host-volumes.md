# Mounting Host Directories

Use Docker volumes to let the sandbox read / write host files. Common use cases:

- Feed large input files to the sandbox
- Persist sandbox artifacts (charts, reports, models) back to the host
- Share read-only data across multiple sandboxes

## Syntax

`DockerSandboxConfig.volumes` accepts a dict:

```python
volumes = {
    '/host/path': {
        'bind': '/container/path',
        'mode': 'rw',   # or 'ro' for read-only
    },
}
```

`/host/path` must be an **absolute** path on the host.

## Example: read & write

```python
import asyncio
import os
import shutil
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    host_dir = os.path.abspath('./sandbox_data')
    os.makedirs(host_dir, exist_ok=True)
    with open(os.path.join(host_dir, 'host.txt'), 'w') as f:
        f.write('hello from host')

    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'shell_executor': {}},
        volumes={host_dir: {'bind': '/sandbox/data', 'mode': 'rw'}},
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sb:
        # Read
        res = await sb.execute_tool('shell_executor', {
            'command': 'cat /sandbox/data/host.txt',
        })
        print(res.output.strip())  # hello from host

        # Write
        await sb.execute_tool('shell_executor', {
            'command': 'echo "from sandbox" > /sandbox/data/sandbox.txt',
        })

    with open(os.path.join(host_dir, 'sandbox.txt')) as f:
        print(f.read().strip())  # from sandbox

    shutil.rmtree(host_dir)

asyncio.run(main())
```

## Common patterns

### 1. Read-only inputs

Mount a dataset as read-only to prevent accidental writes:

```python
volumes={'/data/datasets/squad': {'bind': '/sandbox/input', 'mode': 'ro'}}
```

### 2. Collect artifacts

Use a fixed `output/` directory to gather files generated inside the sandbox:

```python
volumes={os.path.abspath('./output'): {'bind': '/sandbox/output', 'mode': 'rw'}}
```

### 3. Share pip / Hugging Face caches

Avoid repeated downloads:

```python
volumes={
    os.path.expanduser('~/.cache/huggingface'): {'bind': '/root/.cache/huggingface', 'mode': 'rw'},
}
```

## Security note

Mounting exposes host permissions to code running inside the sandbox. In production:

- Prefer `ro` mode
- Don't mount sensitive paths (`/etc`, `/home`, SSH key directories)
- Combine with `network_enabled=False` to disable network access when possible
