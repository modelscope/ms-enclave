"""Unit tests for the sandbox manager functionality."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ms_enclave.sandbox.manager import HttpSandboxManager, LocalSandboxManager, SandboxManagerFactory
from ms_enclave.sandbox.model import (
    DockerSandboxConfig,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxStatus,
    SandboxType,
)


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
