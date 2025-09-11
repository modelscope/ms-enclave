#!/usr/bin/env python3
"""Example demonstrating sandbox server startup and HTTP manager usage."""

import asyncio
import threading
from typing import Any, Dict

from ms_enclave.sandbox import create_server
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxStatus, SandboxType
from ms_enclave.utils import get_logger

logger = get_logger()


def start_server_in_thread():
    """Start the sandbox server in a separate thread."""
    logger.info('Starting sandbox server in background thread...')
    server = create_server(cleanup_interval=300)
    server.run(host='127.0.0.1', port=8000, log_level='info')


async def wait_for_server(base_url: str, max_attempts: int = 30, delay: float = 1.0) -> bool:
    """Wait for server to be ready."""
    import aiohttp

    for attempt in range(max_attempts):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{base_url}/health') as response:
                    if response.status == 200:
                        logger.info('Server is ready!')
                        return True
        except:
            pass

        logger.info(f'Waiting for server... (attempt {attempt + 1}/{max_attempts})')
        await asyncio.sleep(delay)

    return False


async def demonstrate_http_manager():
    """Demonstrate HTTP manager functionality."""
    # Initialize HTTP manager
    base_url = 'http://127.0.0.1:8000'
    manager = HttpSandboxManager(base_url=base_url, timeout=30)

    try:
        # Start the manager
        await manager.start()
        logger.info('HTTP manager started')

        # Health check
        logger.info('=== Health Check ===')
        health = await manager.health_check()
        logger.info(f'Health status: {health}')

        # Get server stats
        logger.info('=== Server Stats ===')
        server_stats = await manager.get_stats()
        logger.info(f'Server stats: {server_stats}')

        # Create a Docker sandbox
        logger.info('=== Creating Docker Sandbox ===')
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={
                'shell_executor': {},
                'python_executor': {}
            }
        )

        sandbox_id = await manager.create_sandbox(
            sandbox_type=SandboxType.DOCKER,
            config=config
        )
        logger.info(f'Created sandbox: {sandbox_id}')

        # Get sandbox info
        logger.info('=== Getting Sandbox Info ===')
        sandbox_info = await manager.get_sandbox_info(sandbox_id)
        if sandbox_info:
            logger.info(f'Sandbox info: {sandbox_info.model_dump_json()}')
        else:
            logger.error('Failed to get sandbox info')
            return

        # List all sandboxes
        logger.info('=== Listing All Sandboxes ===')
        sandboxes = await manager.list_sandboxes()
        logger.info(f'Total sandboxes: {len(sandboxes)}')
        for sb in sandboxes:
            logger.info(f'  - {sb.id} ({sb.status}) - {sb.type}')

        # Wait for sandbox to be running
        logger.info('=== Waiting for Sandbox to be Ready ===')
        max_wait = 30
        for i in range(max_wait):
            info = await manager.get_sandbox_info(sandbox_id)
            if info and info.status == SandboxStatus.RUNNING:
                logger.info('Sandbox is running!')
                break
            elif info and info.status == SandboxStatus.ERROR:
                logger.error('Sandbox failed to start')
                break
            logger.info(f'Waiting for sandbox to start... ({i+1}/{max_wait})')
            await asyncio.sleep(2)

        # Get available tools
        logger.info('=== Getting Available Tools ===')
        try:
            tools = await manager.get_sandbox_tools(sandbox_id)
            logger.info(f'Available tools: {tools}')
        except Exception as e:
            logger.error(f'Error getting tools: {e}')

        # Execute a tool (bash command)
        logger.info('=== Executing Tool - Bash Command ===')
        try:
            result = await manager.execute_tool(
                sandbox_id=sandbox_id,
                tool_name='shell_executor',
                parameters={
                    'command': "echo 'Hello from sandbox!' && python --version && pwd && ls -la"
                }
            )
            logger.info(f'Tool execution result:')
            logger.info(f'  Status: {result.status}')
            logger.info(f'  Output: {result.output}')
            if result.error:
                logger.info(f'  Error: {result.error}')
        except Exception as e:
            logger.error(f'Error executing tool: {e}')

        # Execute Python code
        logger.info('=== Executing Tool - Python Code ===')
        try:
            python_code = """
import sys
import os
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Environment variables:")
for key, value in os.environ.items():
    if 'PYTHON' in key:
        print(f"  {key}: {value}")
"""

            result = await manager.execute_tool(
                sandbox_id=sandbox_id,
                tool_name='python_executor',
                parameters={'code': python_code}
            )
            logger.info(f'Python execution result:')
            logger.info(f'  Status: {result.status}')
            logger.info(f'  Output: {result.output}')
            if result.error:
                logger.info(f'  Error: {result.error}')
        except Exception as e:
            logger.error(f'Error executing Python code: {e}')

        # List sandboxes with status filter
        logger.info('=== Listing Running Sandboxes ===')
        running_sandboxes = await manager.list_sandboxes(status_filter=SandboxStatus.RUNNING)
        logger.info(f'Running sandboxes: {len(running_sandboxes)}')

        # Clean up - delete the sandbox
        logger.info('=== Cleaning Up ===')
        success = await manager.delete_sandbox(sandbox_id)
        if success:
            logger.info(f'Successfully deleted sandbox {sandbox_id}')
        else:
            logger.error(f'Failed to delete sandbox {sandbox_id}')

        # Final stats
        logger.info('=== Final Server Stats ===')
        final_stats = await manager.get_stats()
        logger.info(f'Final server stats: {final_stats}')

    except Exception as e:
        logger.error(f'Error in demonstration: {e}')
    finally:
        # Stop the manager
        await manager.stop()
        logger.info('HTTP manager stopped')


async def main():
    """Main example function."""
    logger.info('=== Sandbox Server and HTTP Manager Example ===')

    # Start server in background thread
    server_thread = threading.Thread(target=start_server_in_thread, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    base_url = 'http://127.0.0.1:8000'
    if not await wait_for_server(base_url):
        logger.error('Server failed to start within timeout')
        return

    # Demonstrate HTTP manager functionality
    await demonstrate_http_manager()

    logger.info('=== Example Complete ===')

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Example interrupted by user')
    except Exception as e:
        logger.error(f'Example failed: {e}')
        raise
