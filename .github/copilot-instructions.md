# Copilot Instructions for ms-enclave

Purpose: a modular sandbox runtime around Docker with both local and HTTP-managed execution. These notes make agents productive fast.

## Big picture
- Code lives under `ms_enclave/sandbox/`:
  - `boxes/`: Sandbox implementations and factory.
    - `boxes/base.py`: `Sandbox` ABC (start/stop/cleanup, tool registry, `execute_tool`, `execute_command`); `SandboxFactory`; `@register_sandbox`.
    - `boxes/docker_sandbox.py`: Real Docker runner via `docker` SDK (image pull, container create/start, resource limits, volumes/ports, network).
    - `boxes/docker_notebook.py`: Jupyter Kernel Gateway flavor (builds `jupyter-kernel-gateway` image if missing, exposes 8888; HTTP+websocket kernel mgmt).
  - `manager/`: Orchestrators.
    - `local_manager.py`: In-process, tracks sandboxes, background cleanup loop.
    - `http_manager.py`: Talks to FastAPI server; mirrors server routes and Pydantic models.
  - `server/server.py`: FastAPI app (health, create/list/get/stop/delete sandbox, execute tool, list tools) using `LocalSandboxManager`.
  - `model/`: Pydantic configs/requests/responses/enums (e.g., `DockerSandboxConfig`, `DockerNotebookConfig`, `SandboxInfo`, `ToolResult`, `SandboxType`).
  - `tools/`: Tool framework: `Tool` ABC + `ToolFactory` + `@register_tool`; built-ins in `tools/sandbox_tools/` wired via `tools/__init__.py`.

## Dev + run
- Python >= 3.10. Install: editable dev `pip install -e ".[dev]"`; add Docker extras `pip install -e ".[docker]"`.
- Run server: `python -m ms_enclave.run_server` (default 0.0.0.0:8000). Programmatic: `from ms_enclave.sandbox import create_server; create_server().run(...)`.
- HTTP API (FastAPI):
  - POST `/sandbox/create?sandbox_type=docker` body=config
  - GET `/sandboxes` (opt `status`), GET `/sandbox/{id}`
  - POST `/sandbox/{id}/stop`, DELETE `/sandbox/{id}`
  - POST `/sandbox/tool/execute` (body `ToolExecutionRequest`), GET `/sandbox/{id}/tools`
- Local manager: `await LocalSandboxManager().create_sandbox(SandboxType.DOCKER, DockerSandboxConfig(...))` then `execute_tool('python_executor', {...})`.

## Patterns that matter
- Registration: `@register_sandbox(SandboxType.DOCKER)` for new sandboxes; `@register_tool('name')` for tools.
- Configs: Pydantic models accept typed instances or dicts (see validators in `model/config.py` for `memory_limit`, `cpu_limit`).
- Tool contract: tools expose OpenAI-style schema via `Tool.schema`; set `required_sandbox_type` and implement async `execute(sandbox_context, **kwargs)`.
- Lifecycle: sandboxes must be RUNNING to execute tools; use `async with SandboxFactory.create_sandbox(...):` or `await start()/stop()`.
- Docker gotchas: tests assume Docker daemon and images like `python:3.11-slim`; some tests reference `python-sandbox` image. Notebook flavor needs network + port 8888; `websocket-client` required.
- Cleanup: `LocalSandboxManager` auto-cleans ERROR/STOPPED >1h and any >48h.

## Extend the system
- New tool: add under `tools/sandbox_tools/`, subclass `SandboxTool`/`Tool`, set `_sandbox_type` or `required_sandbox_type`, implement `execute`, register in `tools/__init__.py`.
- New sandbox: subclass `Sandbox` in `boxes/`, implement lifecycle + `execute_command` + `get_execution_context`, register with `@register_sandbox` (extend `SandboxType` if needed).
- HTTP API changes: edit `server/server.py` and mirror in `manager/http_manager.py`.

## Code Quality

- Always use English comments
- Type hints required for all code
- Public APIs must have docstrings
- Functions must be focused and small
- Follow existing patterns exactly
- Class names in PascalCase
- Constants in UPPER_SNAKE_CASE
- Document with docstrings
- Use f-strings for formatting

## Development Philosophy

- **Simplicity**: Write simple, straightforward code
- **Readability**: Make code easy to understand
- **Performance**: Consider performance without sacrificing readability
- **Maintainability**: Write code that's easy to update
- **Testability**: Ensure code is testable
- **Reusability**: Create reusable components and functions
- **Less Code = Less Debt**: Minimize code footprint


## Coding Best Practices

- **Early Returns**: Use to avoid nested conditions
- **Descriptive Names**: Use clear variable/function names (prefix handlers with "handle")
- **Constants Over Functions**: Use constants where possible
- **DRY Code**: Don't repeat yourself
- **Functional Style**: Prefer functional, immutable approaches when not verbose
- **Minimal Changes**: Only modify code related to the task at hand
- **Function Ordering**: Define composing functions before their components
- **TODO Comments**: Mark issues in existing code with "TODO:" prefix
- **Simplicity**: Prioritize simplicity and readability over clever solutions
- **Build Iteratively** Start with minimal functionality and verify it works before adding complexity
- **Run Tests**: Test your code frequently with realistic inputs and validate outputs
- **Build Test Environments**: Create testing environments for components that are difficult to validate directly
- **Functional Code**: Use functional and stateless approaches where they improve clarity
- **Clean logic**: Keep core logic clean and push implementation details to the edges
- **File Organsiation**: Balance file organization with simplicity - use an appropriate number of files for the project scale
