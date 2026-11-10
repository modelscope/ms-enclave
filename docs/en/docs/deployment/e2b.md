# E2B Remote Sandbox

Run Python and shell commands remotely using official E2B or a compatible Aliyun Agent Sandbox service, without local Docker. Files remain available across calls in the same sandbox. Each Python tool call starts a new process, so Python variables do not persist between calls.

## Install and prepare

Have your service's API key and an available template name ready, then install the dependencies:

```bash
pip install 'ms-enclave[e2b]'
export E2B_API_KEY='your-api-key'
```

The template needs a `python` command, plus `tar` for file uploads. Commands run as `user` in `/home/user` by default; make sure that user and directory exist in your template.

## Run your first task

Replace `your-template` with a template available in your service:

```python
import asyncio

from ms_enclave.sandbox.manager import E2BSandboxManager
from ms_enclave.sandbox.model import E2BSandboxConfig, SandboxType


async def main():
    config = E2BSandboxConfig(
        template='your-template',
        tools_config=['python_executor', 'shell_executor'],
        sandbox_timeout=300,
    )
    async with E2BSandboxManager() as manager:
        sid = await manager.create_sandbox(SandboxType.E2B, config)
        result = await manager.execute_tool(
            sid, 'python_executor', {'code': 'print(1 + 1)', 'timeout': 30}
        )
        if not result.success:
            raise RuntimeError(result.error)
        print(result.output)


asyncio.run(main())
```

The output is `2`. Leaving `async with` automatically cleans up the sandboxes created by this manager.

Here, `timeout=30` limits a single command, while `sandbox_timeout=300` limits the lifetime of the whole sandbox. Sandboxes are not automatically renewed: create a new one after expiry, and choose a lifetime allowed by your service plan.

## Connect to Aliyun or another compatible service

For Aliyun, also set the domain provided by your service console:

```bash
export E2B_DOMAIN='your-service-domain'
```

If the service provides a separate API address, set `E2B_API_URL` too. You can also configure the connection in code; explicit values override the corresponding environment variables:

```python
from ms_enclave.sandbox.model import E2BSandboxManagerConfig

connection = E2BSandboxManagerConfig(
    domain='your-service-domain',
    max_sandboxes=4,
)
```

Then replace `E2BSandboxManager()` in the first example with `E2BSandboxManager(connection)`. This configuration also accepts `api_key` and `api_url`. You usually do not need to set the build mode or image region manually.

## Use your own image

If you do not have a template, replace `template` with `image` to let the service build the environment:

```python
config = E2BSandboxConfig(
    image='your-registry/your-image:tag',
    tools_config=['python_executor', 'shell_executor'],
    sandbox_timeout=300,
)
```

The first run may take longer while the template is built; later runs reuse it. Set either `template` or `image`. If both are provided, `template` takes precedence.

Aliyun requires a converted image from `fc-e2b-registry.<region>.cr.aliyuncs.com/...`; Docker Hub images cannot be used directly. If you have a mapping from source images to converted images, pass it through `E2BSandboxManagerConfig.image_mapping`. Prepare image conversion and access to private registries in advance.

## Upload files and run commands

Inside the first example's `async with` block, get the sandbox and upload a local directory:

```python
sandbox = await manager.get_sandbox(sid)
if not await sandbox.put_dir('./data', '/home/user/data'):
    raise RuntimeError('File upload failed')

result = await sandbox.execute_command(
    ['ls', '/home/user/data'], timeout=30
)
print(result.stdout)
```

Use `put_file` for a text file or `put_archive` for a tar archive. Upload targets must be absolute, writable paths. Command parameters `user`, `cwd` and `env` let you override the execution user, directory and environment variables for a call.

E2B supports `python_executor` and `shell_executor`. Use another supported backend for `file_operation`, Notebook and multi-language tools. See [built-in tools](../guides/builtin-tools.md).

## Capacity and cleanup

- `max_sandboxes` defaults to 16 and limits sandboxes that are running or being created. Individual creation waits when the limit is reached. Use `stop_sandbox` or `delete_sandbox` to release sandboxes you no longer need.
- `stop_sandbox` terminates the remote sandbox and retains its local information, returning `True` on success. `delete_sandbox` also removes that local record. Remote files and processes are no longer retained after stopping or deletion.
- To use a [sandbox pool](../guides/sandbox-pool.md), call `initialize_pool`; the default type is E2B. Initialization fails if the requested pool exceeds available capacity. If some members fail to start, check the returned ID list for the actual number available.
- Call `await manager.delete_sandbox(sid)` to release one sandbox early. Otherwise, `async with` handles cleanup for the manager. Reusable templates are not deleted with sandboxes.

## Troubleshooting

| Problem | What to do |
|---|---|
| Missing API key or authentication failure | Check `E2B_API_KEY` and whether the key matches the service address. |
| Template or image build failure | Check the template name, image and access permissions; create a new manager after fixing them. |
| Command timed out or was cancelled | The backend attempts to terminate the command. If the sandbox is no longer usable, delete it and create a new one. |
| Stopping returns `False`, or deletion/manager shutdown raises an error | Restore the service connection, then retry `delete_sandbox` or `manager.stop()`. |

A remote sandbox may still be running after a network interruption. Use the sandbox ID and `run_id` from logs to inspect and clean up resources in the service console. A local task ending does not confirm remote cleanup.

See the [configuration API](../api/config.md) for more options and defaults.
