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
        self.assertIn(sandbox.status, [SandboxStatus.STOPPED, SandboxStatus.STOPPING])


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

    async def test_cleanup_all_sandboxes(self):
        """Test cleaning up all sandboxes."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # Create multiple sandboxes
        sandbox_ids = []
        for i in range(2):
            sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)
            sandbox_ids.append(sandbox_id)

        # Cleanup all
        await self.manager.cleanup_all()

        self.assertEqual(len(self.manager.sandboxes), 0)
        for sandbox_id in sandbox_ids:
            self.assertNotIn(sandbox_id, self.manager.sandboxes)


class TestSandboxManagerConcurrency(unittest.IsolatedAsyncioTestCase):
    """Test concurrent operations with SandboxManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = SandboxManager()

    async def test_concurrent_sandbox_creation(self):
        """Test creating multiple sandboxes concurrently."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # Create sandboxes concurrently
        tasks = [
            self.manager.create_sandbox(SandboxType.DOCKER, config)
            for _ in range(3)
        ]

        sandbox_ids = await asyncio.gather(*tasks)

        # Verify all sandboxes were created
        self.assertEqual(len(sandbox_ids), 3)
        self.assertEqual(len(set(sandbox_ids)), 3)  # All unique IDs

        # Cleanup
        cleanup_tasks = [
            self.manager.cleanup_sandbox(sandbox_id)
            for sandbox_id in sandbox_ids
        ]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    async def test_concurrent_tool_execution(self):
        """Test executing tools concurrently in different sandboxes."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # Create sandboxes
        sandbox_ids = await asyncio.gather(*[
            self.manager.create_sandbox(SandboxType.DOCKER, config)
            for _ in range(2)
        ])

        # Execute tools concurrently
        tasks = [
            self.manager.execute_tool(
                sandbox_ids[0],
                'python_executor',
                {'code': 'print("Sandbox 1")', 'timeout': 30}
            ),
            self.manager.execute_tool(
                sandbox_ids[1],
                'python_executor',
                {'code': 'print("Sandbox 2")', 'timeout': 30}
            )
        ]

        results = await asyncio.gather(*tasks)

        # Verify results
        self.assertEqual(len(results), 2)
        self.assertIn('Sandbox 1', results[0].output)
        self.assertIn('Sandbox 2', results[1].output)

        # Cleanup
        await asyncio.gather(*[
            self.manager.cleanup_sandbox(sandbox_id)
            for sandbox_id in sandbox_ids
        ], return_exceptions=True)


class TestSandboxManagerErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling in SandboxManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = SandboxManager()
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Tear down test fixtures."""
        asyncio.run(self.manager.stop())

    async def test_invalid_sandbox_type(self):
        """Test creating sandbox with invalid type."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        with self.assertRaises(ValueError):
            await self.manager.create_sandbox('invalid_type', config)

    async def test_stop_nonexistent_sandbox(self):
        """Test stopping non-existent sandbox."""
        with self.assertRaises(ValueError):
            await self.manager.stop_sandbox('nonexistent-id')

    async def test_cleanup_nonexistent_sandbox(self):
        """Test cleaning up non-existent sandbox."""
        with self.assertRaises(ValueError):
            await self.manager.cleanup_sandbox('nonexistent-id')

    async def test_execute_tool_with_invalid_tool(self):
        """Test executing invalid tool."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)

        with self.assertRaises(ValueError):
            await self.manager.execute_tool(
                sandbox_id,
                'nonexistent_tool',
                {'param': 'value'}
            )

        # Cleanup



class TestSandboxManagerConfiguration(unittest.IsolatedAsyncioTestCase):
    """Test SandboxManager with different configurations."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = SandboxManager()

    async def test_different_docker_configurations(self):
        """Test creating sandboxes with different Docker configurations."""
        configs = [
            DockerSandboxConfig(
                image='python:3.11-slim',
                tools_config={'python_executor': {}},
                memory_limit='256m'
            ),
            DockerSandboxConfig(
                image='python:3.9-slim',
                tools_config={'python_executor': {}},
                memory_limit='512m',
                timeout=60
            )
        ]

        sandbox_ids = []
        for config in configs:
            sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)
            sandbox_ids.append(sandbox_id)

        # Verify different configurations
        self.assertEqual(len(sandbox_ids), 2)
        self.assertNotEqual(sandbox_ids[0], sandbox_ids[1])

        # Test execution in both
        for sandbox_id in sandbox_ids:
            result = await self.manager.execute_tool(
                sandbox_id,
                'python_executor',
                {'code': 'print("Config test")', 'timeout': 30}
            )
            self.assertIn('Config test', result.output)


    async def test_sandbox_with_multiple_tools(self):
        """Test sandbox with multiple tool configurations."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={
                'python_executor': {},
                # Add other tools as they become available
            }
        )

        sandbox_id = await self.manager.create_sandbox(SandboxType.DOCKER, config)
        sandbox = self.manager.get_sandbox(sandbox_id)

        # Verify tools are available
        available_tools = sandbox.get_available_tools()
        self.assertIn('python_executor', available_tools)


if __name__ == '__main__':
    unittest.main()
