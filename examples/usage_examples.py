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
        image='python-sandbox',
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


async def advanced_python_example():
    """Example demonstrating advanced Python code execution."""
    print('\n=== Advanced Python Example ===')

    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        memory_limit='1g',
        timeout=60
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # Complex data processing example
        data_processing_code = '''
import json
import math
import statistics

# Generate sample data
data = {
    "sales": [1000, 1200, 1100, 1300, 1150, 1400, 1250],
    "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"],
    "products": {
        "A": {"price": 100, "sales": 150},
        "B": {"price": 200, "sales": 120},
        "C": {"price": 150, "sales": 200}
    }
}

# Calculate statistics
sales_mean = statistics.mean(data["sales"])
sales_median = statistics.median(data["sales"])
sales_stdev = statistics.stdev(data["sales"])

print(f"Sales Statistics:")
print(f"  Mean: ${sales_mean:.2f}")
print(f"  Median: ${sales_median:.2f}")
print(f"  Standard Deviation: ${sales_stdev:.2f}")

# Calculate total revenue per product
total_revenue = 0
print("\\nProduct Analysis:")
for product, info in data["products"].items():
    revenue = info["price"] * info["sales"]
    total_revenue += revenue
    print(f"  {product}: ${revenue:,} (${info['price']} × {info['sales']} units)")

print(f"\\nTotal Revenue: ${total_revenue:,}")

# Find best month
best_month_idx = data["sales"].index(max(data["sales"]))
print(f"Best month: {data['months'][best_month_idx]} (${max(data['sales']):,})")

# Export results
results = {
    "summary": {
        "mean_sales": sales_mean,
        "median_sales": sales_median,
        "total_revenue": total_revenue,
        "best_month": data["months"][best_month_idx]
    }
}

print(f"\\nResults JSON:")
print(json.dumps(results, indent=2))
'''

        print('Executing advanced data processing...')
        result = await sandbox.execute_tool('python_executor', {
            'code': data_processing_code,
            'timeout': 30
        })

        print(f'Data processing result:\n{result.output}')
        if result.error:
            print(f'Error: {result.error}')

        # Mathematical computations example
        math_code = '''
import math

def calculate_pi_leibniz(terms):
    """Calculate pi using Leibniz formula."""
    pi_approx = 0
    for i in range(terms):
        pi_approx += ((-1) ** i) / (2 * i + 1)
    return pi_approx * 4

def fibonacci_sequence(n):
    """Generate Fibonacci sequence."""
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    elif n == 2:
        return [0, 1]

    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    return fib

# Calculate pi approximation
pi_approx = calculate_pi_leibniz(10000)
pi_error = abs(math.pi - pi_approx)

print(f"Mathematical Computations:")
print(f"  Pi approximation: {pi_approx:.10f}")
print(f"  Actual Pi: {math.pi:.10f}")
print(f"  Error: {pi_error:.10f}")

# Generate Fibonacci sequence
fib_seq = fibonacci_sequence(20)
print(f"\\nFibonacci sequence (first 20): {fib_seq}")

# Golden ratio approximation from Fibonacci
if len(fib_seq) > 1:
    golden_ratio = fib_seq[-1] / fib_seq[-2]
    actual_golden = (1 + math.sqrt(5)) / 2
    print(f"\\nGolden ratio approximation: {golden_ratio:.10f}")
    print(f"Actual golden ratio: {actual_golden:.10f}")
    print(f"Error: {abs(actual_golden - golden_ratio):.10f}")
'''

        print('\nExecuting mathematical computations...')
        result = await sandbox.execute_tool('python_executor', {
            'code': math_code,
            'timeout': 30
        })

        print(f'Mathematical result:\n{result.output}')
        if result.error:
            print(f'Error: {result.error}')


async def persistent_state_example():
    """Example showing persistent state across multiple executions."""
    print('\n=== Persistent State Example ===')

    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # First execution - create variables
        result1 = await sandbox.execute_tool('python_executor', {
            'code': '''
# Initialize some data
counter = 0
data_store = {}
user_sessions = []

def add_user_session(user_id, action):
    global counter
    counter += 1
    session = {
        "id": counter,
        "user_id": user_id,
        "action": action,
        "timestamp": f"2024-01-{counter:02d}"
    }
    user_sessions.append(session)
    return session

# Add some sessions
add_user_session("user1", "login")
add_user_session("user2", "view_page")
add_user_session("user1", "purchase")

print(f"Initialized. Counter: {counter}")
print(f"Sessions: {len(user_sessions)}")
'''
        })
        print(f'Initialization result:\n{result1.output}')

        # Second execution - use existing variables
        result2 = await sandbox.execute_tool('python_executor', {
            'code': '''
# Continue from previous state
print(f"Current counter: {counter}")
print(f"Existing sessions: {len(user_sessions)}")

# Add more sessions
add_user_session("user3", "register")
add_user_session("user2", "logout")

# Analyze data
user_actions = {}
for session in user_sessions:
    user_id = session["user_id"]
    action = session["action"]

    if user_id not in user_actions:
        user_actions[user_id] = []
    user_actions[user_id].append(action)

print("\\nUser Activity Summary:")
for user_id, actions in user_actions.items():
    print(f"  {user_id}: {', '.join(actions)}")

print(f"\\nTotal sessions: {len(user_sessions)}")
print(f"Final counter: {counter}")
'''
        })
        print(f'Analysis result:\n{result2.output}')

        # Third execution - verify persistence
        result3 = await sandbox.execute_tool('python_executor', {
            'code': '''
# Verify state is still available
print(f"State verification:")
print(f"  Counter value: {counter}")
print(f"  Total sessions: {len(user_sessions)}")
print(f"  Data store keys: {list(data_store.keys())}")

# Show all session data
print("\\nAll sessions:")
for session in user_sessions:
    print(f"  #{session['id']}: {session['user_id']} -> {session['action']} ({session['timestamp']})")
'''
        })
        print(f'Verification result:\n{result3.output}')


async def main():
    """Run all examples."""
    print('Sandbox System Examples')
    print('======================')

    # Run all examples
    await direct_sandbox_example()
    await tool_factory_example()
    await multiple_sandboxes_example()
    await error_handling_example()
    await advanced_python_example()
    await persistent_state_example()

    print('\n=== Examples completed ===')


if __name__ == '__main__':
    asyncio.run(main())
