# 自定义 SandboxManager

## 必须实现（`SandboxManager` 抽象基类）

- 生命周期：`start()`, `stop()`
- 沙箱操作：`create_sandbox()`, `get_sandbox_info()`, `list_sandboxes()`, `stop_sandbox()`, `delete_sandbox()`
- 工具执行：`execute_tool()`, `get_sandbox_tools()`
- 统计：`get_stats()`
- 清理：`cleanup_all_sandboxes()`
- 池化（即使不用也是抽象方法，给最小实现即可）：`initialize_pool()`, `execute_tool_in_pool()`

注册类型前需要在 `ms_enclave/sandbox/model` 给 `SandboxManagerType` 加一个枚举值，如 `LOCAL_INMEM`。

## 最小示例：内存管理器

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

## 验证

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

## 工程化建议

- **持久化**：把 sandbox 元数据存到 SQLite / Redis，重启不丢失。
- **HTTP 暴露**：参照 `server/server.py` 与 `manager/http_manager.py`，保证 Pydantic 模型对齐。
- **调度策略**：可在 `execute_tool_in_pool` 之上引入优先级队列或按租户隔离。
