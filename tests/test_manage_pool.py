"""Unit tests for LocalSandboxManager pool functionality."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ms_enclave.sandbox.manager.http_manager import HttpSandboxManager
from ms_enclave.sandbox.manager.local_manager import LocalSandboxManager
from ms_enclave.sandbox.model import (
    DockerSandboxConfig,
    SandboxInfo,
    SandboxManagerConfig,
    SandboxStatus,
    SandboxType,
    ToolResult,
)


class TestPoolInitialization(unittest.IsolatedAsyncioTestCase):
    """Test pool initialization functionality."""

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=5.0,
        )
        self.manager = LocalSandboxManager(config)
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())

    async def test_initialize_pool_creates_sandboxes(self):
        """Test that initialize_pool creates the specified number of sandboxes."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_ids = await self.manager.initialize_pool(
            pool_size=3,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        self.assertEqual(len(sandbox_ids), 3)
        self.assertEqual(len(self.manager._sandbox_pool), 3)

        # Verify all sandboxes are in IDLE status
        for sandbox_id in sandbox_ids:
            sandbox = await self.manager.get_sandbox(sandbox_id)
            self.assertEqual(sandbox.status, SandboxStatus.IDLE)

    async def test_initialize_pool_with_zero_size(self):
        """Test that pool initialization with size 0 does nothing."""
        sandbox_ids = await self.manager.initialize_pool(pool_size=0)

        self.assertEqual(len(sandbox_ids), 0)
        self.assertEqual(len(self.manager._sandbox_pool), 0)

    async def test_pool_stats_after_initialization(self):
        """Test that stats include pool information after initialization."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        stats = await self.manager.get_stats()

        self.assertEqual(stats['pool_size'], 2)
        self.assertEqual(stats['total_sandboxes'], 2)


class TestPoolExecution(unittest.IsolatedAsyncioTestCase):
    """Test pool-based tool execution."""

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=5.0,
        )
        self.manager = LocalSandboxManager(config)
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())

    async def test_execute_tool_in_pool_success(self):
        """Test successful tool execution from pool."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        result = await self.manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("hello from pool")', 'timeout': 30}
        )

        self.assertTrue(result.success)
        self.assertIn('hello from pool', result.output)

    async def test_execute_tool_in_pool_returns_sandbox(self):
        """Test that sandbox is returned to pool after execution."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_ids = await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        await self.manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("test")', 'timeout': 30}
        )

        # Sandbox should be back in pool
        self.assertEqual(len(self.manager._sandbox_pool), 1)

        # Verify sandbox is IDLE
        sandbox = await self.manager.get_sandbox(sandbox_ids[0])
        self.assertEqual(sandbox.status, SandboxStatus.IDLE)

    async def test_execute_tool_in_empty_pool_raises_error(self):
        """Test that execution fails when pool is empty."""
        with self.assertRaises(ValueError) as context:
            await self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': 'print("test")'}
            )

        self.assertIn('pool is empty', str(context.exception))

    async def test_sequential_execution_reuses_sandbox(self):
        """Test that sequential executions reuse the same sandbox."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_ids = await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Execute multiple times
        for i in range(3):
            result = await self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': f'print("execution {i}")', 'timeout': 30}
            )
            self.assertTrue(result.success)

        # Should still have same sandbox in pool
        self.assertEqual(len(self.manager._sandbox_pool), 1)
        self.assertEqual(self.manager._sandbox_pool[0], sandbox_ids[0])


class TestConcurrentPoolExecution(unittest.IsolatedAsyncioTestCase):
    """Test concurrent execution with pool."""

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=10.0,
        )
        self.manager = LocalSandboxManager(config)
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())

    async def test_concurrent_execution_within_pool_size(self):
        """Test concurrent execution when requests <= pool size."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=3,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Execute 3 concurrent requests
        tasks = [
            self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': f'print("task {i}")', 'timeout': 30}
            )
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))

        # All sandboxes should be back in pool
        self.assertEqual(len(self.manager._sandbox_pool), 3)

    async def test_concurrent_execution_exceeds_pool_size(self):
        """Test concurrent execution when requests > pool size (queuing)."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Execute 5 concurrent requests (more than pool size)
        start_time = asyncio.get_event_loop().time()
        tasks = [
            self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': f'import time; time.sleep(0.2); print("task {i}")', 'timeout': 30}
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = asyncio.get_event_loop().time() - start_time

        # All requests should complete
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.success for r in results))

        # Should take longer due to queuing
        self.assertGreater(elapsed, 0.4)

        # All sandboxes back in pool
        self.assertEqual(len(self.manager._sandbox_pool), 2)

    async def test_timeout_when_pool_exhausted(self):
        """Test timeout when all sandboxes are busy for too long."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Start one long-running task
        task1 = asyncio.create_task(
            self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': 'import time; time.sleep(5); print("done")', 'timeout': 30}
            )
        )
        await asyncio.sleep(0.2)  # Let it start

        # Try another request with short timeout
        with self.assertRaises(TimeoutError) as context:
            await self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': 'print("quick")', 'timeout': 30},
                timeout=0.5
            )

        self.assertIn('Timeout waiting for available sandbox', str(context.exception))

        # Cleanup
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass


class TestPoolFIFOBehavior(unittest.IsolatedAsyncioTestCase):
    """Test FIFO behavior of pool queue."""

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=5.0,
        )
        self.manager = LocalSandboxManager(config)
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())

    async def test_sandboxes_used_in_order(self):
        """Test that sandboxes are used in FIFO order."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_ids = await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Track order by examining pool state after each execution
        pool_snapshots = []

        for i in range(4):
            # Capture pool state before execution
            async with self.manager._pool_condition:
                pool_snapshots.append(list(self.manager._sandbox_pool))

            # Execute using pool
            result = await self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': f'print("test {i}")', 'timeout': 30}
            )
            self.assertTrue(result.success)

        # Verify FIFO pattern: first sandbox should be at front initially,
        # then cycle through
        self.assertEqual(pool_snapshots[0][0], sandbox_ids[0])
        self.assertEqual(pool_snapshots[1][0], sandbox_ids[1])
        self.assertEqual(pool_snapshots[2][0], sandbox_ids[0])
        self.assertEqual(pool_snapshots[3][0], sandbox_ids[1])


class TestPoolErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling in pool operations."""

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=5.0,
        )
        self.manager = LocalSandboxManager(config)
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())

    async def test_execute_tool_with_error_returns_sandbox(self):
        """Test that sandbox is returned even if execution fails."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Execute code that raises error
        result = await self.manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'raise ValueError("test error")', 'timeout': 30}
        )

        # Should have error but sandbox returned to pool
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertEqual(len(self.manager._sandbox_pool), 1)

    async def test_execute_tool_before_manager_start(self):
        """Test executing tool when manager not started."""
        new_manager = LocalSandboxManager()

        with self.assertRaises(ValueError) as context:
            await new_manager.execute_tool_in_pool(
                'python_executor',
                {'code': 'print("test")'}
            )

        self.assertIn('initialize_pool first', str(context.exception))


class TestPoolWithCleanup(unittest.IsolatedAsyncioTestCase):
    """Test pool behavior with cleanup operations."""

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=5.0,
        )
        self.manager = LocalSandboxManager(config)
        asyncio.run(self.manager.start())

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.manager.stop())

    async def test_cleanup_all_removes_pool_sandboxes(self):
        """Test that cleanup_all removes pool sandboxes."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        await self.manager.cleanup_all_sandboxes()

        self.assertEqual(len(self.manager._sandboxes), 0)
        # Pool still has IDs but sandboxes are gone
        self.assertEqual(len(self.manager._sandbox_pool), 2)

    async def test_pool_execution_after_partial_cleanup(self):
        """Test pool execution after some sandboxes are deleted."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_ids = await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Delete one sandbox
        await self.manager.delete_sandbox(sandbox_ids[0])

        # Should still be able to execute with remaining sandbox
        result = await self.manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("still works")', 'timeout': 30}
        )

        self.assertTrue(result.success)


class TestHttpPoolExecution(unittest.IsolatedAsyncioTestCase):
    """Test HTTP manager pool execution.

    Note: These tests require a running sandbox server at localhost:8000.
    Start the server with: python -m ms_enclave.run_server
    """

    @classmethod
    def setUpClass(cls):
        """Check if server is available."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 8000))
        sock.close()
        if result != 0:
            raise unittest.SkipTest('Server not running at localhost:8000')

    def setUp(self):
        """Set up test fixtures."""
        config = SandboxManagerConfig(
            pool_size=0,
            cleanup_interval=60,
            timeout=30.0,
            base_url='http://localhost:8000'
        )
        self.manager = HttpSandboxManager(config)

    async def asyncTearDown(self):
        """Clean up after tests."""
        if self.manager._running:
            await self.manager.stop()

    async def test_initialize_pool_via_http(self):
        """Test pool initialization via HTTP API."""
        await self.manager.start()

        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_ids = await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        self.assertEqual(len(sandbox_ids), 2)
        self.assertEqual(len(self.manager._sandbox_pool), 2)
        self.assertTrue(self.manager._pool_initialized)

        # Cleanup
        await self.manager.cleanup_all_sandboxes()

    async def test_execute_tool_in_pool_via_http(self):
        """Test tool execution in pool via HTTP API."""
        await self.manager.start()

        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        result = await self.manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("hello from http pool")', 'timeout': 30}
        )

        self.assertTrue(result.success)
        self.assertIn('hello from http pool', result.output)

        # Cleanup
        await self.manager.cleanup_all_sandboxes()

    async def test_execute_tool_in_empty_pool_via_http(self):
        """Test execution fails when pool not initialized."""
        await self.manager.start()

        with self.assertRaises(ValueError) as context:
            await self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': 'print("test")'}
            )

        self.assertIn('pool is empty', str(context.exception))

    async def test_concurrent_pool_execution_via_http(self):
        """Test concurrent execution via HTTP pool."""
        await self.manager.start()

        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=2,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Execute concurrent requests
        tasks = [
            self.manager.execute_tool_in_pool(
                'python_executor',
                {'code': f'print("task {i}")', 'timeout': 30}
            )
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))

        # Cleanup
        await self.manager.cleanup_all_sandboxes()

    async def test_pool_execution_with_error(self):
        """Test error handling in pool execution."""
        await self.manager.start()

        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        await self.manager.initialize_pool(
            pool_size=1,
            sandbox_type=SandboxType.DOCKER,
            config=config
        )

        # Execute code that raises error
        result = await self.manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'raise ValueError("test error")', 'timeout': 30}
        )

        # Should have error but complete
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

        # Cleanup
        await self.manager.cleanup_all_sandboxes()


if __name__ == '__main__':
    unittest.main()
