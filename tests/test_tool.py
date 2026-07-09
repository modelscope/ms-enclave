"""Unit tests for the tool system functionality."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ms_enclave.sandbox.boxes.base import SandboxFactory
from ms_enclave.sandbox.model import ExecutionStatus, SandboxType
from ms_enclave.sandbox.tools import ToolFactory


class TestToolFactory(unittest.TestCase):
    """Test ToolFactory functionality."""

    def test_get_available_tools(self):
        """Test getting list of available tools."""
        available_tools = ToolFactory.get_available_tools()
        self.assertIsInstance(available_tools, list)
        self.assertGreater(len(available_tools), 0)

    def test_create_python_executor_tool(self):
        """Test creating Python executor tool."""
        tool = ToolFactory.create_tool('python_executor')

        self.assertEqual(tool.name, 'python_executor')
        self.assertIsNotNone(tool.description)
        self.assertIsNotNone(tool.schema)
        self.assertEqual(tool.required_sandbox_types, [SandboxType.DOCKER, SandboxType.VOLCENGINE])

    def test_create_unknown_tool_raises_error(self):
        """Test that creating unknown tool raises appropriate error."""
        with self.assertRaises(ValueError):
            ToolFactory.create_tool('unknown_tool')

    def test_tool_registry_not_empty(self):
        """Test that tool registry contains expected tools."""
        available_tools = ToolFactory.get_available_tools()
        self.assertIn('python_executor', available_tools)


class TestExecutorTool(unittest.IsolatedAsyncioTestCase):
    """Test executor tool functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.docker_sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER)
        asyncio.run(self.docker_sandbox.__aenter__())

    def tearDown(self):
        asyncio.run(self.docker_sandbox.__aexit__(None, None, None))

    async def test_python_executor(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('python_executor')
        )
        self.assertIn('python_executor', self.docker_sandbox.get_available_tools())

        result = await self.docker_sandbox.execute_tool(
            'python_executor', {'code': 'print("Hello, World!")'}
        )
        print(result.model_dump_json())
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)

    async def test_shell_executor(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('shell_executor')
        )
        self.assertIn('shell_executor', self.docker_sandbox.get_available_tools())

        result = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': 'echo "Hello, Shell!"'}
        )
        print(result.model_dump_json())
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertIn('Hello, Shell!', result.output)

    async def test_execute_command_timeout_wrapper_keeps_original_command(self):
        command = ['bash', '-c', 'echo wrapped']

        result = await self.docker_sandbox.execute_command(command, timeout=5)

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.command, command)
        self.assertIn('wrapped', result.stdout)

    async def test_execute_command_zero_timeout_disables_timeout(self):
        result = await self.docker_sandbox.execute_command(['bash', '-c', 'echo no-timeout'], timeout=0)

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertIn('no-timeout', result.stdout)

    async def test_shell_executor_exit_124_is_not_timeout(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('shell_executor')
        )

        result = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', 'exit 124'], 'timeout': 5}
        )

        self.assertEqual(result.status, ExecutionStatus.ERROR)

    async def test_shell_executor_sigkill_is_not_timeout(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('shell_executor')
        )

        result = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', 'kill -9 $$'], 'timeout': 5}
        )

        self.assertEqual(result.status, ExecutionStatus.ERROR)

    async def test_shell_executor_timeout_terminates_child_process(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('shell_executor')
        )
        marker = '/tmp/ms-enclave-shell-timeout-marker'

        await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'rm -f {marker}'], 'timeout': 5}
        )
        result = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'sleep 2; touch {marker}'], 'timeout': 0.3}
        )

        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        await asyncio.sleep(2.5)
        check = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'test -e {marker} && echo PRESENT || echo ABSENT']}
        )
        self.assertEqual(check.output.strip(), 'ABSENT')

    async def test_shell_executor_timeout_terminates_grandchild_process(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('shell_executor')
        )
        marker = '/tmp/ms-enclave-shell-grandchild-timeout-marker'

        await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'rm -f {marker}'], 'timeout': 5}
        )
        result = await self.docker_sandbox.execute_tool(
            'shell_executor',
            {
                'command': ['bash', '-c', f'bash -c "bash -c \\"sleep 2; touch {marker}\\" & wait"'],
                'timeout': 0.3
            }
        )

        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        await asyncio.sleep(2.5)
        check = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'test -e {marker} && echo PRESENT || echo ABSENT']}
        )
        self.assertEqual(check.output.strip(), 'ABSENT')

    async def test_python_executor_timeout_terminates_child_process(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('shell_executor')
        )
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('python_executor')
        )
        marker = '/tmp/ms-enclave-python-timeout-marker'

        await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'rm -f {marker}'], 'timeout': 5}
        )
        code = f"import os\nos.system('sleep 2; touch {marker}')\n"
        result = await self.docker_sandbox.execute_tool('python_executor', {'code': code, 'timeout': 0.3})

        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        await asyncio.sleep(2.5)
        check = await self.docker_sandbox.execute_tool(
            'shell_executor', {'command': ['bash', '-c', f'test -e {marker} && echo PRESENT || echo ABSENT']}
        )
        self.assertEqual(check.output.strip(), 'ABSENT')

    async def test_file_operation(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('file_operation')
        )
        self.assertIn('file_operation', self.docker_sandbox.get_available_tools())

        # Create a test file
        create_result = await self.docker_sandbox.execute_tool(
            'file_operation', {'operation': 'create', 'file_path': '/tmp/test_file.txt', 'content': 'Test content'}
        )
        print(create_result.model_dump_json())
        self.assertEqual(create_result.status, ExecutionStatus.SUCCESS)

        # Check if the file exists
        exists_result = await self.docker_sandbox.execute_tool(
            'file_operation', {'operation': 'exists', 'file_path': '/tmp/test_file.txt'}
        )
        print(exists_result.model_dump_json())
        self.assertEqual(exists_result.status, ExecutionStatus.SUCCESS)
        self.assertIn('exists', exists_result.output)

        # List directory contents
        list_result = await self.docker_sandbox.execute_tool(
            'file_operation', {'operation': 'list', 'file_path': '/tmp'}
        )
        print(list_result.model_dump_json())
        self.assertEqual(list_result.status, ExecutionStatus.SUCCESS)
        self.assertIn('test_file.txt', list_result.output)

        # Delete the test file
        delete_result = await self.docker_sandbox.execute_tool(
            'file_operation', {'operation': 'delete', 'file_path': '/tmp/test_file.txt'}
        )
        print(delete_result.model_dump_json())
        self.assertEqual(delete_result.status, ExecutionStatus.SUCCESS)

        # Verify deletion
        verify_delete_result = await self.docker_sandbox.execute_tool(
            'file_operation', {'operation': 'exists', 'file_path': '/tmp/test_file.txt'}
        )
        print(verify_delete_result.model_dump_json())
        self.assertEqual(verify_delete_result.status, ExecutionStatus.SUCCESS)
        self.assertIn('does not exist', verify_delete_result.output)

class TestNotebookExecutorTool(unittest.IsolatedAsyncioTestCase):
    """Test notebook executor tool functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.docker_sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER_NOTEBOOK)
        asyncio.run(self.docker_sandbox.__aenter__())

    def tearDown(self):
        asyncio.run(self.docker_sandbox.__aexit__(None, None, None))

    async def test_notebook_executor(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('notebook_executor')
        )
        self.assertIn('notebook_executor', self.docker_sandbox.get_available_tools())

        notebook_code = """a = 1
b = 2
c = a + b
print(c)"""

        result = await self.docker_sandbox.execute_tool(
            'notebook_executor', {'code': notebook_code}
        )
        print(result.model_dump_json())
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)

    async def test_notebook_executor_state_persistence(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('notebook_executor')
        )
        self.assertIn('notebook_executor', self.docker_sandbox.get_available_tools())

        notebook_code = """a = 1
b = 2
c = a + b
print(c)"""

        result = await self.docker_sandbox.execute_tool(
            'notebook_executor', {'code': notebook_code}
        )
        print(result.model_dump_json())

        result2 = await self.docker_sandbox.execute_tool(
            'notebook_executor', {'code': 'print(c)'}
        )
        print(result2.model_dump_json())
        self.assertEqual(result.output.strip(),  result2.output.strip())
        self.assertEqual(result2.status, ExecutionStatus.SUCCESS)

    async def test_notebook_executor_timeout_interrupts_kernel(self):
        self.docker_sandbox.add_tool(
            ToolFactory.create_tool('notebook_executor')
        )

        await self.docker_sandbox.execute_tool(
            'notebook_executor', {'code': "globals().pop('timeout_marker', None)"}
        )
        result = await self.docker_sandbox.execute_tool(
            'notebook_executor', {'code': "import time\ntime.sleep(5)\ntimeout_marker = 'PRESENT'", 'timeout': 1}
        )

        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        check = await self.docker_sandbox.execute_tool(
            'notebook_executor', {'code': "globals().get('timeout_marker', 'ABSENT')"}
        )
        self.assertEqual(check.status, ExecutionStatus.SUCCESS)
        self.assertIn('ABSENT', check.output)

if __name__ == '__main__':
    import asyncio
    unittest.main()
