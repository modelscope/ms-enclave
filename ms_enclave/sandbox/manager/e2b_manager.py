"""E2B resource lifecycle using the standard local manager registry and tools."""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Set, Union

from ms_enclave.sandbox.boxes.e2b_connection import E2BConnection, require_e2b
from ms_enclave.sandbox.boxes.e2b_sandbox import E2BSandbox
from ms_enclave.sandbox.boxes.e2b_template import E2BTemplateResolver
from ms_enclave.sandbox.manager.base import register_manager
from ms_enclave.sandbox.manager.local_manager import LocalSandboxManager
from ms_enclave.sandbox.model import (
    E2BSandboxConfig,
    E2BSandboxManagerConfig,
    SandboxConfig,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxStatus,
    SandboxType,
)
from ms_enclave.utils import get_logger

logger = get_logger()


@register_manager(SandboxManagerType.E2B)
class E2BSandboxManager(LocalSandboxManager):
    """Limit live sandboxes and share template resolution within one run."""

    def __init__(self, config: Optional[Union[SandboxManagerConfig, Dict[str, Any]]] = None, **kwargs: Any) -> None:
        require_e2b()
        cfg = (
            config
            if isinstance(config, E2BSandboxManagerConfig)
            else E2BSandboxManagerConfig.model_validate(
                config.model_dump(exclude_unset=True) if isinstance(config, SandboxManagerConfig) else (config or {})
            )
        )
        super().__init__(cfg, **kwargs)
        self.config: E2BSandboxManagerConfig = cfg
        self.run_id = cfg.run_id or uuid.uuid4().hex[:12]
        self._conn = E2BConnection.from_config(cfg)
        self._templates = E2BTemplateResolver(self._conn, cfg.image_mapping, cfg.max_concurrent_builds)
        self._capacity_changed = asyncio.Condition()
        self._reservations: Set[str] = set()
        self._creating: Set[asyncio.Task] = set()

    async def stop(self) -> None:
        """Drain pending creates and retain failed deletions for a later retry."""
        pending = list(self._creating)
        for task in pending:
            if not task.cancelling():
                task.cancel()
        try:
            if self._running:
                await super().stop()
            else:
                await self.cleanup_all_sandboxes()
        finally:
            await asyncio.gather(*pending, return_exceptions=True)
        if self._sandboxes or self._reservations:
            raise RuntimeError(f'E2B cleanup incomplete; retry stop(): {list(self._sandboxes)}')

    async def start(self) -> None:
        """Start standard lifecycle management and log the run's cleanup identifier."""
        await super().start()
        logger.info(
            f'E2B manager started run_id={self.run_id} provider={self._conn.provider} '
            f'region={self._conn.region} build_mode={self._conn.build_mode}'
        )

    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict[str, Any]]] = None,
        sandbox_id: Optional[str] = None,
    ) -> str:
        """Resolve templates before reserving a live sandbox slot."""
        if sandbox_type != SandboxType.E2B:
            raise ValueError(f'E2BSandboxManager only supports SandboxType.E2B, got {sandbox_type}')
        if not self._running:
            raise RuntimeError('Sandbox manager not started')
        sandbox = self._new_sandbox(config, sandbox_id)
        task = asyncio.current_task()
        self._creating.add(task)
        try:
            async with self._sandbox_locks.setdefault(sandbox.id, asyncio.Lock()):
                if sandbox.id in self._sandboxes:
                    raise ValueError(f'Sandbox {sandbox.id} already exists')
                await self._templates.resolve(sandbox.config, run_id=self.run_id)
                await self._reserve_capacity([sandbox.id], wait=True)
                return await self._start_reserved(sandbox)
        finally:
            self._creating.discard(task)

    def _new_sandbox(
        self, config: Optional[Union[SandboxConfig, Dict[str, Any]]], sandbox_id: Optional[str] = None
    ) -> E2BSandbox:
        cfg = (
            config
            if isinstance(config, E2BSandboxConfig)
            else E2BSandboxConfig.model_validate(
                config.model_dump(exclude_unset=True) if isinstance(config, SandboxConfig) else (config or {})
            )
        )
        return E2BSandbox(cfg, sandbox_id, connection=self._conn, templates=self._templates, run_id=self.run_id)

    async def _reserve_capacity(self, sandbox_ids: List[str], *, wait: bool = False) -> None:
        """Reserve one create or an entire pool atomically, using IDs as owners."""
        async with self._capacity_changed:
            if wait:
                await self._capacity_changed.wait_for(
                    lambda: not self._running or len(self._reservations) + len(sandbox_ids) <= self.config.max_sandboxes
                )
            if not self._running:
                raise RuntimeError('Sandbox manager not started')
            if len(self._reservations) + len(sandbox_ids) > self.config.max_sandboxes:
                raise ValueError('Not enough E2B capacity for this pool; stop or delete existing sandboxes first')
            if len(set(sandbox_ids)) != len(sandbox_ids) or self._reservations.intersection(sandbox_ids):
                raise ValueError('Sandbox ID already reserved')
            self._reservations.update(sandbox_ids)

    async def _release_capacity(self, sandbox_ids: List[str]) -> None:
        async with self._capacity_changed:
            self._reservations.difference_update(sandbox_ids)
            self._capacity_changed.notify_all()

    async def _start_reserved(self, sandbox: E2BSandbox) -> str:
        """Keep failed-create ownership until remote cleanup is confirmed."""
        self._sandboxes[sandbox.id] = sandbox
        try:
            await sandbox.start()
        except BaseException:
            try:
                await sandbox.stop()
            except Exception as exc:
                logger.warning(self._conn.redact(f'E2B failed-create cleanup: {exc}'))
            if sandbox._sbx is None:
                del self._sandboxes[sandbox.id]
                await self._release_capacity([sandbox.id])
            raise
        return sandbox.id

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        """Release live capacity on confirmed stop, retaining the stopped record."""
        async with self._sandbox_locks.setdefault(sandbox_id, asyncio.Lock()):
            sandbox = self._sandboxes.get(sandbox_id)
            if sandbox is None:
                return False
            try:
                await sandbox.stop()
            except Exception as exc:
                logger.error(self._conn.redact(f'E2B sandbox {sandbox_id}: stop failed: {exc}'))
                return False
            await self._release_capacity([sandbox_id])
            return True

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Release registration and capacity only after confirmed deletion."""
        async with self._sandbox_locks.setdefault(sandbox_id, asyncio.Lock()):
            sandbox = self._sandboxes.get(sandbox_id)
            if sandbox is None:
                return False
            await sandbox.stop()
            del self._sandboxes[sandbox_id]
            await self._release_capacity([sandbox_id])
            return True

    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict[str, Any]]] = None,
    ) -> List[str]:
        """Reserve a whole pool before starting members; never wait for partial capacity."""
        if sandbox_type not in (None, SandboxType.E2B):
            raise ValueError(f'E2BSandboxManager only supports SandboxType.E2B, got {sandbox_type}')
        if not self._running:
            raise RuntimeError('Sandbox manager not started')
        size = self.config.pool_size if pool_size is None else pool_size
        if size <= 0:
            return []
        if size > self.config.max_sandboxes:
            raise ValueError(f'pool_size={size} exceeds E2B max_sandboxes={self.config.max_sandboxes}')
        task = asyncio.current_task()
        self._creating.add(task)
        try:
            async with self._pool_lock:
                sandboxes = [self._new_sandbox(config or self.config.sandbox_config) for _ in range(size)]
                await self._reserve_capacity([box.id for box in sandboxes])
                created_ids = []
                try:
                    await self._templates.resolve(sandboxes[0].config, run_id=self.run_id)
                    for sandbox in sandboxes:
                        try:
                            async with self._sandbox_locks.setdefault(sandbox.id, asyncio.Lock()):
                                await self._start_reserved(sandbox)
                                sandbox.update_status(SandboxStatus.IDLE)
                                self._sandbox_pool.append(sandbox.id)
                                created_ids.append(sandbox.id)
                        except Exception as exc:
                            logger.error(self._conn.redact(f'E2B pool member {sandbox.id}: create failed: {exc}'))
                finally:
                    await self._release_capacity([box.id for box in sandboxes if box.id not in self._sandboxes])
                    if created_ids:
                        self._pool_initialized = True
                return created_ids
        finally:
            self._creating.discard(task)

    async def get_stats(self) -> Dict[str, Any]:
        """Report the E2B manager type with the shared lifecycle statistics."""
        stats = await super().get_stats()
        stats['manager_type'] = SandboxManagerType.E2B.value
        return stats
