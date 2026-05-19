# Extension Overview

`ms-enclave` is built around three abstract base classes: `Tool`, `Sandbox`, and `SandboxManager`. Each ships with a **decorator-based registry + factory** pair, so you can extend the system without modifying the framework.

## Registration cheatsheet

| Abstraction | Decorator | Factory call |
|---|---|---|
| Tool | `@register_tool('name')` | `ToolFactory.create_tool('name', **kwargs)` |
| Sandbox | `@register_sandbox(SandboxType.XYZ)` | `SandboxFactory.create_sandbox(type, config, sandbox_id)` |
| SandboxManager | `@register_manager(SandboxManagerType.XYZ)` | `SandboxManagerFactory.create_manager(manager_type, config, **kwargs)` |

When adding a new Sandbox or Manager, you usually also extend the `SandboxType` / `SandboxManagerType` enum in `ms_enclave/sandbox/model`.

## Which one should I extend?

| Goal | Extend |
|---|---|
| Add a new capability for the LLM to call (SQL, HTTP request, …) | [Custom Tool](custom-tool.md) |
| Integrate a new isolation runtime (microVM, remote container service, local process) | [Custom Sandbox](custom-sandbox.md) |
| Implement your own orchestration (K8s-based scheduling, external metadata store) | [Custom SandboxManager](custom-manager.md) |

## General best practices

- **Lifecycle**: only execute tools when `status == SandboxStatus.RUNNING`; call `await self.initialize_tools()` inside `start()`.
- **Compatibility**: tools declare allowed sandbox types via `required_sandbox_types`; the framework filters via `SandboxType.is_compatible`. Return `None` to allow any sandbox.
- **Parameter schema**: pass `parameters` (a Pydantic model from `tools/tool_info.py`) to your Tool for strict validation; the framework will surface it through `Tool.schema` as an OpenAI function definition.
- **Start small**: get a trivial tool returning `{"hello": "world"}` working first, then add complexity.
