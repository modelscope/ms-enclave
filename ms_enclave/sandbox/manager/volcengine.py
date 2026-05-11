"""VolcEngine / SandboxFusion sandbox manager.

Wraps a SandboxFusion HTTP service (started manually by the user, e.g.
``docker run -it -p 8080:8080 vemlp-cn-beijing.cr.volces.com/preset-images/code-sandbox:server-20250609``)
and exposes it through the standard :class:`SandboxManager` interface.

Key design:

- **Shared HTTP session**: manager owns a single ``aiohttp.ClientSession`` and
  hands it to every :class:`VolcengineSandbox` it creates. The session is
  closed only when the manager stops.
- **Concurrency gate**: a global ``asyncio.Semaphore(max_concurrency)`` throttles
  concurrent ``/run_code`` requests across all sandboxes.
- **No real pool**: because the backend is stateless, a "pool" is logically a
  no-op; :meth:`initialize_pool` just ensures a default sandbox exists so that
  :meth:`execute_tool_in_pool` has somewhere to dispatch.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Dict, List, Optional, Union

import aiohttp

from ms_enclave.utils import get_logger

from ..boxes.volcengine import VolcengineSandbox
from ..model import (
    SandboxConfig,
    SandboxInfo,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxStatus,
    SandboxType,
    ToolResult,
    VolcengineSandboxConfig,
    VolcengineSandboxManagerConfig,
)
from .base import SandboxManager, register_manager

logger = get_logger()


@register_manager(SandboxManagerType.VOLCENGINE)
class VolcengineSandboxManager(SandboxManager):
    """Manager for VolcEngine/SandboxFusion stateless sandboxes."""

    def __init__(self, config: Optional[SandboxManagerConfig] = None, **kwargs):
        if config is None:
            raise ValueError(
                'VolcengineSandboxManager requires a VolcengineSandboxManagerConfig '
                '(with at least `base_url`).'
            )
        if not isinstance(config, VolcengineSandboxManagerConfig):
            # Best-effort upcast: build a VolcengineSandboxManagerConfig from the
            # fields of the provided config, so users that pass a plain dict or
            # base SandboxManagerConfig still work when a `base_url` is present.
            data = config.model_dump(exclude_none=True) if hasattr(config, 'model_dump') else dict(config)
            config = VolcengineSandboxManagerConfig(**data)

        super().__init__(config, **kwargs)
        self.config: VolcengineSandboxManagerConfig = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    # --------------------------------------------------------------------- #
    # Lifecycle                                                             #
    # --------------------------------------------------------------------- #
    async def start(self) -> None:
        if self._running:
            return

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        if self.config.api_key:
            headers['Authorization'] = self.config.api_key
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)

        self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self._running = True
        logger.info(
            f'VolcengineSandboxManager started (base_url={self.config.base_url}, '
            f'max_concurrency={self.config.max_concurrency})'
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False

        await self.cleanup_all_sandboxes()

        if self._session is not None:
            try:
                await self._session.close()
            except Exception as e:  # noqa: BLE001
                logger.warning(f'Error closing manager HTTP session: {e}')
            finally:
                self._session = None
        logger.info('VolcengineSandboxManager stopped')

    # --------------------------------------------------------------------- #
    # Sandbox CRUD                                                          #
    # --------------------------------------------------------------------- #
    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None,
    ) -> str:
        if sandbox_type != SandboxType.VOLCENGINE:
            raise ValueError(f'VolcengineSandboxManager only supports SandboxType.VOLCENGINE, got {sandbox_type}')

        # Normalize the sandbox-level config.
        if config is None:
            cfg = VolcengineSandboxConfig()
        elif isinstance(config, dict):
            cfg = VolcengineSandboxConfig(**config)
        elif isinstance(config, VolcengineSandboxConfig):
            cfg = config
        else:
            # Allow plain SandboxConfig by forwarding its fields.
            data = config.model_dump(exclude_none=True)
            cfg = VolcengineSandboxConfig(**data)

        try:
            sandbox = VolcengineSandbox(
                cfg,
                sandbox_id=sandbox_id,
                base_url=self.config.base_url,
                run_code_path=self.config.run_code_path,
                request_timeout=self.config.request_timeout,
                verify_ssl=self.config.verify_ssl,
                extra_headers=self.config.extra_headers,
                api_key=self.config.api_key,
                dataset_language_map=self.config.dataset_language_map,
                session=self._session,
            )
            await sandbox.start()
            self._sandboxes[sandbox.id] = sandbox
            logger.info(f'Created VolcEngine sandbox {sandbox.id}')
            return sandbox.id
        except Exception as e:
            logger.error(f'Failed to create VolcEngine sandbox: {e}')
            raise RuntimeError(f'Failed to create sandbox: {e}') from e

    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        sandbox = self._sandboxes.get(sandbox_id)
        return sandbox.get_info() if sandbox else None

    async def list_sandboxes(self, status_filter: Optional[SandboxStatus] = None) -> List[SandboxInfo]:
        result: List[SandboxInfo] = []
        for sandbox in self._sandboxes.values():
            info = sandbox.get_info()
            if status_filter is None or info.status == status_filter:
                result.append(info)
        return result

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False
        try:
            await sandbox.stop()
            return True
        except Exception as e:
            logger.error(f'Error stopping sandbox {sandbox_id}: {e}')
            return False

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            return False
        try:
            await sandbox.stop()
        except Exception as e:
            logger.warning(f'Error stopping sandbox {sandbox_id} during delete: {e}')
        self._sandboxes.pop(sandbox_id, None)
        # Remove from pool deque if present (rare path)
        try:
            self._sandbox_pool.remove(sandbox_id)  # type: ignore[arg-type]
        except ValueError:
            pass
        return True

    async def cleanup_all_sandboxes(self) -> None:
        ids = list(self._sandboxes.keys())
        for sid in ids:
            try:
                await self.delete_sandbox(sid)
            except Exception as e:  # noqa: BLE001
                logger.error(f'Error cleaning up sandbox {sid}: {e}')

    # --------------------------------------------------------------------- #
    # Tool execution                                                        #
    # --------------------------------------------------------------------- #
    async def execute_tool(self, sandbox_id: str, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f'Sandbox {sandbox_id} not found')
        if self._semaphore is None:
            raise RuntimeError('VolcengineSandboxManager is not started')

        async with self._semaphore:
            return await sandbox.execute_tool(tool_name, parameters)

    async def get_sandbox_tools(self, sandbox_id: str) -> Dict[str, Any]:
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f'Sandbox {sandbox_id} not found')
        return sandbox.get_available_tools()

    # --------------------------------------------------------------------- #
    # Stats                                                                 #
    # --------------------------------------------------------------------- #
    async def get_stats(self) -> Dict[str, Any]:
        status_counter: Counter = Counter()
        type_counter: Counter = Counter()
        for sandbox in self._sandboxes.values():
            status_counter[sandbox.status.value] += 1
            type_counter[sandbox.sandbox_type.value] += 1
        return {
            'manager_type': SandboxManagerType.VOLCENGINE.value,
            'base_url': self.config.base_url,
            'total_sandboxes': len(self._sandboxes),
            'status_counts': dict(status_counter),
            'sandbox_types': dict(type_counter),
            'running': self._running,
            'max_concurrency': self.config.max_concurrency,
            'pool_size': len(self._sandbox_pool),
            'pool_initialized': self._pool_initialized,
        }

    # --------------------------------------------------------------------- #
    # Pool (no-op, since the backend is stateless)                          #
    # --------------------------------------------------------------------- #
    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict]] = None,
    ) -> List[str]:
        """Mark the pool as initialized without spawning any extra sandboxes.

        SandboxFusion is stateless, so a real pool buys nothing. We simply
        ensure a default sandbox exists, register it in ``_sandbox_pool`` so
        it can be used by :meth:`execute_tool_in_pool`, and return its id.
        """
        _ = pool_size  # intentionally unused — kept for interface parity
        async with self._pool_lock:
            if not self._sandboxes:
                default_id = await self.create_sandbox(
                    sandbox_type or SandboxType.VOLCENGINE,
                    config or self.config.sandbox_config,
                )
                self._sandbox_pool.append(default_id)
            self._pool_initialized = True
        return list(self._sandboxes.keys())

    async def execute_tool_in_pool(
        self, tool_name: str, parameters: Dict[str, Any], timeout: Optional[float] = None
    ) -> ToolResult:
        """Dispatch the tool on any existing sandbox (creating one if missing)."""
        _ = timeout  # the semaphore + HTTP timeout already bound wait time
        if not self._sandboxes:
            await self.initialize_pool()
        # Any sandbox works — pick the first one.
        sandbox_id = next(iter(self._sandboxes))
        return await self.execute_tool(sandbox_id, tool_name, parameters)
