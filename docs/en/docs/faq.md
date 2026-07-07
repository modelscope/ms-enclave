# FAQ & Troubleshooting

## Installation & environment

### Q: After `pip install ms-enclave`, calls fail with `docker` module missing.
A: The base install doesn't include the Docker SDK. Install the extra:

```bash
pip install 'ms-enclave[docker]'
```

### Q: On macOS / Apple Silicon, pulled images are amd64 and run slowly or fail.
A: Specify the platform on `DockerSandboxConfig`, or pick an arm64 image:

```python
DockerSandboxConfig(image='python:3.11-slim', platform='linux/arm64')
```

### Q: Docker reports `permission denied while trying to connect to the Docker daemon socket`.
A: Your user can't access `/var/run/docker.sock`. On Linux, add the user to the `docker` group:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Or run with `sudo` (not recommended).

## Sandbox usage

### Q: `execute_tool` raises `Tool 'xxx' not found`.
A: You forgot to declare the tool in `tools_config`. **Only declared tools get registered.**

```python
DockerSandboxConfig(tools_config={'python_executor': {}, 'shell_executor': {}})
```

### Q: A command timed out.
A: Default `timeout=30` seconds. Pass a larger `timeout` to the tool call, or set a global default via `SandboxConfig.timeout`.

### Q: Containers leak.
A: Common causes:

- `SandboxFactory` used without `async with`, and `await sandbox.stop()` forgotten
- The process was SIGKILL'd before cleanup

Prefer `LocalSandboxManager`: it ships with a background cleanup coroutine that reclaims timed-out (default 48h) or errored sandboxes.

Or clean up manually:

```bash
docker ps -a --filter "label=ms-enclave" -q | xargs -r docker rm -f
```

### Q: How do I preserve Python variables across calls?
A: Use the [Notebook sandbox](guides/notebook-sandbox.md) (`SandboxType.DOCKER_NOTEBOOK` + `notebook_executor`), which keeps a single Jupyter kernel. `python_executor` is stateless.

## Notebook sandbox

### Q: `Jupyter Kernel Gateway failed to become ready within 30 seconds`.
A: Usually the first-time image build is slow (downloading jupyter-kernel-gateway and friends). Retry after the build, or pre-build an image tagged `jupyter-kernel-gateway`.

### Q: `websocket-client package is required`.
A: Install extra client deps:

```bash
pip install websocket-client requests
```

### Q: Port 8888 in use.
A: Change `DockerNotebookConfig.port` to a free port.

## HTTP server

### Q: All requests return 401 Unauthorized.
A: The server has `api_key` enabled. Clients must include:

- Header: `X-API-Key: your-secret-key`
- or `HttpSandboxManager(base_url=..., api_key='...')`

### Q: Server image pull is slow and the client times out.
A: The default client HTTP timeout is short. Increase it:

```python
HttpSandboxManager(base_url='...', timeout=120)
```

Or pre-`docker pull` images on the server.

## Volcengine cloud sandbox

### Q: Connection refused.
A: Check that SandboxFusion is running (`docker run -p 8080:8080 ...`) and the `base_url` is correct (default `http://localhost:8080`).

### Q: Variables disappear between calls.
A: The Volcengine sandbox is **stateless** — every `execute_tool` is an independent execution. For state, use a Docker or DockerNotebook sandbox.

## Performance

### Q: Sandbox startup is slow.
A:

- Pre-`docker pull` images to avoid live downloads
- Use a [sandbox pool](guides/sandbox-pool.md) for warm-up
- Build a slim base image (only the dependencies you need)

### Q: Some requests time out under high concurrency.
A:

- Increase `pool_size`, set a sensible `timeout` so over-limit requests fail fast
- Monitor `get_stats()` for active counts / pool usage to find bottlenecks

## Still stuck?

File an issue at <https://github.com/modelscope/ms-enclave/issues> with:

- A minimal reproducer
- Output of `pip show ms-enclave`
- Output of `docker version`
- The full error traceback
