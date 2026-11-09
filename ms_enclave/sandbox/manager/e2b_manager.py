"""E2B resource lifecycle using the standard local manager registry and tools."""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Union

from ms_enclave.utils import get_logger

from ..boxes.e2b_connection import E2BConnection, require_e2b
from ..boxes.e2b_sandbox import E2BSandbox
from ..boxes.e2b_template import E2BTemplateResolver
from ..model import (
    E2BSandboxConfig,
    E2BSandboxManagerConfig,
    SandboxConfig,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxType,
)
from .base import register_manager
from .local_manager import LocalSandboxManager

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
        self._slots = asyncio.Semaphore(cfg.max_sandboxes)

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
        cfg = (
            config
            if isinstance(config, E2BSandboxConfig)
            else E2BSandboxConfig.model_validate(
                config.model_dump(exclude_unset=True) if isinstance(config, SandboxConfig) else (config or {})
            )
        )
        await self._templates.resolve(cfg, run_id=self.run_id)
        await self._slots.acquire()
        sandbox = E2BSandbox(cfg, sandbox_id, connection=self._conn, templates=self._templates, run_id=self.run_id)
        try:
            await sandbox.start()
        except BaseException:
            self._slots.release()
            raise
        self._sandboxes[sandbox.id] = sandbox
        return sandbox.id

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Remove registration before kill so concurrent deletes are idempotent."""
        sandbox = self._sandboxes.pop(sandbox_id, None)
        if sandbox is None:
            return False
        try:
            await sandbox.stop()
        finally:
            self._sandbox_locks.pop(sandbox_id, None)
            self._slots.release()
        return True

    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict[str, Any]]] = None,
    ) -> List[str]:
        """Reject pools that cannot fit within the live sandbox limit."""
        size = pool_size or self.config.pool_size
        if size > self.config.max_sandboxes:
            raise ValueError(f'pool_size={size} exceeds E2B max_sandboxes={self.config.max_sandboxes}')
        return await super().initialize_pool(pool_size, sandbox_type or SandboxType.E2B, config)
