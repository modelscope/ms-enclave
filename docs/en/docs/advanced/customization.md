# Customization & Extensions

ms-enclave is highly modular and supports extending Tool, Sandbox, and SandboxManager. This guide covers required interfaces, registration, and minimal runnable examples to get you productive quickly.

## Registry Overview

A decorator-based registry enables type-driven creation:

- Sandbox:
  - Decorator: `@register_sandbox(SandboxType.XYZ)`
  - Factory: `SandboxFactory.create_sandbox(sandbox_type, config, sandbox_id)`

- Tool:
  - Decorator: `@register_tool('tool_name')`
  - Factory: `ToolFactory.create_tool('tool_name', **kwargs)`
  
- SandboxManager:
  - Decorator: `@register_manager(SandboxManagerType.XYZ)`
  - Factory: `SandboxManagerFactory.create_manager(manager_type, config, **kwargs)`

Tips:
- When adding a new Sandbox, extend `SandboxType` enum under `ms_enclave/sandbox/model` (e.g., `LOCAL_PROCESS`).
- When adding a new SandboxManager, extend `SandboxManagerType` (e.g., `LOCAL_INMEM`).

> All examples use English comments and full type hints to match project style.

---

## Custom Tool

Implement/override:
- `required_sandbox_type`: declare compatible sandbox type (return `None` for any).
- `async def execute(self, sandbox_context, **kwargs)`: implement tool logic and return `ToolResult`.
- Optional constructor args: `name/description/parameters/enabled/timeout`. If no params are needed, you may omit `parameters`.

Notes:
- The framework exposes an OpenAI-style function schema via `Tool.schema`. For strict validation, pass a Pydantic model via `parameters` (see `tools/tool_info.py`).
- Compatibility is checked by `Tool.is_compatible_with_sandbox` using `required_sandbox_type` plus `SandboxType.is_compatible`.

### Example A: Minimal tool (no sandbox command)

```python
from typing import Any, Dict, Optional
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.model import SandboxType

@register_tool('hello')
class HelloTool(Tool):
    def __init__(self, name: str = 'hello', description: str = 'Say hello', enabled: bool = True):
        super().__init__(name=name, description=description, enabled=enabled)

    @property
    def required_sandbox_type(self) -> Optional[SandboxType]:
        return None

    async def execute(self, sandbox_context: Any, name: str = 'world', **kwargs) -> Dict[str, Any]:
        return {'message': f'Hello, {name}!'}
```

Enable and run (Docker sandbox example):
```python
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, DockerSandboxConfig
import asyncio

async def main():
    sb = SandboxFactory.create_sandbox(SandboxType.DOCKER, DockerSandboxConfig(image='python:3.11-slim'))
    async with sb:
        await sb.initialize_tools()
        result = await sb.execute_tool('hello', {'name': 'ms-enclave'})
        print(result)

asyncio.run(main())
```

### Example B: Prefer in-sandbox command with local fallback

```python
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.model import SandboxType

@register_tool('time_teller')
class TimeTellerTool(Tool):
    def __init__(self, name: str = 'time_teller', description: str = 'Tell current time', enabled: bool = True):
        super().__init__(name=name, description=description, enabled=enabled)

    @property
    def required_sandbox_type(self) -> Optional[SandboxType]:
        return SandboxType.DOCKER

    async def execute(self, sandbox_context: Any, timezone_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        cmd = 'date'
        if timezone_name:
            cmd = f'TZ={timezone_name} date'
        try:
            exit_code, out, err = await sandbox_context.execute_command(cmd, timeout=5)
            if exit_code == 0:
                return {'time': out.strip()}
            return {'error': err.strip() or 'unknown error'}
        except Exception:
            tz = timezone.utc if (timezone_name or '').upper() == 'UTC' else None
            return {'time': datetime.now(tz=tz).isoformat()}
```

Enable via config:
```python
from ms_enclave.sandbox.model import DockerSandboxConfig

config = DockerSandboxConfig(
    image='debian:stable-slim',
    tools_config={
        'hello': {},
        'time_teller': {}
    }
)
```

---

## Custom Sandbox

Implement:
- `sandbox_type`
- `start()`, `stop()`, `cleanup()`
- `execute_command(command, timeout=None, stream=True)`
- `get_execution_context()`

Minimal demo: local process-based sandbox (for development/testing only). Assume you added `LOCAL_PROCESS` to `SandboxType`.

```python
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union
from ms_enclave.sandbox.boxes.base import Sandbox, register_sandbox
from ms_enclave.sandbox.model import SandboxType, SandboxStatus, SandboxConfig

CommandResult = Tuple[int, str, str]

@register_sandbox(SandboxType.LOCAL_PROCESS)
class LocalProcessSandbox(Sandbox):
    """Run host commands as a 'sandbox' (for demo/dev only)."""

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
        stream: bool = True
    ) -> CommandResult:
        if isinstance(command, list):
            shell_cmd = ' '.join(command)
        else:
            shell_cmd = command

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

Quick check:
```python
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, SandboxConfig
import asyncio

async def main():
    sb = SandboxFactory.create_sandbox(SandboxType.LOCAL_PROCESS, SandboxConfig())
    async with sb:
        await sb.initialize_tools()
        print(await sb.execute_tool('hello', {'name': 'sandbox'}))
        print(await sb.execute_command('echo hi'))

asyncio.run(main())
```

> Production sandboxes (e.g., Docker) must implement image pull, container create/start, limits, mounts, etc. See `ms_enclave/sandbox/boxes/docker_sandbox.py`.

---

## Custom SandboxManager

Implement (as defined in `SandboxManager` ABC):
- Lifecycle: `start()`, `stop()`
- Sandbox ops: `create_sandbox()`, `get_sandbox_info()`, `list_sandboxes()`, `stop_sandbox()`, `delete_sandbox()`
- Tool exec: `execute_tool()`, `get_sandbox_tools()`
- Stats: `get_stats()`
- Cleanup: `cleanup_all_sandboxes()`
- Pool (abstract; provide minimal implementation): `initialize_pool()`, `execute_tool_in_pool()`

Minimal runnable demo: in-memory manager. Assume you added `LOCAL_INMEM` to `SandboxManagerType`.

```python
import asyncio
from typing import Any, Dict, List, Optional, Union
from ms_enclave.sandbox.manager.base import SandboxManager, register_manager
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import (
    SandboxConfig, SandboxInfo, SandboxManagerConfig, SandboxManagerType,
    SandboxStatus, SandboxType, ToolResult
)

@register_manager(SandboxManagerType.LOCAL_INMEM)
class LocalInMemoryManager(SandboxManager):
    """A minimal in-memory manager for demo/dev."""

    def __init__(self, config: Optional[SandboxManagerConfig] = None, **kwargs):
        super().__init__(config=config, **kwargs)
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        await self.cleanup_all_sandboxes()
        self._running = False

    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None
    ) -> str:
        sb = SandboxFactory.create_sandbox(sandbox_type, config, sandbox_id)
        await sb.start()
        await sb.initialize_tools()
        self._sandboxes[sb.id] = sb
        async with self._pool_lock:
            self._sandbox_pool.append(sb.id)
        return sb.id

    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        sb = self._sandboxes.get(sandbox_id)
        return sb.get_info() if sb else None

    async def list_sandboxes(self, status_filter: Optional[SandboxStatus] = None) -> List[SandboxInfo]:
        infos = [sb.get_info() for sb in self._sandboxes.values()]
        if status_filter:
            return [i for i in infos if i.status == status_filter]
        return infos

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            return False
        await sb.stop()
        return True

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.pop(sandbox_id, None)
        if not sb:
            return False
        await sb.cleanup()
        async with self._pool_lock:
            try:
                self._sandbox_pool.remove(sandbox_id)
            except ValueError:
                pass
        return True

    async def execute_tool(self, sandbox_id: str, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            raise ValueError(f'Sandbox {sandbox_id} not found')
        if sb.status != SandboxStatus.RUNNING:
            raise ValueError('Sandbox not running')
        return await sb.execute_tool(tool_name, parameters)

    async def get_sandbox_tools(self, sandbox_id: str) -> Dict[str, Any]:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            raise ValueError(f'Sandbox {sandbox_id} not found')
        return sb.get_available_tools()

    async def get_stats(self) -> Dict[str, Any]:
        total = len(self._sandboxes)
        running = sum(1 for s in self._sandboxes.values() if s.status == SandboxStatus.RUNNING)
        return {'total': total, 'running': running}

    async def cleanup_all_sandboxes(self) -> None:
        for sb in list(self._sandboxes.values()):
            try:
                await sb.stop()
                await sb.cleanup()
            except Exception:
                pass
        self._sandboxes.clear()
        async with self._pool_lock:
            self._sandbox_pool.clear()

    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict]] = None
    ) -> List[str]:
        if self._pool_initialized:
            return list(self._sandbox_pool)
        size = pool_size or (self.config.pool_size if self.config else 0) or 0
        if size <= 0:
            self._pool_initialized = True
            return []
        st = sandbox_type or (self.config.sandbox_type if self.config else None)
        if not st:
            raise ValueError('sandbox_type required for pool initialization')
        ids: List[str] = []
        for _ in range(size):
            sb_id = await self.create_sandbox(st, config or (self.config.sandbox_config if self.config else None))
            ids.append(sb_id)
        self._pool_initialized = True
        return ids

    async def execute_tool_in_pool(
        self, tool_name: str, parameters: Dict[str, Any], timeout: Optional[float] = None
    ) -> ToolResult:
        async def acquire_one() -> str:
            start = asyncio.get_event_loop().time()
            while True:
                async with self._pool_lock:
                    if self._sandbox_pool:
                        return self._sandbox_pool.popleft()
                if timeout and (asyncio.get_event_loop().time() - start) > timeout:
                    raise TimeoutError('No sandbox available from pool')
                await asyncio.sleep(0.05)

        sandbox_id = await acquire_one()
        try:
            return await self.execute_tool(sandbox_id, tool_name, parameters)
        finally:
            async with self._pool_lock:
                if sandbox_id in self._sandboxes:
                    self._sandbox_pool.append(sandbox_id)
```

Verify:
```python
from ms_enclave.sandbox.manager.base import SandboxManagerFactory
from ms_enclave.sandbox.model import SandboxManagerType, SandboxType, DockerSandboxConfig
import asyncio

async def main():
    mgr = SandboxManagerFactory.create_manager(SandboxManagerType.LOCAL_INMEM)
    async with mgr:
        sb_id = await mgr.create_sandbox(SandboxType.DOCKER, DockerSandboxConfig(image='python:3.11-slim'))
        print(await mgr.get_sandbox_tools(sb_id))
        print(await mgr.execute_tool(sb_id, 'hello', {'name': 'manager'}))

asyncio.run(main())
```

---

## Best Practices

- Lifecycle & state:
  - Only execute tools when status is `SandboxStatus.RUNNING`.
  - Call `await self.initialize_tools()` in `start()`.
- Compatibility:
  - Tools should declare `required_sandbox_type`; return `None` if no restriction.
  - `SandboxType.is_compatible` enables subtypes to reuse parent tools (e.g., `DOCKER_NOTEBOOK` with `DOCKER`).
- Parameter schema:
  - Pass a Pydantic model via `parameters` for validation and documentation. Otherwise, `parameters` defaults to `{}`.
- Keep it simple:
  - Small functions, clear names, English comments, and docstrings.
- Validate fast:
  - Start from minimal (e.g., Example A/B) locally, then add pool/network/resources as needed.

> In practice: for a new Sandbox, refer to `ms_enclave/sandbox/boxes/docker_sandbox.py`. For HTTP API changes, update `server/server.py` and mirror in `manager/http_manager.py` with synchronized Pydantic models.
