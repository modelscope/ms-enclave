# HTTP Server

`ms-enclave` ships with a FastAPI-based HTTP service that exposes sandbox capabilities to remote callers. Use it for distributed deployments or multi-language clients.

## Starting the server

### CLI

```bash
ms-enclave server --host 0.0.0.0 --port 8000
```

### Programmatic (custom auth / cleanup)

```python
from ms_enclave.sandbox.server import create_server
from ms_enclave.sandbox.model import SandboxManagerConfig

server = create_server(config=SandboxManagerConfig(
    cleanup_interval=600,
    api_key='your-secret-key',   # optional, enables auth
))
server.run(host='0.0.0.0', port=8000)
```

## Authentication

When `api_key` is set, every request must include it via:

- HTTP header: `X-API-Key: your-secret-key`
- or query parameter: `?api_key=your-secret-key`

Otherwise the server returns `401 Unauthorized`. `HttpSandboxManager` accepts an `api_key` argument for clients.

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET`  | `/health` | Health check (with active-sandbox stats) |
| `GET`  | `/stats`  | System statistics |
| `POST` | `/sandbox/create` | Create a sandbox |
| `GET`  | `/sandboxes` | List sandboxes (optionally filter by `status`) |
| `GET`  | `/sandbox/{id}` | Get sandbox info |
| `POST` | `/sandbox/{id}/stop` | Stop a sandbox |
| `DELETE` | `/sandbox/{id}` | Delete a sandbox |
| `GET`  | `/sandbox/{id}/tools` | Get enabled tools (OpenAI schema) for a sandbox |
| `POST` | `/sandbox/tool/execute` | Execute a tool in a sandbox |
| `POST` | `/pool/initialize` | Pre-warm the sandbox pool |
| `POST` | `/pool/execute` | Borrow a sandbox from the pool and run a tool |

### Create a sandbox

```bash
curl -X POST 'http://localhost:8000/sandbox/create?sandbox_type=docker' \
  -H 'Content-Type: application/json' \
  -d '{"image":"python:3.11-slim","tools_config":{"python_executor":{}}}'
# => {"sandbox_id":"abc123"}
```

### Execute a tool

```bash
curl -X POST http://localhost:8000/sandbox/tool/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "sandbox_id": "abc123",
    "tool_name": "python_executor",
    "parameters": {"code": "print(40 + 2)"}
  }'
```

## Docker deployment

The server needs Docker access. The simplest pattern is mounting the host docker socket:

```bash
docker run -d --name ms-enclave-server \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  python:3.11-slim \
  bash -c 'pip install "ms-enclave[docker]" && ms-enclave server --host 0.0.0.0'
```

> ⚠️ Mounting the docker socket grants the container root-equivalent access to the host. Use **only on trusted networks**. For production, prefer:
> - Running the server on a dedicated host or VM
> - Putting it behind a reverse proxy (Nginx / Traefik) with HTTPS + rate limiting

## Client

Once the server is up, use [`HttpSandboxManager`](http-client.md) to call it remotely.
