"""Unit tests for the sandbox manager functionality."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.manager import LocalSandboxManager, SandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxStatus, SandboxType


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
