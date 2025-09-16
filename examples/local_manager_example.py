#!/usr/bin/env python3
"""Example demonstrating local sandbox manager usage with Docker Notebook."""

import asyncio
from typing import Any, Dict

from ms_enclave.sandbox.manager import HttpSandboxManager, LocalSandboxManager
from ms_enclave.sandbox.model import DockerNotebookConfig, SandboxStatus, SandboxType
from ms_enclave.utils import get_logger

logger = get_logger()


async def demonstrate_local_manager():
    """Demonstrate local manager functionality with Docker Notebook."""
    # Initialize local manager
    # manager = HttpSandboxManager(base_url='http://127.0.0.1:8000')
    manager = LocalSandboxManager(cleanup_interval=300)

    try:
        # Start the manager
        await manager.start()
        logger.info('Local manager started')

        # Get initial stats
        logger.info('=== Initial Manager Stats ===')
        initial_stats = await manager.get_stats()
        logger.info(f'Initial stats: {initial_stats}')

        # Create a Docker Notebook sandbox
        logger.info('=== Creating Docker Notebook Sandbox ===')
        config = DockerNotebookConfig(
            image='jupyter-kernel-gateway',
            tools_config={
                'notebook_executor': {}
            }
        )

        sandbox_id = await manager.create_sandbox(
            sandbox_type=SandboxType.DOCKER_NOTEBOOK,
            config=config
        )
        logger.info(f'Created notebook sandbox: {sandbox_id}')

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
        max_wait = 60
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

        # Execute notebook code - Basic Python
        logger.info('=== Executing Notebook Code - Basic Python ===')
        try:
            result = await manager.execute_tool(
                sandbox_id=sandbox_id,
                tool_name='notebook_executor',
                parameters={
                    'code': '''
import sys
import os
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

# Simple calculation
x = 10
y = 20
result = x + y
print(f"{x} + {y} = {result}")
'''
                }
            )
            logger.info(f'Notebook execution result:')
            logger.info(f'  Status: {result.status}')
            logger.info(f'  Output: {result.output}')
            if result.error:
                logger.info(f'  Error: {result.error}')
        except Exception as e:
            logger.error(f'Error executing notebook code: {e}')

        # Execute notebook code - Data Analysis
        logger.info('=== Executing Notebook Code - Data Analysis ===')
        try:
            data_analysis_code = '''
# Create and analyze some data
import json
import statistics

# Sample data
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
print(f"Original data: {data}")

# Calculate statistics
mean = statistics.mean(data)
median = statistics.median(data)
stdev = statistics.stdev(data)

results = {
    "mean": mean,
    "median": median,
    "standard_deviation": stdev,
    "min": min(data),
    "max": max(data)
}

print("Statistical Analysis:")
for key, value in results.items():
    print(f"  {key}: {value:.2f}")

# Show the results as JSON
print("\\nJSON Output:")
print(json.dumps(results, indent=2))
'''

            result = await manager.execute_tool(
                sandbox_id=sandbox_id,
                tool_name='notebook_executor',
                parameters={'code': data_analysis_code}
            )
            logger.info(f'Data analysis result:')
            logger.info(f'  Status: {result.status}')
            logger.info(f'  Output: {result.output}')
            if result.error:
                logger.info(f'  Error: {result.error}')
        except Exception as e:
            logger.error(f'Error executing data analysis code: {e}')

        # Execute notebook code - State Persistence Test
        logger.info('=== Testing State Persistence ===')
        try:
            # First execution - set variables
            result1 = await manager.execute_tool(
                sandbox_id=sandbox_id,
                tool_name='notebook_executor',
                parameters={
                    'code': '''
# Set some variables
global_var = "Hello from notebook!"
counter = 42
my_list = [1, 2, 3]

print(f"Set global_var = '{global_var}'")
print(f"Set counter = {counter}")
print(f"Set my_list = {my_list}")
'''
                }
            )
            logger.info(f'State setting result: {result1.status}')

            # Second execution - use variables from previous execution
            result2 = await manager.execute_tool(
                sandbox_id=sandbox_id,
                tool_name='notebook_executor',
                parameters={
                    'code': '''
# Use variables from previous execution
print(f"Retrieved global_var = '{global_var}'")
print(f"Retrieved counter = {counter}")
print(f"Retrieved my_list = {my_list}")

# Modify and extend
counter += 10
my_list.append(4)

print(f"Modified counter = {counter}")
print(f"Modified my_list = {my_list}")
'''
                }
            )
            logger.info(f'State persistence result: {result2.status}')
            logger.info(f'  Output: {result2.output}')

        except Exception as e:
            logger.error(f'Error testing state persistence: {e}')

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
        logger.info('=== Final Manager Stats ===')
        final_stats = await manager.get_stats()
        logger.info(f'Final stats: {final_stats}')

    except Exception as e:
        logger.error(f'Error in demonstration: {e}')
    finally:
        # Stop the manager
        await manager.stop()
        logger.info('Local manager stopped')


async def main():
    """Main example function."""
    logger.info('=== Local Sandbox Manager with Docker Notebook Example ===')

    # Demonstrate local manager functionality
    await demonstrate_local_manager()

    logger.info('=== Example Complete ===')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Example interrupted by user')
    except Exception as e:
        logger.error(f'Example failed: {e}')
        raise
