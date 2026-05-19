# API 概览

本章节通过 mkdocstrings 从源码自动生成 API 文档，涵盖核心接口与工厂类：

- 管理器：`SandboxManager`、`SandboxManagerFactory`
- 沙箱：`Sandbox`、`SandboxFactory`
- 工具：`Tool`、`ToolFactory`
- 配置：`SandboxManagerConfig`、`SandboxConfig`、`DockerSandboxConfig`、`DockerNotebookConfig`、`VolcengineSandboxConfig`、`VolcengineSandboxManagerConfig`、`ToolConfig` 等
- 数据模型：请求/响应模型（`ExecuteCodeRequest`、`ToolResult`、`SandboxInfo` 等）与枚举类型（`SandboxStatus`、`SandboxType`、`ExecutionStatus` 等）

使用方式：页面中的签名、参数与返回值来自源码的类型注解与文档字符串，请以源码为准。

> 提示：若页面未展示某些类/函数，请确认其 docstring 是否完善，以及模块是否包含在 mkdocs 的 `handlers.python.paths` 配置搜索路径中。
