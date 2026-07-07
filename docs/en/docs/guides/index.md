# Usage Guides Overview

`ms-enclave` exposes four typical entry points for different integration needs. This section is organized by **what you want to do** — pick an entry point from the table below, then jump to the matching guide.

## Which entry should I use?

| Scenario | Recommended entry | Guide |
|---|---|---|
| Scripts / unit tests, run-and-done | `SandboxFactory` | [Using a sandbox directly](sandbox-factory.md) |
| Manage many sandboxes in one app, with background cleanup | `LocalSandboxManager` | [Local manager](local-manager.md) |
| High-concurrency service, need warm-up & pooling | `Sandbox Pool` | [Sandbox pool](sandbox-pool.md) |
| Sandbox runs on a separate server | `HttpSandboxManager` | [HTTP client](../deployment/http-client.md) |
| Let the LLM choose which tool to call | `Manager` + OpenAI Tools | [LLM Agent integration](agent-integration.md) |

Rule of thumb:

- **Script / Notebook** → `SandboxFactory`
- **Web backend / task scheduler** → `LocalSandboxManager` (add pool when needed)
- **Distributed deployment** → run the HTTP service on a server, use `HttpSandboxManager` on clients

## Unified factory entry

To avoid hard-coding "local vs. remote" in business code, use `SandboxManagerFactory`:

- pass `base_url` → returns `HttpSandboxManager`
- omit `base_url` → returns `LocalSandboxManager`

```python
from ms_enclave.sandbox.manager import SandboxManagerFactory

# Local
async with SandboxManagerFactory.create_manager() as manager:
    ...

# Remote
async with SandboxManagerFactory.create_manager(base_url='http://server:8000') as manager:
    ...
```

## Common topics

- [Built-in tools](builtin-tools.md): `python_executor` / `shell_executor` / `file_operation` parameters and returns
- [Installing third-party dependencies in a sandbox](install-deps.md)
- [Mounting host directories](host-volumes.md)
- [Notebook sandbox (preserves variable state)](notebook-sandbox.md)
- [LLM Agent / OpenAI Tools integration](agent-integration.md)
