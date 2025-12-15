"""Example usage of the sandbox system."""

import asyncio

from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType
from ms_enclave.sandbox.tools import ToolFactory


async def direct_sandbox_example():
    """Example using sandbox directly."""
    print('=== Direct Sandbox Example ===')

    # Create Docker sandbox configuration
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        timeout=30,
        memory_limit='512m',
        cpu_limit=1.0,
        tools_config={
            'python_executor': {}  # Enable Python executor tool
        }
    )

    # Create and use sandbox with context manager
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print(f'Created sandbox: {sandbox.id}')
        print(f'Sandbox status: {sandbox.status}')

        # Execute Python code using tool
        result = await sandbox.execute_tool('python_executor', {
            'code': "print('Hello from sandbox!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')",
            'timeout': 30
        })
        print(f'Python execution result: {result.output}')
        if result.error:
            print(f'Error: {result.error}')

        # Execute another Python script
        result = await sandbox.execute_tool('python_executor', {
            'code': '''
import os
import sys
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")
print(f"Current user: {os.getenv('USER', 'unknown')}")

# Create some data
data = [i**2 for i in range(10)]
print(f"Squares: {data}")
'''
        })
        print(f'System info result: {result.output}')

        # Get available tools
        tools = sandbox.get_available_tools()
        print(f'Available tools: {list(tools.keys())}')

        # Get sandbox info
        info = sandbox.get_info()
        print(f'Sandbox info: {info.type}, Status: {info.status}')

    print('Sandbox automatically cleaned up')


async def tool_factory_example():
    """Example using ToolFactory directly."""
    print('\n=== Tool Factory Example ===')

    # Get available tools
    available_tools = ToolFactory.get_available_tools()
    print(f'Available tools: {available_tools}')

    # Create a Python executor tool
    try:
        python_tool = ToolFactory.create_tool('python_executor')
        print(f'Created tool: {python_tool.name}')
        print(f'Tool description: {python_tool.description}')
        print(f'Tool schema: {python_tool.schema}')
        print(f'Required sandbox type: {python_tool.required_sandbox_type}')
    except Exception as e:
        print(f'Failed to create tool: {e}')


async def multiple_sandboxes_example():
    """Example using multiple sandboxes."""
    print('\n=== Multiple Sandboxes Example ===')

    config1 = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        working_dir='/workspace'
    )

    config2 = DockerSandboxConfig(
        image='python:3.9-slim',
        tools_config={'python_executor': {}},
        working_dir='/app'
    )

    # Create multiple sandboxes
    sandbox1 = SandboxFactory.create_sandbox(SandboxType.DOCKER, config1)
    sandbox2 = SandboxFactory.create_sandbox(SandboxType.DOCKER, config2)

    try:
        await sandbox1.start()
        await sandbox2.start()

        print(f'Sandbox 1: {sandbox1.id} (Python 3.11)')
        print(f'Sandbox 2: {sandbox2.id} (Python 3.9)')

        # Execute code in both sandboxes
        code = """
import sys
print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}")
print(f"Working directory: {__import__('os').getcwd()}")
"""

        result1 = await sandbox1.execute_tool('python_executor', {'code': code})
        result2 = await sandbox2.execute_tool('python_executor', {'code': code})

        print(f'Sandbox 1 result:\n{result1.output}')
        print(f'Sandbox 2 result:\n{result2.output}')

    finally:
        await sandbox1.stop()
        await sandbox1.cleanup()
        await sandbox2.stop()
        await sandbox2.cleanup()


async def error_handling_example():
    """Example demonstrating error handling."""
    print('\n=== Error Handling Example ===')

    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        timeout=5  # Short timeout for demonstration
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # Test various error scenarios

        # 1. Syntax error
        print('1. Testing syntax error...')
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print("Hello" # Missing closing parenthesis'
        })
        print(f'Syntax error result: {result.status}')
        if result.error:
            print(f'Error: {result.error[:100]}...')

        # 2. Runtime error
        print('\n2. Testing runtime error...')
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print(1/0)'  # Division by zero
        })
        print(f'Runtime error result: {result.status}')
        if result.error:
            print(f'Error: {result.error[:100]}...')

        # 3. Successful execution
        print('\n3. Testing successful execution...')
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print("This should work fine!")'
        })
        print(f'Success result: {result.status}')
        print(f'Output: {result.output.strip()}')


async def main():
    """Run all examples."""
    print('Sandbox System Examples')
    print('======================')

    # Run all examples
    await direct_sandbox_example()
    await tool_factory_example()
    await multiple_sandboxes_example()
    await error_handling_example()

    print('\n=== Examples completed ===')


if __name__ == '__main__':
    asyncio.run(main())
