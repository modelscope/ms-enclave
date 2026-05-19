# Installing Third-Party Dependencies in a Sandbox

A sandbox only ships with the packages from the base image. To install extras (e.g. `numpy`, `pandas`), the simplest path is: write a `requirements.txt` via `file_operation`, then `pip install` via `shell_executor`.

## Example

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},
            'file_operation': {},
            'shell_executor': {},
        },
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 1) Write requirements.txt
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/requirements.txt',
            'content': 'numpy\npandas\n',
        })

        # 2) pip install
        install = await sandbox.execute_command(
            'pip install -r /sandbox/requirements.txt'
        )
        assert install.exit_code == 0, install.stderr

        # 3) Verify
        check = await sandbox.execute_tool('python_executor', {
            'code': 'import numpy, pandas; print(numpy.__version__, pandas.__version__)',
        })
        print(check.output.strip())

asyncio.run(main())
```

## Performance optimization

Reinstalling deps on every new sandbox is slow. Two production-friendly options:

### Option 1: Custom base image (recommended)

Pre-bake the image and reference it via `image`:

```dockerfile
# Dockerfile
FROM python:3.11-slim
RUN pip install numpy pandas
```

```bash
docker build -t my-runtime:1.0 .
```

```python
config = DockerSandboxConfig(image='my-runtime:1.0', ...)
```

Startup time drops significantly, and the image plays nicely with [sandbox pools](sandbox-pool.md).

### Option 2: Mount a shared pip cache

```python
config = DockerSandboxConfig(
    image='python:3.11-slim',
    volumes={
        '/home/me/.cache/pip': {'bind': '/root/.cache/pip', 'mode': 'rw'},
    },
    ...
)
```

Subsequent installs hit the local wheel cache and skip downloads.

## Offline environments

When the sandbox has no internet access, `pip download` wheels on the host, then [mount the host directory](host-volumes.md) and run `pip install --no-index --find-links /sandbox/wheels` inside the sandbox.
