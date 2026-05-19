# Deploy HTTP Server

ms-enclave ships a FastAPI-based HTTP server that exposes sandbox capabilities to remote clients — useful for distributed systems or microservice-style deployments.

## Start the server

### CLI

```bash
ms-enclave server --host 0.0.0.0 --port 8000
```

## Use HttpSandboxManager client

Operate remote sandboxes just like local ones:

```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with SandboxManagerFactory.create_manager(base_url='http://127.0.0.1:8000') as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
        print(f"Remote sandbox ID: {sandbox_id}")
        
        result = await manager.execute_tool(sandbox_id, 'python_executor', {
            'code': 'import platform; print(platform.node())'
        })
        print(f"Remote output: {result.output}")

if __name__ == '__main__':
    asyncio.run(main())
```

## API overview

- `POST /sandbox/create`: Create sandbox
- `GET /sandboxes`: List sandboxes
- `GET /sandbox/{sandbox_id}`: Get sandbox detail
- `POST /sandbox/{sandbox_id}/stop`: Stop sandbox
- `DELETE /sandbox/{sandbox_id}`: Delete sandbox
- `POST /sandbox/tool/execute`: Execute tool (Body: `ToolExecutionRequest`)
- `GET /sandbox/{sandbox_id}/tools`: List tools available in a sandbox
