"""Pure image, endpoint and secret handling for E2B-compatible services."""

import hashlib
import re
from typing import Literal, Optional
from urllib.parse import urlparse

E2BProvider = Literal['e2b_official', 'aliyun']
BuildMode = Literal['micro', 'container']
TEMPLATE_NAME_PREFIX = 'evalscope'
TEMPLATE_NAME_MAX_LEN = 128
ACR_HOST_PATTERN = re.compile(r'^fc-e2b-registry\.(?P<region>[a-z0-9-]+)\.cr\.aliyuncs\.com/')
_REGION_LABEL = re.compile(r'[a-z]{2}-[a-z]+(?:-\d+)?')
REDACTED = '***'


def detect_provider(domain: Optional[str], api_url: Optional[str]) -> E2BProvider:
    """Identify Aliyun endpoints by their host suffix."""
    hosts = (domain or '', (urlparse(api_url).hostname or '') if api_url else '')
    return 'aliyun' if any(h.lower().endswith('.aliyuncs.com') for h in hosts) else 'e2b_official'


def infer_region(domain: Optional[str], api_url: Optional[str]) -> Optional[str]:
    """Find a region DNS label in a new or legacy Aliyun endpoint."""
    for host in (domain, urlparse(api_url).hostname if api_url else None):
        if host and host.lower().endswith('.aliyuncs.com'):
            for label in host.lower().split('.'):
                if _REGION_LABEL.fullmatch(label):
                    return label
    return None


def is_acr_image(image: str) -> bool:
    """Return whether the image uses the Agent Sandbox ACR registry."""
    return ACR_HOST_PATTERN.match(image) is not None


def rewrite_acr_region(image: str, region: Optional[str]) -> str:
    """Replace only the region segment of an ACR registry host."""
    if not region:
        return image
    return ACR_HOST_PATTERN.sub(f'fc-e2b-registry.{region}.cr.aliyuncs.com/', image, count=1)


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


def redact(text: str, secret: Optional[str]) -> str:
    """Mask every occurrence of a nonempty secret."""
    return text.replace(secret, REDACTED) if secret else text
