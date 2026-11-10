"""E2B backend tests use fakes and never contact a provider."""

import asyncio
import builtins
import io
import logging
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import e2b
import e2b.api.client_async as e2b_api
import httpx
import pytest
from e2b import CommandExitException
from e2b.connection_config import ConnectionConfig
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import SecretStr, ValidationError

from ms_enclave.sandbox.boxes import DockerSandbox, SandboxFactory
from ms_enclave.sandbox.boxes import e2b_connection as connection_module
from ms_enclave.sandbox.boxes import e2b_template as template_module
from ms_enclave.sandbox.boxes.e2b_connection import E2BConnection, E2BError, retry_dispatch
from ms_enclave.sandbox.boxes.e2b_sandbox import E2BSandbox
from ms_enclave.sandbox.boxes.e2b_template import E2BTemplateError, E2BTemplateResolver
from ms_enclave.sandbox.manager import E2BSandboxManager
from ms_enclave.sandbox.model import (
    DockerSandboxConfig,
    E2BSandboxConfig,
    E2BSandboxManagerConfig,
    ExecutionStatus,
    SandboxStatus,
    SandboxType,
)


class FakeHandle:
    def __init__(self, code: int = 0, stdout: str = 'out', stderr: str = '') -> None:
        self.stdout, self.stderr, self.code = stdout, stderr, code
        self.hang = False
        self.kill = AsyncMock()

    async def wait(self) -> SimpleNamespace:
        if self.hang:
            await asyncio.Event().wait()
        if self.code:
            raise CommandExitException(stderr=self.stderr, stdout=self.stdout, exit_code=self.code, error=None)
        return SimpleNamespace(stdout=self.stdout, stderr=self.stderr)


class FakeCommands:
    def __init__(self) -> None:
        self.handle = FakeHandle()
        self.run = AsyncMock(side_effect=lambda *a, **k: self.handle)


class FakeFiles:
    def __init__(self) -> None:
        self.write = AsyncMock()


class FakeAsyncSandbox:
    def __init__(self) -> None:
        self.sandbox_id = 'remote-id'
        self.commands = FakeCommands()
        self.files = FakeFiles()
        self.kill = AsyncMock()


class FakeTemplateApi:
    def __init__(self) -> None:
        self.rows = []
        self.deleted = []
        self.error = None

    async def __aenter__(self) -> 'FakeTemplateApi':
        return self

    async def __aexit__(self, *args) -> None:
        pass

    def get_async_httpx_client(self) -> 'FakeTemplateApi':
        return self

    async def get(self, path: str) -> httpx.Response:
        if self.error:
            raise self.error
        return httpx.Response(200, json=self.rows, request=httpx.Request('GET', 'https://example.com/templates'))

    async def delete(self, path: str) -> httpx.Response:
        self.deleted.append(path)
        self.rows = []
        return httpx.Response(204, request=httpx.Request('DELETE', 'https://example.com' + path))


class FakeAsyncTemplate:
    def from_image(self, image: str) -> str:
        return image


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    api = FakeTemplateApi()
    remote = FakeAsyncSandbox()
    create = AsyncMock(return_value=remote)

    async def build(image: str, name: str, **kwargs) -> None:
        api.rows = [{'templateID': 'template-id', 'aliases': [name], 'buildStatus': 'ready'}]

    builder = AsyncMock(side_effect=build)
    monkeypatch.setattr(e2b, 'AsyncSandbox', SimpleNamespace(create=create))
    monkeypatch.setattr(e2b_api, 'get_api_client', lambda *a, **k: api)
    monkeypatch.setattr(e2b, 'AsyncTemplate', FakeAsyncTemplate)
    monkeypatch.setattr(FakeAsyncTemplate, 'build_in_background', builder, raising=False)
    monkeypatch.setattr(template_module, '_POLL_INTERVAL_S', 0)
    return SimpleNamespace(api=api, remote=remote, create=create, build=builder)


def connection(**kwargs) -> E2BConnection:
    return E2BConnection.from_config(E2BSandboxManagerConfig(api_key='test-secret', **kwargs))


def running_sandbox(handle: FakeHandle | None = None) -> E2BSandbox:
    box = E2BSandbox(E2BSandboxConfig(template='explicit'), connection=connection())
    box._sbx = FakeAsyncSandbox()
    if handle:
        box._sbx.commands.handle = handle
    return box


def test_manager_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('E2B_API_KEY', raising=False)
    with pytest.raises(ValidationError, match='api_key.*E2B_API_KEY'):
        E2BSandboxManagerConfig()
    monkeypatch.setenv('E2B_API_KEY', 'environment-key')
    cfg = E2BSandboxManagerConfig()
    assert cfg.api_key.get_secret_value() == 'environment-key'
    assert cfg.api_url is cfg.domain is None
    assert cfg.resolved_build_mode == 'container'
    assert 'environment-key' not in repr(cfg)
    cfg = E2BSandboxManagerConfig(domain='cn-hangzhou.sandbox.aliyuncs.com', image_mapping={'hidden': 'value'})
    assert cfg.resolved_build_mode == 'micro'
    assert 'hidden' not in repr(cfg)
    with pytest.raises(ValidationError, match='only supported by Aliyun'):
        E2BSandboxManagerConfig(build_mode='micro')
    for field in ['provider', 'request_timeout', 'metadata', 'template_label', 'unknown']:
        with pytest.raises(ValidationError, match=field):
            E2BSandboxManagerConfig(**{field: 'bad'})
    for field in ['max_sandboxes', 'max_concurrent_builds']:
        for value in [0, -1]:
            with pytest.raises(ValidationError, match=field):
                E2BSandboxManagerConfig(**{field: value})


def test_sandbox_config() -> None:
    cfg = E2BSandboxConfig(image='example:image')
    assert (cfg.sandbox_timeout, cfg.cpu_count, cfg.memory_mb, cfg.disk_size_mb) == (3600, 2, 4096, 15360)
    assert cfg.user == 'user' and cfg.working_dir == '/home/user'
    for field in ['sandbox_timeout', 'cpu_count', 'memory_mb', 'disk_size_mb']:
        for value in [0, -1]:
            with pytest.raises(ValidationError, match=field):
                E2BSandboxConfig(image='image', **{field: value})
    with pytest.raises(ValidationError, match='template.*image'):
        E2BSandboxConfig()
    with pytest.raises(ValidationError, match='unknown'):
        E2BSandboxConfig(template='existing', unknown=True)


def test_invalid_manager_config_masks_key() -> None:
    with pytest.raises(ValidationError) as error:
        E2BSandboxManagerConfig(api_key='plaintext-secret', build_mode='micro')
    assert 'plaintext-secret' not in str(error.value)


def test_environment_endpoints_match_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('E2B_DOMAIN', 'id.cn-shanghai.e2b.fc.aliyuncs.com')
    monkeypatch.setenv('E2B_API_URL', 'https://api.cn-shanghai.sandbox.aliyuncs.com')
    cfg = E2BSandboxManagerConfig(api_key='placeholder')
    assert cfg.provider == 'aliyun' and cfg.resolved_build_mode == 'micro'
    assert cfg.target_region == 'cn-shanghai'
    assert ConnectionConfig(**E2BConnection.from_config(cfg).api_params()).domain == cfg.domain
    cfg = E2BSandboxManagerConfig(api_key='placeholder', domain='example.com', api_url='https://api.example.com')
    assert cfg.provider == 'e2b_official' and cfg.resolved_build_mode == 'container'


@pytest.mark.parametrize('capabilities', [[], ['SYS_ADMIN']])
async def test_docker_capabilities(capabilities: list[str]) -> None:
    sandbox = DockerSandbox(DockerSandboxConfig(cap_add=capabilities))
    sandbox.client = MagicMock()
    sandbox._run_blocking = AsyncMock(return_value=MagicMock())
    try:
        await sandbox._create_container()
        kwargs = sandbox._run_blocking.await_args.kwargs
        if capabilities:
            assert kwargs['cap_add'] == capabilities
        else:
            assert 'cap_add' not in kwargs
    finally:
        sandbox._executor.shutdown(wait=False, cancel_futures=True)


async def test_docker_unrestricted_resources() -> None:
    defaults = DockerSandboxConfig()
    assert defaults.memory_limit == '4g' and defaults.cpu_limit == 2
    sandbox = DockerSandbox(DockerSandboxConfig(memory_limit=None, cpu_limit=None))
    sandbox.client = MagicMock()
    sandbox._run_blocking = AsyncMock(return_value=MagicMock())
    try:
        await sandbox._create_container()
        assert not {'mem_limit', 'cpu_quota', 'cpu_period'} & sandbox._run_blocking.await_args.kwargs.keys()
    finally:
        sandbox._executor.shutdown(wait=False, cancel_futures=True)


@pytest.mark.parametrize('failures', [0, 1, 2, 3])
async def test_retry_connection_failures(failures: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection_module.asyncio, 'sleep', AsyncMock())
    call = AsyncMock(side_effect=[ConnectionError('test-secret')] * failures + ['ok'])
    if failures == 3:
        with pytest.raises(RuntimeError, match='run_id=run') as error:
            await retry_dispatch('create', call, run_id='run')
        assert 'test-secret' not in str(error.value)
    else:
        assert await retry_dispatch('create', call, run_id='run') == 'ok'
    assert call.call_count == min(failures + 1, 3)


async def test_retry_status_and_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection_module.asyncio, 'sleep', AsyncMock())
    response = httpx.Response(429, request=httpx.Request('GET', 'https://example.com'))
    call = AsyncMock(side_effect=[httpx.HTTPStatusError('limited', request=response.request, response=response), 'ok'])
    assert await retry_dispatch('status', call, run_id='r') == 'ok'
    call = AsyncMock(side_effect=httpx.ReadTimeout('unknown dispatch state'))
    with pytest.raises(E2BError, match='ReadTimeout') as error:
        await retry_dispatch('create', call, run_id='r')
    assert error.value.details.get_secret_value() == 'unknown dispatch state'
    assert call.call_count == 1
    assert 'api_url' not in connection().api_params()
    assert 'domain' not in connection().api_params()


# Feature: e2b-sandbox, Property 4: Final images match provider-specific mapping and region rules.
@settings(max_examples=100)
@given(st.booleans(), st.booleans(), st.booleans(), st.from_regex('[a-z]{1,12}', fullmatch=True))
def test_final_image(aliyun: bool, mapped: bool, prefix: bool, label: str) -> None:
    source = f'org/{label}:latest'
    acr = f'fc-e2b-registry.cn-shanghai.cr.aliyuncs.com/repo/{label}:v1'
    conn = connection(domain='cn-hangzhou.sandbox.aliyuncs.com' if aliyun else None)
    resolver = E2BTemplateResolver(conn, {('docker.io/' if prefix else '') + source: acr} if mapped else {}, 2)
    if aliyun and not mapped:
        with pytest.raises(E2BTemplateError, match=source):
            resolver.final_image(source)
    else:
        expected = acr.replace('cn-shanghai', 'cn-hangzhou') if aliyun else source
        assert resolver.final_image(source) == expected


# Feature: e2b-sandbox, Property 6: Concurrent same-name resolution shares one terminal build outcome.
@settings(max_examples=100)
@given(st.integers(1, 16), st.sampled_from([None, 'ready', 'building', 'waiting', 'error']), st.booleans())
def test_shared_template_resolution(count: int, initial: str | None, success: bool) -> None:
    async def run() -> None:
        resolver = E2BTemplateResolver(connection(), {}, 2)
        remote = template_module._RemoteTemplate(template_id='id', status=initial) if initial else None
        resolver._find = AsyncMock(return_value=remote)
        resolver._delete = AsyncMock()
        resolver._build = AsyncMock()
        resolver._wait = AsyncMock(return_value=template_module._RemoteTemplate(template_id='id', status='ready' if success else 'error'))
        cfg = E2BSandboxConfig(image='org/image')
        results = await asyncio.gather(*(resolver.resolve(cfg, run_id='r') for _ in range(count)), return_exceptions=True)
        failed = initial != 'ready' and not success
        assert all(isinstance(r, E2BTemplateError) == failed for r in results)
        assert len({str(r) for r in results}) == 1
        should_build = initial not in ['ready', 'building', 'waiting'] or (initial in ['building', 'waiting'] and not success)
        assert resolver._build.call_count == int(should_build)
        assert resolver._delete.call_count == int(initial == 'error' or (initial in ['building', 'waiting'] and not success))
        if failed:
            with pytest.raises(E2BTemplateError):
                await resolver.resolve(cfg, run_id='r')
            assert resolver._build.call_count == int(should_build)
    asyncio.run(run())


async def test_template_api_and_headers(sdk: SimpleNamespace) -> None:
    for domain, mode in [(None, 'container'), ('id.cn-shanghai.e2b.fc.aliyuncs.com', 'micro')]:
        resolver = E2BTemplateResolver(connection(domain=domain), {}, 2)
        cfg = E2BSandboxConfig(image='fc-e2b-registry.cn-shanghai.cr.aliyuncs.com/repo:i', disk_size_mb=12345)
        name = await resolver.resolve(cfg, run_id='r')
        headers = sdk.build.call_args.kwargs['api_headers']
        assert headers == ({'X-E2B-Template-Build-Mode': 'micro', 'X-E2B-Template-Alpha-Disk-Size': '12345'} if mode == 'micro' else {})
        assert sdk.build.call_args.kwargs['retries'] == 0
        fresh = E2BTemplateResolver(connection(domain=domain), {}, 2)
        sdk.api.rows = [{'templateID': 'id', 'names': [f'team/{name}'], 'buildStatus': 'ready'}]
        before = sdk.build.call_count
        assert await fresh.resolve(cfg, run_id='r') == name
        assert sdk.build.call_count == before
    assert await resolver.resolve(E2BSandboxConfig(template='explicit'), run_id='r') == 'explicit'


async def test_template_poll_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = E2BTemplateResolver(connection(), {}, 1)
    resolver._find = AsyncMock(return_value=template_module._RemoteTemplate(template_id='id', status='waiting'))
    monkeypatch.setattr(template_module, '_POLL_TIMEOUT_S', 0)
    with pytest.raises(E2BTemplateError, match='name.*waiting'):
        await resolver._wait('name', run_id='r')


async def test_template_eventual_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = E2BTemplateResolver(connection(), {}, 1)
    ready = template_module._RemoteTemplate(template_id='id', status='ready')
    resolver._find = AsyncMock(side_effect=[None, template_module._RemoteTemplate(template_id='id', status='building'), ready])
    monkeypatch.setattr(template_module, '_POLL_INTERVAL_S', 0)
    assert await resolver._wait('name', run_id='r') == ready


async def test_build_concurrency_limit() -> None:
    resolver = E2BTemplateResolver(connection(), {}, 2)
    resolver._find = AsyncMock(return_value=None)
    active = peak = 0

    async def build(*args, **kwargs) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)

    async def wait(*args, **kwargs):
        nonlocal active
        await asyncio.sleep(0)
        active -= 1
        return template_module._RemoteTemplate(template_id='id', status='ready')

    resolver._build, resolver._wait = build, wait
    await asyncio.gather(*(resolver.resolve(E2BSandboxConfig(image=f'org/{i}'), run_id='r') for i in range(8)))
    assert peak == 2 and active == 0


# Feature: e2b-sandbox, Property 7: POSIX list command quoting round-trips without argument loss.
@settings(max_examples=100)
@given(st.lists(st.text(alphabet=st.characters(blacklist_characters='\x00', blacklist_categories=('Cs',))), max_size=8))
def test_command_quoting(argv: list[str]) -> None:
    async def run() -> None:
        box = running_sandbox()
        await box.execute_command(argv)
        assert shlex.split(box._sbx.commands.run.call_args.args[0]) == argv
    asyncio.run(run())


# Feature: e2b-sandbox, Property 8: Command output and exit codes are preserved without redispatch.
@settings(max_examples=100)
@given(st.integers(0, 255), st.text(), st.text())
def test_command_result(code: int, stdout: str, stderr: str) -> None:
    async def run() -> None:
        box = running_sandbox(FakeHandle(code, stdout, stderr))
        result = await box.execute_command('command')
        assert (result.exit_code, result.stdout, result.stderr) == (code, stdout, stderr)
        assert result.status == (ExecutionStatus.ERROR if code else ExecutionStatus.SUCCESS)
        assert box._sbx.commands.run.call_count == 1
    asyncio.run(run())


# Feature: e2b-sandbox, Property 9: Uploaded directories preserve relative paths and bytes.
@settings(max_examples=100)
@given(st.dictionaries(st.lists(st.from_regex('[a-z]{1,5}', fullmatch=True), min_size=1, max_size=3).map('/'.join),
                       st.binary(max_size=100), max_size=8))
def test_put_dir_roundtrip(files: dict[str, bytes]) -> None:
    # Prefix file names so generated file paths cannot also be parent directories.
    files = {str(Path(path).parent / ('file-' + Path(path).name)): data for path, data in files.items()}
    async def run() -> None:
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / 'source', Path(root) / 'target'
            source.mkdir()
            for path, data in files.items():
                dest = source / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            box = running_sandbox()
            assert await box.put_dir(source, '/target')
            archive = box._sbx.files.write.call_args.args[1]
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(target, filter='data')
            restored = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}
            assert restored == files
    asyncio.run(run())


async def test_command_timeout_and_overrides() -> None:
    handle = FakeHandle(stdout='partial', stderr='partial error')
    handle.hang = True
    handle.kill.side_effect = RuntimeError('test-secret kill failed')
    box = running_sandbox(handle)
    box.config.env_vars = {'A': 'old', 'B': 'kept'}
    result = await box.execute_command('sleep 100', timeout=0.001, user='root', cwd='/testbed', env={'A': 'new'})
    assert (result.status, result.stdout, result.stderr) == (ExecutionStatus.TIMEOUT, 'partial', 'partial error')
    handle.kill.assert_awaited_once()
    kwargs = box._sbx.commands.run.call_args.kwargs
    assert kwargs == dict(background=True, user='root', cwd='/testbed', envs={'A': 'new', 'B': 'kept'}, timeout=0)
    assert box.status == SandboxStatus.ERROR
    with pytest.raises(RuntimeError, match='error state'):
        await box.execute_command('command')
    box = running_sandbox()
    box._sbx.commands.run.side_effect = RuntimeError('test-secret dispatch failed')
    result = await box.execute_command('command')
    assert result.exit_code == -1 and result.status == ExecutionStatus.ERROR
    assert 'test-secret' not in result.stderr
    assert box._sbx.commands.run.call_count == 1


async def test_archive_errors_and_cleanup() -> None:
    box = running_sandbox()
    with pytest.raises(ValueError, match='absolute'):
        await box.put_archive('relative', b'archive')
    box._sbx.files.write.assert_not_awaited()
    assert await box.put_archive('/test path', b'archive')
    assert box._sbx.files.write.call_args.kwargs == {'user': 'user'}
    cmd = box._sbx.commands.run.call_args.args[0]
    assert "-C '/test path'" in cmd and 'rm -f' in cmd
    box._sbx.files.write.side_effect = RuntimeError('upload failed')
    assert not await box.put_archive('/path', b'archive')
    box._sbx.files.write.side_effect = None
    box._sbx.commands.handle.code = 1
    assert not await box.put_archive('/path', b'archive')
    remote = box._sbx
    remote.kill.side_effect = RuntimeError('kill failed')
    with pytest.raises(E2BError, match='kill sandbox.*failed'):
        await box.stop()
    assert box.status == SandboxStatus.ERROR and box._sbx is remote
    remote.kill.side_effect = None
    await box.stop()
    await box.stop()
    assert remote.kill.await_count == 2 and box._sbx is None


async def test_create_metadata_factory_and_failure(sdk: SimpleNamespace) -> None:
    box = SandboxFactory.create_sandbox(SandboxType.E2B, {'template': 'explicit'})
    assert isinstance(box.config, E2BSandboxConfig)
    box._conn = connection()
    await box.start()
    kwargs = sdk.create.call_args.kwargs
    assert kwargs['metadata'] == {'created_by': 'ms-enclave', 'run_id': box._run_id}
    assert kwargs['timeout'] == 3600 and kwargs['retries'] == 0
    assert 'lifecycle' not in kwargs and 'envs' not in kwargs
    await box.stop()
    sdk.create.side_effect = RuntimeError('test-secret Timeout cannot be greater than 1 hours')
    with pytest.raises(E2BError, match='template=explicit.*sandbox_timeout=3600.*run_id=') as error:
        await box.start()
    assert 'test-secret' not in str(error.value)
    assert 'test-secret' in error.value.details.get_secret_value()


# Feature: e2b-sandbox, Property 10: Live sandbox limits and slots survive create failures and repeated deletion.
@settings(max_examples=100)
@given(st.integers(1, 8), st.lists(st.booleans(), min_size=1, max_size=16))
def test_manager_slots(limit: int, outcomes: list[bool]) -> None:
    async def run() -> None:
        with pytest.MonkeyPatch.context() as patch:
            active = peak = 0
            remotes = []
            async def create(**kwargs):
                nonlocal active, peak
                if not outcomes.pop(0):
                    raise RuntimeError('creation failed')
                remote = FakeAsyncSandbox()
                active += 1
                peak = max(peak, active)
                async def kill(**kwargs):
                    nonlocal active
                    active -= 1
                remote.kill.side_effect = kill
                remotes.append(remote)
                return remote
            patch.setattr(e2b, 'AsyncSandbox', SimpleNamespace(create=create))
            manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': limit})
            await manager.start()
            async def worker() -> None:
                try:
                    sid = await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})
                except RuntimeError:
                    return
                await asyncio.sleep(0)
                await asyncio.gather(manager.delete_sandbox(sid), manager.delete_sandbox(sid))
            await asyncio.gather(*(worker() for _ in range(len(outcomes))))
            await manager.stop()
            assert peak <= limit and active == 0
            assert not manager._reservations and not manager._sandboxes
            assert all(remote.kill.call_count == 1 for remote in remotes)
    outcomes = list(outcomes)
    asyncio.run(run())


# Feature: e2b-sandbox, Property 11: SDK failure diagnostics and cached errors never expose the API key.
@settings(max_examples=100)
@given(st.text(alphabet='abcdef0123456789', min_size=12, max_size=24))
def test_sdk_error_details_are_secret(secret: str) -> None:
    async def run() -> None:
        conn = E2BConnection.from_config(E2BSandboxManagerConfig(api_key=secret))
        assert secret not in repr(conn)
        assert secret not in E2BSandboxManagerConfig(api_key=secret).model_dump_json()
        resolver = E2BTemplateResolver(conn, {}, 1)
        resolver._find = AsyncMock(side_effect=RuntimeError(secret))
        with pytest.raises(E2BTemplateError) as error:
            await resolver.resolve(E2BSandboxConfig(image='org/image'), run_id='r')
        assert secret not in str(error.value) and secret not in str(resolver._failed)
        box = running_sandbox()
        box._conn = conn
        box._sbx.commands.run.side_effect = RuntimeError(secret)
        assert secret not in (await box.execute_command('cmd')).stderr
        call = AsyncMock(side_effect=RuntimeError(secret))
        with pytest.raises(RuntimeError) as error:
            await retry_dispatch('create', call, run_id='r')
        assert secret not in str(error.value)
        assert isinstance(error.value.details, SecretStr)
        assert secret not in repr(vars(error.value))
        assert error.value.details.get_secret_value() == secret
        assert secret not in ''.join(traceback.format_exception(error.value))
    asyncio.run(run())


@pytest.mark.parametrize('sdk_error', [False, True])
async def test_sdk_response_is_private_in_errors_and_retry_logs(
    sdk_error: bool, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from e2b import RateLimitException

    secret = 'private-key-for-test-only'
    message = f'api_key={secret}; encoded=private%2Dkey%2Dfor%2Dtest%2Donly'
    response = httpx.Response(429, request=httpx.Request('POST', 'https://example.com?api_key=' + secret))
    cause = (
        RateLimitException(message)
        if sdk_error
        else httpx.HTTPStatusError(message, request=response.request, response=response)
    )
    monkeypatch.setattr(connection_module.asyncio, 'sleep', AsyncMock())
    logger = connection_module.logger
    logger.addHandler(caplog.handler)
    try:
        with pytest.raises(E2BError) as raised:
            await retry_dispatch('create', AsyncMock(side_effect=cause), run_id='test-run')
    finally:
        logger.removeHandler(caplog.handler)
    error = raised.value
    assert error.status_code == 429 and 'HTTP 429' in str(error)
    assert type(cause).__name__ in str(error) and 'test-run' in str(error)
    assert error.details.get_secret_value() == message
    public = '\n'.join([
        str(error), repr(error), repr(vars(error)),
        ''.join(traceback.format_exception(error)), caplog.text,
    ])
    assert secret not in public and 'private%2Dkey' not in public
    assert len(caplog.records) == 2
    outer = E2BError.from_exception('create sandbox', error, run_id='test-run')
    assert outer.status_code == 429 and outer.details is error.details


async def test_upload_failure_log_keeps_sdk_response_private(caplog: pytest.LogCaptureFixture) -> None:
    box = running_sandbox()
    box._sbx.files.write.side_effect = RuntimeError('test-secret upload rejected')
    logger = connection_module.logger
    logger.addHandler(caplog.handler)
    try:
        assert not await box.put_archive('/home/user', b'archive')
    finally:
        logger.removeHandler(caplog.handler)
    assert 'test-secret' not in caplog.text
    assert 'upload to /home/user' in caplog.text and 'RuntimeError' in caplog.text


async def test_unexpected_template_response_does_not_expose_details(sdk: SimpleNamespace) -> None:
    secret = 'unexpected-response-with-test-secret'

    async def build(image, name, **kwargs):
        sdk.api.rows = [{'templateID': 'id', 'aliases': [name], 'buildStatus': secret}]

    sdk.build.side_effect = build
    resolver = E2BTemplateResolver(connection(), {}, 1)
    with pytest.raises(E2BTemplateError, match='ValidationError') as error:
        await resolver.resolve(E2BSandboxConfig(image='org/image'), run_id='r')
    assert secret not in str(error.value) and secret not in str(resolver._failed)
    assert isinstance(error.value.details, SecretStr)
    assert secret not in error.value.details.get_secret_value()


async def test_manager_cleanup_and_invalid_type(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder'})
    assert re.fullmatch('[0-9a-f]{12}', manager.run_id)
    await manager.start()
    with pytest.raises(ValueError, match='only supports'):
        await manager.create_sandbox(SandboxType.DOCKER, {})
    sid = await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})
    assert sid in manager._sandboxes
    await manager.stop()
    assert not manager._sandboxes
    sdk.remote.kill.assert_awaited_once()


@pytest.mark.parametrize('explicit_size', [None, 2])
async def test_pool_rejects_impossible_size(sdk: SimpleNamespace, explicit_size: int | None) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1, 'pool_size': 2})
    await manager.start()
    try:
        with pytest.raises(ValueError, match='pool_size=2 exceeds E2B max_sandboxes=1'):
            await asyncio.wait_for(manager.initialize_pool(explicit_size, config={'template': 'explicit'}), 1)
        sdk.create.assert_not_awaited()
    finally:
        await manager.stop()


async def test_pool_defaults_to_e2b(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    try:
        pool = await manager.initialize_pool(1, config={'template': 'explicit'})
        assert len(pool) == 1
        assert (await manager.get_sandbox(pool[0])).sandbox_type == SandboxType.E2B
        assert (await manager.get_stats())['manager_type'] == 'e2b'
        with pytest.raises(ValueError, match='Not enough E2B capacity'):
            await manager.initialize_pool(1, config={'template': 'explicit'})
    finally:
        await manager.stop()
    sdk.remote.kill.assert_awaited_once()


async def test_concurrent_start_and_stop_are_idempotent(sdk: SimpleNamespace) -> None:
    box = E2BSandbox(E2BSandboxConfig(template='explicit'), connection=connection())
    await asyncio.gather(box.start(), box.start())
    sdk.create.assert_awaited_once()
    await asyncio.gather(box.stop(), box.stop())
    sdk.remote.kill.assert_awaited_once()


async def test_concurrent_pools_check_remaining_capacity(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    entered, release = asyncio.Event(), asyncio.Event()

    async def resolve(*args, **kwargs):
        entered.set()
        await release.wait()
        return 'explicit'

    manager._templates.resolve = resolve
    await manager.start()
    first = asyncio.create_task(manager.initialize_pool(1, config={'template': 'explicit'}))
    await entered.wait()
    second = asyncio.create_task(manager.initialize_pool(1, config={'template': 'explicit'}))
    release.set()
    try:
        results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 1)
        assert len(results[0]) == 1
        assert isinstance(results[1], ValueError)
        sdk.create.assert_awaited_once()
    finally:
        await manager.stop()


async def test_startup_failure_cleans_created_resource(sdk: SimpleNamespace) -> None:
    box = E2BSandbox(E2BSandboxConfig(template='explicit'), connection=connection())
    box.initialize_tools = AsyncMock(side_effect=RuntimeError('initialization failed'))
    with pytest.raises(RuntimeError, match='initialization failed'):
        await box.start()
    sdk.remote.kill.assert_awaited_once()
    assert box._sbx is None and box.status == SandboxStatus.ERROR


@pytest.mark.parametrize('tool', ['shell_executor', 'python_executor'])
@pytest.mark.parametrize('status', [ExecutionStatus.SUCCESS, ExecutionStatus.ERROR, ExecutionStatus.TIMEOUT])
async def test_tools(tool: str, status: ExecutionStatus) -> None:
    box = running_sandbox()
    box.config.tools_config = {tool: {}}
    await box.initialize_tools()
    box.put_file = AsyncMock(return_value=True)
    from ms_enclave.sandbox.model import CommandResult
    box.execute_command = AsyncMock(return_value=CommandResult(
        command='cmd', status=status, exit_code=0 if status == ExecutionStatus.SUCCESS else -1, stdout='out', stderr='err'))
    params = {'command': 'echo hi'} if tool == 'shell_executor' else {'code': 'print(1)'}
    result = await box.execute_tool(tool, params)
    assert result.status == status


async def test_python_upload_failure_does_not_execute() -> None:
    box = running_sandbox()
    box.config.tools_config = {'python_executor': {}}
    await box.initialize_tools()
    box.put_file = AsyncMock(return_value=False)
    result = await box.execute_tool('python_executor', {'code': 'print(1)'})
    assert result.status == ExecutionStatus.ERROR and 'upload' in result.error
    box._sbx.commands.run.assert_not_awaited()


async def test_cancelled_command_kills_remote_process() -> None:
    entered = asyncio.Event()
    handle = FakeHandle()

    async def wait():
        entered.set()
        await asyncio.Event().wait()

    handle.wait = wait
    box = running_sandbox(handle)
    task = asyncio.create_task(box.execute_command('sleep 999'))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    handle.kill.assert_awaited_once()


async def test_command_timeout_covers_dispatch() -> None:
    box = running_sandbox()

    async def dispatch(*args, **kwargs):
        await asyncio.Event().wait()

    box._sbx.commands.run.side_effect = dispatch
    result = await asyncio.wait_for(box.execute_command('sleep 999', timeout=0.001), 1)
    assert result.status == ExecutionStatus.TIMEOUT
    assert box.status == SandboxStatus.ERROR
    assert box._sbx.commands.run.await_count == 1


async def test_manager_retries_failed_delete_and_shutdown(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    sid = await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})
    sdk.remote.kill.side_effect = RuntimeError('kill rejected')
    with pytest.raises(E2BError, match='kill sandbox.*failed'):
        await manager.delete_sandbox(sid)
    assert sid in manager._sandboxes and manager._reservations == {sid}
    with pytest.raises(RuntimeError, match='cleanup incomplete'):
        await manager.stop()
    assert sid in manager._sandboxes and manager._reservations == {sid}
    sdk.remote.kill.side_effect = None
    await manager.stop()
    assert not manager._sandboxes and not manager._reservations


async def test_duplicate_id_does_not_create_or_consume_capacity(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    try:
        await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}, 'same')
        with pytest.raises(ValueError, match='already exists'):
            await asyncio.wait_for(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}, 'same'), 1)
        sdk.create.assert_awaited_once()
    finally:
        await manager.stop()
    assert not manager._reservations


async def test_shutdown_drains_inflight_creation(sdk: SimpleNamespace) -> None:
    entered, finish = asyncio.Event(), asyncio.Event()

    async def create(**kwargs):
        entered.set()
        await finish.wait()
        return sdk.remote

    sdk.create.side_effect = create
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    creating = asyncio.create_task(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}))
    await entered.wait()
    stopping = asyncio.create_task(manager.stop())
    # Wait until shutdown has closed admission, before delivering the create response.
    while manager._running:
        await asyncio.sleep(0)
    finish.set()
    await asyncio.wait_for(stopping, 1)
    with pytest.raises(asyncio.CancelledError):
        await creating
    sdk.remote.kill.assert_awaited_once()
    assert not manager._sandboxes and not manager._reservations
    with pytest.raises(RuntimeError, match='not started'):
        await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})


async def test_stop_releases_capacity_without_double_release(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    try:
        sid = await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})
        assert await manager.stop_sandbox(sid)
        assert (await manager.get_sandbox_info(sid)).status == SandboxStatus.STOPPED
        next_id = await asyncio.wait_for(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}), 1)
        assert await manager.stop_sandbox(sid)
        assert await manager.delete_sandbox(sid)
        assert manager._reservations == {next_id}
    finally:
        await manager.stop()


async def test_pool_reserves_full_capacity_before_resolution(sdk: SimpleNamespace) -> None:
    entered, competing, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 2})

    async def resolve(config, **kwargs):
        if config.template == 'pool':
            entered.set()
            await finish.wait()
        else:
            competing.set()
        return config.template

    sdk.create.side_effect = lambda **kwargs: FakeAsyncSandbox()
    manager._templates.resolve = resolve
    await manager.start()
    pool = asyncio.create_task(manager.initialize_pool(2, config={'template': 'pool'}))
    await entered.wait()
    other = asyncio.create_task(manager.create_sandbox(SandboxType.E2B, {'template': 'other'}))
    await competing.wait()
    try:
        sdk.create.assert_not_awaited()
        finish.set()
        members = await asyncio.wait_for(pool, 1)
        assert len(members) == 2 and not other.done()
        assert sdk.create.await_count == 2
        assert await manager.stop_sandbox(members[0])
        other_id = await asyncio.wait_for(other, 1)
        assert manager._reservations == {members[1], other_id}
    finally:
        finish.set()
        await manager.stop()


async def test_failed_stop_keeps_capacity_reserved(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    sid = await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})
    sdk.remote.kill.side_effect = RuntimeError('kill rejected')
    assert not await manager.stop_sandbox(sid)
    assert manager._reservations == {sid}
    assert (await manager.get_sandbox_info(sid)).status == SandboxStatus.ERROR
    sdk.remote.kill.side_effect = None
    assert await manager.stop_sandbox(sid)
    assert not manager._reservations
    await manager.stop()


async def test_failed_pool_build_releases_all_unused_capacity(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 2})
    manager._templates.resolve = AsyncMock(side_effect=RuntimeError('template failed'))
    await manager.start()
    try:
        with pytest.raises(RuntimeError, match='template failed'):
            await manager.initialize_pool(2, config={'image': 'org/image'})
        assert not manager._reservations and not manager._sandboxes
        sdk.create.assert_not_awaited()
        manager._templates.resolve = AsyncMock(return_value='explicit')
        assert len(await manager.initialize_pool(2, config={'template': 'explicit'})) == 2
    finally:
        await manager.stop()


async def test_failed_pool_member_releases_only_its_capacity(sdk: SimpleNamespace) -> None:
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 2})
    sdk.create.side_effect = [RuntimeError('create rejected'), FakeAsyncSandbox(), FakeAsyncSandbox()]
    await manager.start()
    try:
        members = await manager.initialize_pool(2, config={'template': 'explicit'})
        assert len(members) == 1 and manager._reservations == set(members)
        extra = await asyncio.wait_for(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}), 1)
        assert manager._reservations == {members[0], extra}
    finally:
        await manager.stop()


@pytest.mark.parametrize('ready', [False, True])
async def test_pool_rejects_capacity_occupied_by_live_or_inflight_create(sdk: SimpleNamespace, ready: bool) -> None:
    entered, finish = asyncio.Event(), asyncio.Event()

    async def create(**kwargs):
        entered.set()
        await finish.wait()
        return sdk.remote

    sdk.create.side_effect = create
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 2})
    await manager.start()
    creating = asyncio.create_task(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}))
    await entered.wait()
    if ready:
        finish.set()
        await creating
    try:
        with pytest.raises(ValueError, match='Not enough E2B capacity'):
            await asyncio.wait_for(manager.initialize_pool(2, config={'template': 'explicit'}), 1)
        sdk.create.assert_awaited_once()
        finish.set()
        await creating
    finally:
        finish.set()
        await manager.stop()


async def test_failed_pool_start_keeps_unconfirmed_remote_reservation(
    sdk: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed_remote = FakeAsyncSandbox()
    failed_remote.kill.side_effect = RuntimeError('kill rejected')
    sdk.create.side_effect = [failed_remote, FakeAsyncSandbox()]
    monkeypatch.setattr(E2BSandbox, 'initialize_tools', AsyncMock(side_effect=[RuntimeError('startup failed'), None]))
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 2})
    await manager.start()
    try:
        members = await manager.initialize_pool(2, config={'template': 'explicit'})
        assert len(members) == 1
        assert manager._reservations == set(manager._sandboxes) and len(manager._reservations) == 2
        failed_id, = manager._reservations - set(members)
        assert (await manager.get_sandbox_info(failed_id)).status == SandboxStatus.ERROR
        failed_remote.kill.side_effect = None
        assert await manager.delete_sandbox(failed_id)
        assert manager._reservations == set(members)
    finally:
        failed_remote.kill.side_effect = None
        await manager.stop()


async def test_shutdown_cancels_capacity_waiter(sdk: SimpleNamespace) -> None:
    waiting = asyncio.Event()
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'})

    async def resolve(*args, **kwargs):
        waiting.set()
        return 'explicit'

    manager._templates.resolve = resolve
    queued = asyncio.create_task(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}))
    await waiting.wait()
    await manager.stop()
    with pytest.raises(asyncio.CancelledError):
        await queued
    sdk.create.assert_awaited_once()
    assert not manager._sandboxes and not manager._reservations


async def test_shutdown_drains_pool_create_and_unused_reservations(sdk: SimpleNamespace) -> None:
    entered, finish = asyncio.Event(), asyncio.Event()

    async def create(**kwargs):
        entered.set()
        await finish.wait()
        return sdk.remote

    sdk.create.side_effect = create
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 3})
    await manager.start()
    pool = asyncio.create_task(manager.initialize_pool(3, config={'template': 'explicit'}))
    await entered.wait()
    stopping = asyncio.create_task(manager.stop())
    while manager._running:
        await asyncio.sleep(0)
    finish.set()
    await asyncio.wait_for(stopping, 1)
    with pytest.raises(asyncio.CancelledError):
        await pool
    sdk.create.assert_awaited_once()
    sdk.remote.kill.assert_awaited_once()
    assert not manager._sandboxes and not manager._reservations


async def test_concurrent_duplicate_id_never_reaches_provider_twice(sdk: SimpleNamespace) -> None:
    creating, competing, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def create(**kwargs):
        creating.set()
        await finish.wait()
        return sdk.remote

    sdk.create.side_effect = create
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 2})
    await manager.start()
    first = asyncio.create_task(manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}, 'same'))
    await creating.wait()

    async def duplicate():
        competing.set()
        return await manager.create_sandbox(SandboxType.E2B, {'template': 'explicit'}, 'same')

    second = asyncio.create_task(duplicate())
    await competing.wait()
    finish.set()
    try:
        results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 1)
        assert results[0] == 'same' and isinstance(results[1], ValueError)
        sdk.create.assert_awaited_once()
        assert manager._reservations == {'same'}
    finally:
        await manager.stop()


async def test_pool_cancellation_waits_for_process_kill(sdk: SimpleNamespace) -> None:
    waiting, killing, finish_kill = asyncio.Event(), asyncio.Event(), asyncio.Event()
    handle = FakeHandle()

    async def wait():
        waiting.set()
        await asyncio.Event().wait()

    async def kill():
        killing.set()
        await finish_kill.wait()

    handle.wait = wait
    handle.kill.side_effect = kill
    sdk.remote.commands.run.side_effect = [handle, FakeHandle()]
    manager = E2BSandboxManager({'api_key': 'placeholder', 'max_sandboxes': 1})
    await manager.start()
    members = await manager.initialize_pool(1, config={'template': 'explicit', 'tools_config': ['shell_executor']})
    executing = asyncio.create_task(manager.execute_tool_in_pool('shell_executor', {'command': 'sleep 999'}))
    await waiting.wait()
    executing.cancel()
    await killing.wait()
    try:
        assert manager._sandboxes[members[0]].status == SandboxStatus.BUSY
        assert not executing.done()
        finish_kill.set()
        with pytest.raises(asyncio.CancelledError):
            await executing
        result = await asyncio.wait_for(manager.execute_tool_in_pool('shell_executor', {'command': 'echo next'}), 1)
        assert result.success
        assert sdk.remote.commands.run.await_count == 2
    finally:
        finish_kill.set()
        await manager.stop()


def test_optional_dependency() -> None:
    script = """
import builtins
import sys
original_import = builtins.__import__
def import_without_sdk(name, *args, **kwargs):
    if name == 'e2b' or name.startswith('e2b.'):
        raise AssertionError('E2B SDK imported before choosing E2B')
    return original_import(name, *args, **kwargs)
builtins.__import__ = import_without_sdk
import ms_enclave.sandbox
builtins.__import__ = original_import
sys.modules['e2b'] = None
from ms_enclave.sandbox.manager import E2BSandboxManager
try:
    E2BSandboxManager()
except ImportError as exc:
    assert "pip install 'ms-enclave[e2b]'" in str(exc)
else:
    raise AssertionError('missing installation error')
"""
    subprocess.run([sys.executable, '-c', script], check=True, capture_output=True)


def test_e2b_does_not_require_docker_sdk() -> None:
    script = """
import sys
sys.modules['docker'] = None
from ms_enclave.sandbox.manager import E2BSandboxManager
from ms_enclave.sandbox.model import E2BSandboxConfig, SandboxType
from ms_enclave.sandbox.boxes import SandboxFactory
manager = E2BSandboxManager({'api_key': 'placeholder'})
box = SandboxFactory.create_sandbox(SandboxType.E2B, E2BSandboxConfig(template='existing'))
assert box.sandbox_type == SandboxType.E2B
"""
    subprocess.run([sys.executable, '-c', script], check=True, capture_output=True)


@pytest.mark.parametrize('error', [
    ModuleNotFoundError('SDK dependency missing', name='sdk_dependency'),
    ImportError('SDK import failed'),
])
def test_sdk_import_failure_preserves_original_error(monkeypatch: pytest.MonkeyPatch, error: ImportError) -> None:
    original_import = builtins.__import__

    def import_sdk(name, *args, **kwargs):
        if name == 'e2b':
            raise error
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', import_sdk)
    with pytest.raises(type(error)) as raised:
        connection_module.require_e2b()
    assert raised.value is error
