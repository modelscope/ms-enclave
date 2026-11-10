"""Resolve and build reusable E2B templates from container images."""

import asyncio
import time
from typing import Dict, Literal, Mapping, Optional, Set

from pydantic import BaseModel, ConfigDict

from ms_enclave.sandbox.boxes.e2b_connection import E2BConnection, E2BError, retry_dispatch
from ms_enclave.sandbox.model import E2BSandboxConfig
from ms_enclave.sandbox.utils.e2b_helpers import (
    build_template_name,
    is_acr_image,
    normalize_image_ref,
    rewrite_acr_region,
)
from ms_enclave.utils import get_logger

logger = get_logger()
TemplateSource = Literal['explicit', 'reused', 'built', 'rebuilt']
_POLL_INTERVAL_S = 10.0
_POLL_TIMEOUT_S = 3600.0
_BUSY = {'building', 'waiting'}


class E2BTemplateError(E2BError):
    """A remote template could not be resolved or built."""


class _RemoteTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    template_id: str
    status: Literal['building', 'waiting', 'ready', 'error']


class E2BTemplateResolver:
    """Share in-flight builds and cache terminal outcomes within one manager."""

    def __init__(self, connection: E2BConnection, image_mapping: Mapping[str, str], max_concurrent_builds: int) -> None:
        self._conn = connection
        self._mapping = {normalize_image_ref(k): v for k, v in image_mapping.items()}
        self._build_slots = asyncio.Semaphore(max_concurrent_builds)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._ready: Set[str] = set()
        self._failed: Dict[str, str] = {}

    async def resolve(self, config: E2BSandboxConfig, *, run_id: str) -> str:
        """Prefer an explicit template, otherwise reuse or build the resolved image."""
        if config.template:
            logger.info(f'E2B template {config.template} source=explicit run_id={run_id}')
            return config.template
        if not config.image:
            raise ValueError('E2B sandbox config requires either `template` or `image`.')
        image = self.final_image(config.image)
        name = build_template_name(
            image,
            build_mode=self._conn.build_mode,
            cpu_count=config.cpu_count,
            memory_mb=config.memory_mb,
            disk_size_mb=config.disk_size_mb,
        )
        async with self._locks.setdefault(name, asyncio.Lock()):
            if name in self._ready:
                return name
            if name in self._failed:
                raise E2BTemplateError(self._failed[name])
            started = time.monotonic()
            try:
                source = await self._ensure(name, image, config, run_id=run_id)
            except Exception as exc:
                error = E2BTemplateError.from_exception(
                    f'resolve template {name!r} from image {image!r}', exc, run_id=run_id
                )
                self._failed[name] = str(error)
                raise error from None
            self._ready.add(name)
            logger.info(
                f'E2B template {name} source={source} image={config.image} -> {image} '
                f'build_mode={self._conn.build_mode} elapsed={time.monotonic() - started:.1f}s run_id={run_id}'
            )
        return name

    def final_image(self, image: str) -> str:
        """Map official images on Aliyun and rewrite only an ACR registry region."""
        if self._conn.provider == 'aliyun' and not is_acr_image(image):
            mapped = self._mapping.get(normalize_image_ref(image))
            if mapped is None:
                raise E2BTemplateError(
                    f'No converted ACR image for {image!r}; Aliyun Agent Sandbox cannot build templates from '
                    'docker.io images. Add it to E2BSandboxManagerConfig.image_mapping or set E2BSandboxConfig.template.'
                )
            image = mapped
        return rewrite_acr_region(image, self._conn.region)

    async def _ensure(self, name: str, image: str, config: E2BSandboxConfig, *, run_id: str) -> TemplateSource:
        remote = await self._find(name, run_id=run_id)
        if remote is not None and remote.status in _BUSY:
            remote = await self._wait(name, run_id=run_id)
        if remote is not None and remote.status == 'ready':
            return 'reused'
        source: TemplateSource = 'built'
        if remote is not None and remote.status == 'error':
            await self._delete(remote.template_id)
            source = 'rebuilt'
        async with self._build_slots:
            await self._build(name, image, config, run_id=run_id)
            remote = await self._wait(name, run_id=run_id)
        if remote is None or remote.status != 'ready':
            raise E2BTemplateError(f'template {name!r} finished with status {remote.status if remote else "missing"}')
        return source

    async def _find(self, name: str, *, run_id: str) -> Optional[_RemoteTemplate]:
        async def fetch() -> Optional[_RemoteTemplate]:
            # Read raw JSON: compatible providers may omit generated-model fields.
            async with self._conn.api_client() as client:
                response = await client.get_async_httpx_client().get('/templates')
                response.raise_for_status()
                for item in response.json():
                    names = (item.get('aliases') or []) + (item.get('names') or [])
                    if any(n == name or n.endswith(f'/{name}') for n in names):
                        return _RemoteTemplate(template_id=item['templateID'], status=item['buildStatus'])
            return None

        return await retry_dispatch('template status', fetch, run_id=run_id)

    async def _delete(self, template_id: str) -> None:
        async with self._conn.api_client() as client:
            response = await client.get_async_httpx_client().delete(f'/templates/{template_id}')
            response.raise_for_status()

    async def _build(self, name: str, image: str, config: E2BSandboxConfig, *, run_id: str) -> None:
        from e2b import AsyncTemplate

        headers = {}
        if self._conn.build_mode == 'micro':
            headers = {'X-E2B-Template-Build-Mode': 'micro', 'X-E2B-Template-Alpha-Disk-Size': str(config.disk_size_mb)}
        await retry_dispatch(
            'template build',
            lambda: AsyncTemplate.build_in_background(
                AsyncTemplate().from_image(image),
                name,
                cpu_count=config.cpu_count,
                memory_mb=config.memory_mb,
                **self._conn.api_params(retries=0, api_headers=headers),
            ),
            run_id=run_id,
        )

    async def _wait(self, name: str, *, run_id: str) -> Optional[_RemoteTemplate]:
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while True:
            remote = await self._find(name, run_id=run_id)
            if remote is not None and remote.status not in _BUSY:
                return remote
            if time.monotonic() >= deadline:
                status = remote.status if remote is not None else 'missing'
                raise E2BTemplateError(f'Timed out waiting for E2B template {name!r}; last status={status}')
            await asyncio.sleep(_POLL_INTERVAL_S)
