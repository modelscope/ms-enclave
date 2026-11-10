"""Property checks for image identity and endpoint handling."""

import hashlib
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from ms_enclave.sandbox.model import E2BSandboxManagerConfig
from ms_enclave.sandbox.utils.e2b_helpers import (
    E2BEndpoint,
    build_template_name,
    normalize_image_ref,
    rewrite_acr_region,
)

regions = st.from_regex(r'[a-z]{2}-[a-z]{1,12}(-[0-9]{1,2})?', fullmatch=True)
text = st.text(alphabet=st.characters(blacklist_categories=('Cs',)))


# Feature: e2b-sandbox, Property 1: Provider depends only on the host suffix.
@settings(max_examples=100)
@given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=15),
       st.one_of(st.none(), st.booleans()), st.one_of(st.none(), st.booleans()), st.integers(0, 65535))
def test_provider(prefix: str, domain_cloud: bool | None, url_cloud: bool | None, case_mask: int) -> None:
    def mixed_case(host: str) -> str:
        return ''.join(char.upper() if case_mask & (1 << (i % 16)) else char for i, char in enumerate(host))
    domain = mixed_case(prefix + ('.aliyuncs.com' if domain_cloud else '.example.com')) if domain_cloud is not None else None
    url = 'https://' + mixed_case(prefix + ('.aliyuncs.com' if url_cloud else '.example.com')) + '/aliyuncs.com' if url_cloud is not None else None
    expected = domain_cloud is True or url_cloud is True
    assert E2BEndpoint(domain, url).provider == ('aliyun' if expected else 'e2b_official')


# Feature: e2b-sandbox, Property 2: New and legacy endpoints yield the region; overrides win.
@settings(max_examples=100)
@given(regions, regions)
def test_region(region: str, override: str) -> None:
    for kwargs in ({'domain': f'{region}.sandbox.aliyuncs.com'},
                   {'domain': f'id.{region}.e2b.fc.aliyuncs.com'},
                   {'api_url': f'https://api.{region}.sandbox.aliyuncs.com'}):
        cfg = E2BSandboxManagerConfig(api_key='placeholder', **kwargs)
        assert cfg.target_region == region
        assert E2BSandboxManagerConfig(api_key='placeholder', image_region=override, **kwargs).target_region == override
    assert E2BEndpoint('ap-southeast-1.sandbox.aliyuncs.com').region == 'ap-southeast-1'
    assert E2BEndpoint('e2b.app').region is None


# Feature: e2b-sandbox, Property 3: Rewrite changes only the ACR host region and is idempotent.
@settings(max_examples=100)
@given(regions, regions, text)
def test_region_rewrite(source: str, target: str, path: str) -> None:
    image = f'fc-e2b-registry.{source}.cr.aliyuncs.com/{path}'
    expected = f'fc-e2b-registry.{target}.cr.aliyuncs.com/{path}'
    assert rewrite_acr_region(image, target) == expected
    assert rewrite_acr_region(expected, target) == expected
    assert rewrite_acr_region(image, None) == image
    assert rewrite_acr_region(f'docker.io/{path}', target) == f'docker.io/{path}'


# Feature: e2b-sandbox, Property 5: Template names are bounded, deterministic and sensitive to build inputs.
@settings(max_examples=100)
@given(text, st.sampled_from(['micro', 'container']), st.integers(1, 64), st.integers(1, 65536), st.integers(1, 99999))
def test_template_name(image: str, mode: str, cpu: int, memory: int, disk: int) -> None:
    kwargs = dict(build_mode=mode, cpu_count=cpu, memory_mb=memory, disk_size_mb=disk)
    name = build_template_name(image, **kwargs)
    assert re.fullmatch(r'ms-enclave-[a-z0-9_-]+-[0-9a-f]{8}', name)
    assert len(name) <= 128
    payload = '\n'.join([image, mode, str(cpu), str(memory), str(disk)])
    assert name.endswith(hashlib.sha256(payload.encode()).hexdigest()[:8])
    assert build_template_name(image, **kwargs) == name
    for key, value in [('build_mode', 'micro' if mode == 'container' else 'container'),
                       ('cpu_count', cpu + 1), ('memory_mb', memory + 1), ('disk_size_mb', disk + 1)]:
        assert build_template_name(image, **(kwargs | {key: value}))[-8:] != name[-8:]
    assert build_template_name(image + 'x', **kwargs)[-8:] != name[-8:]


def test_image_normalization() -> None:
    assert normalize_image_ref(' swebench/task:latest ') == 'docker.io/swebench/task:latest'
    for image in ['docker.io/swebench/task:latest', 'localhost:5000/repo:t', 'ghcr.io/org/image:t']:
        assert normalize_image_ref(image) == image


def test_provider_requires_dns_suffix_boundary() -> None:
    assert E2BEndpoint('notaliyuncs.com').provider == 'e2b_official'
    assert E2BEndpoint(api_url='https://notaliyuncs.com').provider == 'e2b_official'
    assert E2BEndpoint('cn-hangzhou.notaliyuncs.com').region is None


def test_endpoint_normalizes_hosts_once_for_all_rules() -> None:
    endpoint = E2BEndpoint(domain='ID.CN-SHANGHAI.E2B.FC.ALIYUNCS.COM:8443')
    assert endpoint.provider == 'aliyun'
    assert endpoint.region == 'cn-shanghai'
    assert endpoint.default_build_mode == 'micro'
    endpoint = E2BEndpoint(api_url='https://API.CN-HANGZHOU.SANDBOX.ALIYUNCS.COM/path')
    assert endpoint.provider == 'aliyun' and endpoint.region == 'cn-hangzhou'
    assert E2BEndpoint().default_build_mode == 'container'
