# Custom Sandbox

## Must implement

- `sandbox_type`: returns the corresponding `SandboxType` enum value.
- `async def start(self)`: start the sandbox and set `status` to `RUNNING`; call `await self.initialize_tools()` at the end.
- `async def stop(self)`: stop the sandbox and set `status` to `STOPPED`.
- `async def cleanup(self)`: release resources (delete container, reclaim network, …).
- `async def execute_command(self, command, timeout=None, stream=True)`: run a command inside the sandbox. Implementations that don't support this may raise `NotImplementedError`.
- `async def get_execution_context(self)`: return an execution context for tools (container/process handle, etc.); return `None` if not applicable.

For a new sandbox type, usually extend the `SandboxType` enum first (e.g. add `LOCAL_PROCESS`).

## Full example: local-process sandbox (demo only)

> ⚠️ Running commands directly on the host gives no isolation. **Not for production.** This only illustrates which methods you need.

```python
import asyncio
from typing import Any, List, Optional, Tuple, Union
from ms_enclave.sandbox.boxes.base import Sandbox, register_sandbox
from ms_enclave.sandbox.model import SandboxType, SandboxStatus

CommandResult = Tuple[int, str, str]

@register_sandbox(SandboxType.LOCAL_PROCESS)  # extend the enum first
class LocalProcessSandbox(Sandbox):
    """Run host commands as a 'sandbox' (demo only)."""

    @property
    def sandbox_type(self) -> SandboxType:
        return SandboxType.LOCAL_PROCESS

    async def start(self) -> None:
        self.update_status(SandboxStatus.RUNNING)
        await self.initialize_tools()

    async def stop(self) -> None:
        self.update_status(SandboxStatus.STOPPED)

    async def cleanup(self) -> None:
        return

    async def execute_command(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        stream: bool = True,
    ) -> CommandResult:
        shell_cmd = ' '.join(command) if isinstance(command, list) else command
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            if timeout:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            else:
                stdout, stderr = await proc.communicate()
        except asyncio.TimeoutError:
            proc.kill()
            return 124, '', 'command timed out'
        return proc.returncode, (stdout or b'').decode(), (stderr or b'').decode()

    async def get_execution_context(self) -> Any:
        return None
```

## Quick verification

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, SandboxConfig

async def main():
    sb = SandboxFactory.create_sandbox(SandboxType.LOCAL_PROCESS, SandboxConfig())
    async with sb:
        await sb.initialize_tools()
        print(await sb.execute_tool('hello', {'name': 'sandbox'}))
        print(await sb.execute_command('echo hi'))

asyncio.run(main())
```

## Production considerations

Real sandboxes typically need to:

- **Provision images / resources**: pull images, check socket permissions, apply resource limits.
- **Robust state machine**: set `status` to `ERROR` and record `metadata['error']` on every failure path.
- **Observability**: log container id, PID, key events; surface them via `get_info()`.
- **Concurrency safety**: `execute_command` may be called concurrently — add locks if needed.

Reference implementation: [`ms_enclave/sandbox/boxes/docker_sandbox.py`](https://github.com/modelscope/ms-enclave/blob/main/ms_enclave/sandbox/boxes/docker_sandbox.py).
