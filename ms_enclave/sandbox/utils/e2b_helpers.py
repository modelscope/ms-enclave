"""Endpoint and image rules for E2B-compatible services."""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal, Optional, Tuple
from urllib.parse import urlsplit

E2BProvider = Literal['e2b_official', 'aliyun']
BuildMode = Literal['micro', 'container']
TEMPLATE_NAME_PREFIX = 'ms-enclave'
TEMPLATE_NAME_MAX_LEN = 128
_ALIYUN_DOMAIN_SUFFIX = '.aliyuncs.com'
_ACR_HOST_PATTERN = re.compile(rf'^fc-e2b-registry\.(?P<region>[a-z0-9-]+)\.cr{re.escape(_ALIYUN_DOMAIN_SUFFIX)}/')
_REGION_LABEL = re.compile(r'[a-z]{2}-[a-z]+(?:-\d+)?')


@dataclass(frozen=True)
class E2BEndpoint:
    """Interpret connection hosts consistently for provider and region selection."""

    domain: Optional[str] = None
    api_url: Optional[str] = None

    @property
    def _aliyun_hosts(self) -> Tuple[str, ...]:
        hosts = (
            urlsplit(value if '://' in value else f'//{value}').hostname
            for value in (self.domain, self.api_url)
            if value
        )
        return tuple(host for host in hosts if host and host.endswith(_ALIYUN_DOMAIN_SUFFIX))

    @property
    def provider(self) -> E2BProvider:
        return 'aliyun' if self._aliyun_hosts else 'e2b_official'

    @property
    def region(self) -> Optional[str]:
        return next(
            (label for host in self._aliyun_hosts for label in host.split('.') if _REGION_LABEL.fullmatch(label)),
            None,
        )

    @property
    def default_build_mode(self) -> BuildMode:
        return 'micro' if self.provider == 'aliyun' else 'container'


def is_acr_image(image: str) -> bool:
    """Return whether the image uses the Agent Sandbox ACR registry."""
    return _ACR_HOST_PATTERN.match(image) is not None


def rewrite_acr_region(image: str, region: Optional[str]) -> str:
    """Replace only the region segment of an ACR registry host."""
    match = _ACR_HOST_PATTERN.match(image)
    if not region or match is None:
        return image
    start, end = match.span('region')
    return image[:start] + region + image[end:]


def normalize_image_ref(ref: str) -> str:
    """Add the implicit docker.io registry without changing repository paths."""
    ref = ref.strip()
    first, sep, _ = ref.partition('/')
    if sep and ('.' in first or ':' in first or first == 'localhost'):
        return ref
    return f'docker.io/{ref}'


def build_template_name(image: str, *, build_mode: BuildMode, cpu_count: int, memory_mb: int, disk_size_mb: int) -> str:
    """Build a deterministic template name including all build resource settings."""
    payload = '\n'.join([image, build_mode, str(cpu_count), str(memory_mb), str(disk_size_mb)])
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8]
    base = image.rsplit('/', 1)[-1].split('@', 1)[0].split(':', 1)[0]
    label = re.sub(r'[^a-z0-9_-]+', '-', base.lower()).strip('-') or 'image'
    budget = TEMPLATE_NAME_MAX_LEN - len(TEMPLATE_NAME_PREFIX) - len(digest) - 2
    return f'{TEMPLATE_NAME_PREFIX}-{label[:budget]}-{digest}'
