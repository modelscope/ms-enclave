"""Unit tests for the sandbox system functionality."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxStatus, SandboxType
from ms_enclave.sandbox.tools import ToolFactory


class TestSandboxBasicFunctionality(unittest.IsolatedAsyncioTestCase):
    """Test basic sandbox functionality."""

    async def test_direct_sandbox_creation_and_execution(self):
        """Test direct sandbox creation and Python code execution."""
        # Create Docker sandbox configuration
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            timeout=30,
            memory_limit='512m',
            cpu_limit=1.0,
            tools_config={
                'python_executor': {}
            }
        )

        # Create and use sandbox with context manager
        async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
            # Verify sandbox creation
            self.assertIsNotNone(sandbox.id)
            self.assertIsNotNone(sandbox.status)

            # Execute simple Python code
            result = await sandbox.execute_tool('python_executor', {
                'code': "print('Hello from sandbox!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')",
                'timeout': 30
            })

            # Verify execution result
            self.assertIsNotNone(result.output)
            self.assertIn('Hello from sandbox!', result.output)
            self.assertIn('2 + 2 = 4', result.output)
            self.assertIsNone(result.error)

    async def test_sandbox_system_info_execution(self):
        """Test executing system information commands in sandbox."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
            # Execute system info script
            result = await sandbox.execute_tool('python_executor', {
                'code': '''
import os
import sys
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")
print(f"Current user: {os.getenv('USER', 'unknown')}")

# Create some data
data = [i**2 for i in range(5)]
print(f"Squares: {data}")
'''
            })

            # Verify system info results
            self.assertIsNotNone(result.output)
            self.assertIn('Python version:', result.output)
            self.assertIn('Working directory:', result.output)
            self.assertIn('Squares: [0, 1, 4, 9, 16]', result.output)

    async def test_sandbox_available_tools(self):
        """Test getting available tools from sandbox."""
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
            # Get available tools
            tools = sandbox.get_available_tools()
            self.assertIsInstance(tools, dict)
            self.assertIn('python_executor', tools)

            # Get sandbox info
            info = sandbox.get_info()
            self.assertEqual(info.type, SandboxType.DOCKER)
            self.assertIsNotNone(info.status)



if __name__ == '__main__':
    unittest.main()
