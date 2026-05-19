# Custom SandboxManager

## Must implement (from the `SandboxManager` ABC)

- Lifecycle: `start()`, `stop()`
- Sandbox ops: `create_sandbox()`, `get_sandbox_info()`, `list_sandboxes()`, `stop_sandbox()`, `delete_sandbox()`
- Tool execution: `execute_tool()`, `get_sandbox_tools()`
- Stats: `get_stats()`
- Cleanup: `cleanup_all_sandboxes()`
- Pooling (abstract even if unused): `initialize_pool()`, `execute_tool_in_pool()` — give a minimal impl

Before registering a new type, add a value to `SandboxManagerType` in `ms_enclave/sandbox/model`, e.g. `LOCAL_INMEM`.

## Minimal example: in-memory manager

```python
import asyncio
from typing import Any, Dict, List, Optional, Union
from ms_enclave.sandbox.manager.base import SandboxManager, register_manager
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import (
    SandboxConfig, SandboxInfo, SandboxManagerConfig, SandboxManagerType,
    SandboxStatus, SandboxType, ToolResult,
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
        sandbox_id: Optional[str] = None,
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
        return [i for i in infos if i.status == status_filter] if status_filter else infos

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
        config: Optional[Union[SandboxConfig, Dict]] = None,
    ) -> List[str]:
        if self._pool_initialized:
            return list(self._sandbox_pool)
        size = pool_size or (self.config.pool_size if self.config else 0) or 0
        if size <= 0:
            self._pool_initialized = True
            return []
        if not sandbox_type:
            raise ValueError('sandbox_type required for pool initialization')
        ids = [await self.create_sandbox(sandbox_type, config) for _ in range(size)]
        self._pool_initialized = True
        return ids

    async def execute_tool_in_pool(
        self, tool_name: str, parameters: Dict[str, Any], timeout: Optional[float] = None,
    ) -> ToolResult:
        async def acquire() -> str:
            start = asyncio.get_event_loop().time()
            while True:
                async with self._pool_lock:
                    if self._sandbox_pool:
                        return self._sandbox_pool.popleft()
                if timeout and (asyncio.get_event_loop().time() - start) > timeout:
                    raise TimeoutError('No sandbox available from pool')
                await asyncio.sleep(0.05)

        sandbox_id = await acquire()
        try:
            return await self.execute_tool(sandbox_id, tool_name, parameters)
        finally:
            async with self._pool_lock:
                if sandbox_id in self._sandboxes:
                    self._sandbox_pool.append(sandbox_id)
```

## Verify

```python
import asyncio
from ms_enclave.sandbox.manager.base import SandboxManagerFactory
from ms_enclave.sandbox.model import SandboxManagerType, SandboxType, DockerSandboxConfig

async def main():
    mgr = SandboxManagerFactory.create_manager(SandboxManagerType.LOCAL_INMEM)
    async with mgr:
        sb_id = await mgr.create_sandbox(
            SandboxType.DOCKER,
            DockerSandboxConfig(image='python:3.11-slim', tools_config={'hello': {}}),
        )
        print(await mgr.execute_tool(sb_id, 'hello', {'name': 'manager'}))

asyncio.run(main())
```

## Production tips

- **Persistence**: store sandbox metadata in SQLite / Redis so restarts don't lose state.
- **HTTP exposure**: mirror `server/server.py` and `manager/http_manager.py`; keep Pydantic models in sync.
- **Scheduling**: layer priority queues or per-tenant isolation on top of `execute_tool_in_pool`.
