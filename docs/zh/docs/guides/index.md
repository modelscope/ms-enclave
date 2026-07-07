# 使用指南概览

`ms-enclave` 提供四种典型的入口方式，对应不同的集成需求。本节按"做什么"组织文档，先用下面的决策表选好入口，再翻到对应章节查代码示例。

## 我该用哪个入口？

| 场景 | 推荐入口 | 章节 |
|---|---|---|
| 写脚本 / 单元测试，跑完即走 | `SandboxFactory` | [直接使用沙箱](sandbox-factory.md) |
| 应用内同时管理多个沙箱、需要后台清理 | `LocalSandboxManager` | [本地管理器](local-manager.md) |
| 高并发服务，需要预热和池化 | `Sandbox Pool` | [沙箱池](sandbox-pool.md) |
| 沙箱跑在独立服务器上 | `HttpSandboxManager` | [HTTP 客户端](../deployment/http-client.md) |
| 让 LLM 自主决定调用哪个工具 | `Manager` + OpenAI Tools | [接入 LLM Agent](agent-integration.md) |

不确定选哪种？记住一个粗略经验：

- **脚本/Notebook** → `SandboxFactory`
- **Web 后端/任务调度** → `LocalSandboxManager`（必要时启池）
- **分布式部署** → 服务端跑 HTTP 服务，客户端用 `HttpSandboxManager`

## 工厂统一入口

如果不希望在代码里硬编码"本地还是远程"，可以用 `SandboxManagerFactory`：

- 传入 `base_url` → 自动返回 `HttpSandboxManager`
- 不传 `base_url` → 返回 `LocalSandboxManager`

```python
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import SandboxManagerConfig

# 本地
async with SandboxManagerFactory.create_manager() as manager:
    ...

# 远程
async with SandboxManagerFactory.create_manager(base_url='http://server:8000') as manager:
    ...
```

这样业务代码可以无缝切换部署模式。

## 常用主题

- [内置工具一览](builtin-tools.md)：`python_executor` / `shell_executor` / `file_operation` 的参数与返回
- [在沙箱内安装第三方依赖](install-deps.md)
- [挂载宿主机目录读写文件](host-volumes.md)
- [Notebook 沙箱（保持变量状态）](notebook-sandbox.md)
- [接入 LLM Agent / OpenAI Tools](agent-integration.md)
