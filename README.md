# ms-enclave

Modularized and Stable Sandbox runtime environment

## Overview

ms-enclave is a modularized and stable sandbox runtime environment that provides secure isolated execution environments for applications. It supports multiple programming languages and frameworks, ensuring code runs safely in controlled environments with Docker-based containerization.

## Features

- 🔒 **Secure Isolation**: Complete isolation using Docker containers
- 🧩 **Modular Design**: Plugin-based architecture with extensible tools
- ⚡ **High Performance**: Optimized runtime performance with resource monitoring
- 📊 **Resource Monitoring**: Real-time CPU, memory, and resource usage tracking
- 🛡️ **Security Policies**: Configurable security policies and permission control
- 🌐 **HTTP API**: RESTful API for remote sandbox management
- 🔧 **Tool System**: Extensible tool system for different execution environments

## Requirements

- Python >= 3.9
- Operating System: Linux, macOS, or Windows with Docker support

## Installation

### Install from PyPI

```bash
pip install ms-enclave
```

### Install from Source

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
```

## Quick Start

### Basic Usage

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # Create Docker sandbox configuration
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        timeout=30,
        memory_limit='512m',
        tools_config={'python_executor': {}}
    )

    # Create and use sandbox with context manager
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # Execute Python code
        result = await sandbox.execute_tool('python_executor', {
            'code': "print('Hello from sandbox!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')"
        })
        print(f'Result: {result.output}')

asyncio.run(main())
```

### HTTP Server Usage

```python
from ms_enclave.sandbox import create_server

# Start the sandbox server
server = create_server(cleanup_interval=300)
server.run(host='127.0.0.1', port=8000)
```
or
```shell
python -m ms_enclave.run_server
```

### HTTP Manager Client

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():

    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as manager:
        # Create sandbox
        config = DockerSandboxConfig(image='python:3.11-slim', tools_config={'python_executor': {}})
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        # Execute code
        result = await manager.execute_tool(
            sandbox_id, 'python_executor',
            {'code': 'print("Hello from remote sandbox!")'}
        )
        print(result.model_dump())

asyncio.run(main())
```

## API Reference

### SandboxFactory

#### create_sandbox(sandbox_type, config)

Create a new sandbox instance.

```python
sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)
```

### Sandbox Methods

#### execute_tool(tool_name, parameters)

Execute a tool within the sandbox.

```python
result = await sandbox.execute_tool('python_executor', {
    'code': 'print("Hello World")',
    'timeout': 30
})
```

#### get_available_tools()

Get list of available tools.

```python
tools = sandbox.get_available_tools()
```

#### start() / stop() / cleanup()

Manage sandbox lifecycle.

```python
await sandbox.start()
await sandbox.stop()
await sandbox.cleanup()
```

### HttpSandboxManager

Remote sandbox management via HTTP API.

#### create_sandbox(sandbox_type, config)

```python
sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
```

#### execute_tool(sandbox_id, tool_name, parameters)

```python
result = await manager.execute_tool(sandbox_id, 'python_executor', params)
```

#### list_sandboxes(status_filter=None)

```python
sandboxes = await manager.list_sandboxes()
```

## Examples

### Advanced Python Execution

```python
async def advanced_example():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        memory_limit='1g'
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # Data processing example
        code = '''
import json
import statistics

data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
result = {
    "mean": statistics.mean(data),
    "median": statistics.median(data),
    "stdev": statistics.stdev(data)
}
print(json.dumps(result, indent=2))
'''

        result = await sandbox.execute_tool('python_executor', {'code': code})
        print(result.output)
```


### Error Handling

```python
async def error_handling_example():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        timeout=5
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # Handle syntax errors
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print("Missing quote'
        })

        if result.error:
            print(f"Error: {result.error}")
        else:
            print(f"Output: {result.output}")
```

## Development

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave

# Install dependencies
pip install -e ".[dev]"

# Run examples
python examples/usage_examples.py
python examples/server_example.py
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Contributing Steps

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run tests: `pytest`
5. Commit changes: `git commit -m 'Add amazing feature'`
6. Push to branch: `git push origin feature/amazing-feature`
7. Submit a Pull Request

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.
