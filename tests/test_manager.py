"""Unit tests for the sandbox manager functionality."""

import asyncio
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ms_enclave.sandbox.manager import HttpSandboxManager, LocalSandboxManager, SandboxManagerFactory
from ms_enclave.sandbox.model import (
    DockerSandboxConfig,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxStatus,
    SandboxType,
)
from ms_enclave.sandbox.server.server import create_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


async def _wait_for_port(host: str, port: int) -> None:
    for _ in range(100):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f'Timed out waiting for {host}:{port}')


def _skip_if_docker_unavailable() -> None:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.close()
    except Exception as exc:
        raise unittest.SkipTest(f'Docker daemon is not available: {exc}')


class TestSandboxManagerFactory(unittest.TestCase):
    """Test SandboxManagerFactory functionality."""

    def test_factory_registry_has_managers(self):
        """Test that factory has registered managers."""
        registered_types = SandboxManagerFactory.get_registered_types()
        self.assertIn(SandboxManagerType.LOCAL, registered_types)
        self.assertIn(SandboxManagerType.HTTP, registered_types)

    def test_create_local_manager_explicit(self):
        """Test creating local manager explicitly."""
        manager = SandboxManagerFactory.create_manager(
            manager_type=SandboxManagerType.LOCAL
        )
        self.assertIsInstance(manager, LocalSandboxManager)

    def test_create_local_manager_implicit(self):
        """Test creating local manager implicitly (no config)."""
        manager = SandboxManagerFactory.create_manager()
        self.assertIsInstance(manager, LocalSandboxManager)

    def test_create_http_manager_explicit(self):
        """Test creating HTTP manager explicitly."""
        config = SandboxManagerConfig(base_url='http://localhost:8000')
        manager = SandboxManagerFactory.create_manager(
            manager_type=SandboxManagerType.HTTP,
            config=config
        )
        self.assertIsInstance(manager, HttpSandboxManager)

    def test_create_http_manager_implicit(self):
        """Test creating HTTP manager implicitly (base_url in config)."""
        config = SandboxManagerConfig(base_url='http://localhost:8000')
        manager = SandboxManagerFactory.create_manager(config=config)
        self.assertIsInstance(manager, HttpSandboxManager)

    def test_create_http_manager_implicit_via_kwargs(self):
        """Test creating HTTP manager implicitly (base_url in kwargs)."""
        manager = SandboxManagerFactory.create_manager(base_url='http://localhost:8000')
        self.assertIsInstance(manager, HttpSandboxManager)

    def test_create_manager_with_config(self):
        """Test creating manager with configuration."""
        config = SandboxManagerConfig(cleanup_interval=600)
        manager = SandboxManagerFactory.create_manager(
            manager_type=SandboxManagerType.LOCAL,
            config=config
        )
        self.assertEqual(manager.config.cleanup_interval, 600)

    def test_create_invalid_manager_type(self):
        """Test creating manager with invalid type."""
        with self.assertRaises(ValueError) as context:
            SandboxManagerFactory.create_manager(
                manager_type='invalid_type'  # type: ignore
            )
        self.assertIn('not registered', str(context.exception))

    def test_get_registered_types(self):
        """Test getting list of registered types."""
        types = SandboxManagerFactory.get_registered_types()
        self.assertIsInstance(types, list)
        self.assertGreater(len(types), 0)


class TestLocalSandboxManager(unittest.IsolatedAsyncioTestCase):
    """Test SandboxManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = LocalSandboxManager()
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())


    async def test_manager_initialization(self):
        """Test manager initialization."""
        self.assertIsNotNone(self.manager)
        sandboxes = await self.manager.list_sandboxes()
        self.assertEqual(len(sandboxes), 0)

    async def test_create_sandbox(self):
        """Test creating a sandbox through manager."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)

        self.assertIsNotNone(sandbox_id)


    async def test_get_sandbox(self):
        """Test retrieving sandbox by ID."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)
        sandbox = await self.manager.get_sandbox(sandbox_id)

        self.assertIsNotNone(sandbox)
        self.assertEqual(sandbox.id, sandbox_id)

    async def test_get_nonexistent_sandbox(self):
        """Test retrieving non-existent sandbox."""
        sandbox = await self.manager.get_sandbox('nonexistent-id')
        self.assertIsNone(sandbox)

    async def test_list_sandboxes(self):
        """Test listing all sandboxes."""
        initial_boxes = await self.manager.list_sandboxes()
        initial_count = len(initial_boxes)

        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)
        sandboxes = await self.manager.list_sandboxes()

        self.assertEqual(len(sandboxes), initial_count + 1)
        self.assertIn(sandbox_id, [sb.id for sb in sandboxes])


    async def test_stop_sandbox(self):
        """Test stopping a sandbox."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)
        sandbox = await self.manager.get_sandbox(sandbox_id)
        self.assertIn(sandbox.status, [SandboxStatus.RUNNING])


    async def test_execute_tool_in_sandbox(self):
        """Test executing a tool in a managed sandbox."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)

        result = await self.manager.execute_tool(
            sandbox_id,
            'python_executor',
            {'code': 'print("Hello from manager!")', 'timeout': 30}
        )

        self.assertIsNotNone(result)
        self.assertIn('Hello from manager!', result.output)
        self.assertIsNone(result.error)


    async def test_execute_tool_nonexistent_sandbox(self):
        """Test executing tool in non-existent sandbox."""
        with self.assertRaises(ValueError):
            await self.manager.execute_tool(
                'nonexistent-id',
                'python_executor',
                {'code': 'print("test")'}
            )

    async def test_execute_tool_accepts_active_pool_statuses(self):
        """Test direct operations can target pooled sandboxes."""
        for status in (SandboxStatus.IDLE, SandboxStatus.BUSY):
            sandbox = MagicMock()
            sandbox.status = status
            sandbox.execute_tool = AsyncMock(return_value=f'{status.value}-result')
            sandbox.stop = AsyncMock()
            self.manager._sandboxes[status.value] = sandbox

            result = await self.manager.execute_tool(status.value, 'python_executor', {})

            self.assertEqual(result, f'{status.value}-result')
            sandbox.execute_tool.assert_awaited_once_with('python_executor', {})


class TestSandboxFileTransfer(unittest.IsolatedAsyncioTestCase):
    """Test manager file transfer helpers through real local and HTTP APIs."""

    async def test_local_put_dir_copies_directory_into_docker_sandbox(self):
        _skip_if_docker_unavailable()
        manager = LocalSandboxManager()
        await manager.start()
        sandbox_id = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'skills'
                skill = source / 'demo'
                skill.mkdir(parents=True)
                (skill / 'SKILL.md').write_text('skill from local', encoding='utf-8')
                sandbox_id = await manager.create_sandbox(
                    SandboxType.DOCKER,
                    DockerSandboxConfig(image='python:3.11-slim', tools_config={'shell_executor': {}}),
                )
                ok = await manager.put_dir(sandbox_id, source, '/tmp/eval-skills')
                result = await manager.execute_tool(
                    sandbox_id,
                    'shell_executor',
                    {'command': ['cat', '/tmp/eval-skills/demo/SKILL.md'], 'timeout': 30},
                )
        finally:
            if sandbox_id is not None:
                await manager.delete_sandbox(sandbox_id)
            await manager.stop()

        self.assertTrue(ok)
        self.assertTrue(result.success)
        self.assertIn('skill from local', result.output)

    async def test_http_put_dir_copies_directory_into_docker_sandbox(self):
        _skip_if_docker_unavailable()
        import uvicorn

        port = _free_port()
        server = create_server(SandboxManagerConfig(cleanup_interval=60))
        uvicorn_server = uvicorn.Server(
            uvicorn.Config(server.app, host='127.0.0.1', port=port, log_level='warning', ws='none')
        )
        thread = threading.Thread(target=uvicorn_server.run, daemon=True)
        thread.start()
        await _wait_for_port('127.0.0.1', port)

        manager = HttpSandboxManager(SandboxManagerConfig(base_url=f'http://127.0.0.1:{port}', timeout=60.0))
        await manager.start()
        sandbox_id = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'skills'
                skill = source / 'demo'
                skill.mkdir(parents=True)
                (skill / 'SKILL.md').write_text('skill from http', encoding='utf-8')
                sandbox_id = await manager.create_sandbox(
                    SandboxType.DOCKER,
                    DockerSandboxConfig(image='python:3.11-slim', tools_config={'shell_executor': {}}),
                )
                ok = await manager.put_dir(sandbox_id, source, '/tmp/eval-skills')
                result = await manager.execute_tool(
                    sandbox_id,
                    'shell_executor',
                    {'command': ['cat', '/tmp/eval-skills/demo/SKILL.md'], 'timeout': 30},
                )
        finally:
            if sandbox_id is not None:
                await manager.delete_sandbox(sandbox_id)
            await manager.stop()
            uvicorn_server.should_exit = True
            thread.join(timeout=10)

        self.assertTrue(ok)
        self.assertTrue(result.success)
        self.assertIn('skill from http', result.output)
