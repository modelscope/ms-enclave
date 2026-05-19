# ms-enclave 中文文档

![logo](./_static/logo.png)

**ms-enclave** 是一个模块化、稳定的沙箱运行时，为应用程序提供安全的隔离执行环境。基于 Docker 实现强隔离，配套本地 / HTTP 管理器和可扩展工具系统，帮助你在受控环境中安全、高效地执行代码（包括 LLM 生成的代码）。

## 主要特性

- 🔒 **安全隔离**：Docker 容器隔离 + 资源限制
- 🧩 **模块化**：沙箱、工具、管理器均可按注册机制扩展
- ⚡ **稳定性能**：简洁实现，快速启动，支持池化预热
- 🌐 **远程能力**：内置 FastAPI 服务，本地与远程接口一致
- 🔧 **OpenAI 兼容**：工具 schema 直接可用于 Function Calling

## 系统要求

- Python ≥ 3.10
- 操作系统：Linux / macOS / Windows（需 Docker）
- 本机 Docker 守护进程；使用 Notebook 沙箱时需开放 8888 端口

## 文档导航

### 第一次使用？

1. [安装](getting-started/installation.md)
2. [5 分钟上手](getting-started/quickstart.md) — 一段最小可运行代码
3. [核心概念](getting-started/concepts.md) — 理解 Sandbox / Manager / Tool 的关系

### 按任务查

- [选择合适的入口](guides/index.md)：Factory / Manager / Pool / HTTP
- [内置工具用法](guides/builtin-tools.md)
- [安装第三方依赖](guides/install-deps.md) / [挂载宿主机目录](guides/host-volumes.md)
- [Notebook 沙箱（保留状态）](guides/notebook-sandbox.md)
- [接入 LLM Agent](guides/agent-integration.md)

### 部署

- [部署 HTTP 服务](deployment/http-server.md) / [客户端调用](deployment/http-client.md)
- [使用 Volcengine 云沙箱](deployment/volcengine.md)

### 扩展开发

- [注册机制总览](extending/index.md)
- 自定义 [Tool](extending/custom-tool.md) / [Sandbox](extending/custom-sandbox.md) / [SandboxManager](extending/custom-manager.md)

### 查 API

- [API 参考](api/index.md)（mkdocstrings 自动生成）

### 遇到问题？

- [常见问题与故障排查](faq.md)
- 提交 issue：<https://github.com/modelscope/ms-enclave/issues>
