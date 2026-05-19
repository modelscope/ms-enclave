# 扩展开发概览

`ms-enclave` 围绕三个抽象基类组织：`Tool`、`Sandbox`、`SandboxManager`。每个基类都配套了**装饰器注册 + 工厂创建**两件套，扩展时不需要修改框架代码。

## 注册机制速查表

| 抽象 | 装饰器 | 工厂调用 |
|---|---|---|
| Tool | `@register_tool('name')` | `ToolFactory.create_tool('name', **kwargs)` |
| Sandbox | `@register_sandbox(SandboxType.XYZ)` | `SandboxFactory.create_sandbox(type, config, sandbox_id)` |
| SandboxManager | `@register_manager(SandboxManagerType.XYZ)` | `SandboxManagerFactory.create_manager(manager_type, config, **kwargs)` |

新增 Sandbox / Manager 时通常还需要在 `ms_enclave/sandbox/model` 中给 `SandboxType` 或 `SandboxManagerType` 枚举加一个新值。

## 应该扩展哪个？

| 目标 | 应该扩展 |
|---|---|
| 新增一个 LLM 可调用的能力（如 SQL 执行、HTTP 请求） | [自定义 Tool](custom-tool.md) |
| 接入一种新的隔离运行时（如 microVM、远程容器服务、本地进程） | [自定义 Sandbox](custom-sandbox.md) |
| 自己实现编排逻辑（如基于 K8s 的调度、外部数据库存沙箱元数据） | [自定义 SandboxManager](custom-manager.md) |

## 通用最佳实践

- **生命周期**：仅在 `SandboxStatus.RUNNING` 时执行工具；`start()` 中调用 `await self.initialize_tools()`。
- **兼容性**：工具通过 `required_sandbox_types` 声明可运行的沙箱类型，框架会自动按 `SandboxType.is_compatible` 过滤。返回 `None` 表示任意沙箱可用。
- **参数 Schema**：若需要严格校验，给 Tool 构造时传 `parameters`（Pydantic 模型，参见 `tools/tool_info.py`）。框架会通过 `Tool.schema` 自动输出 OpenAI 风格的 function schema。
- **从最小实现开始**：先跑通一个返回 `{"hello": "world"}` 的 demo 工具，再加复杂逻辑。
