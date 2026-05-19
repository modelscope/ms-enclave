# 核心概念

ms-enclave 采用模块化分层架构，将运行时环境管理、工具执行和生命周期维护解耦。理解以下核心概念及其关系，有助于您构建高效的 Agent 系统。

## 架构概览

核心组件之间的关系如下图所示：

```ascii
+------------------+           +----------------------+
|   User / Client  | --------> |    SandboxManager    |
+------------------+           | (Local / HTTP Proxy) |
                               +----------+-----------+
                                          |
                                          | 1. Manage
                                          |
                                          v
+----------------------+       +----------------------+
|    SandboxFactory    | ----> |       Sandbox        | <---+
+----------------------+  2.   | (Docker / Notebook)  |     |
                         Create+----------+-----------+     |
                                          |                 | 4.
                                          | 3. Run          | Execute
                                          v                 |
                               +----------------------+     |
                               |    Runtime Envrion   |     |
                               |  (Container / Kernel)|     |
                               +----------------------+     |
                                          |                 |
+----------------------+       +----------+-----------+     |
|      ToolFactory     | ----> |         Tool         | ----+
+----------------------+  2.   | (Python/Shell/File)  |
                         Create+----------------------+
```

## 1. 沙箱系统 (Sandbox System)

沙箱是代码安全执行的隔离环境。

### Sandbox (沙箱基类)
`Sandbox` 是核心抽象类 (ABC)，定义了隔离环境的标准行为。

*   **作用**: 封装底层的运行时细节（如 Docker API 调用），提供统一的 `start` (启动)、`stop` (停止)、`execute_command` (执行底层命令) 接口。
*   **状态管理**: 维护严格的生命周期状态：
    *   `CREATED`: 已初始化但未分配资源。
    *   `STARTING`: 正在启动容器或分配资源。
    *   `RUNNING`: 正常运行中，可接受指令。
    *   `STOPPING` / `STOPPED`: 正在停止或已停止。
    *   `ERROR`: 发生运行时错误。

### SandboxFactory (沙箱工厂)

*   **作用**: 这是一个工厂模式实现，负责根据配置类型（`SandboxType`）动态创建具体的沙箱实例。
*   **扩展性**: 使用 `@register_sandbox` 装饰器注册新的沙箱类型，无需修改工厂代码即可扩展系统。

### 具体实现与配置

*   **DockerSandbox (类型: `docker`)**:
    *   基于 Docker 容器的标准沙箱，提供文件系统和网络隔离。
    *   **主要配置 (`DockerSandboxConfig`)**:
        *   `image` (str): Docker 镜像名 (如 `python:3.10-slim`)。
        *   `cpu_limit` (float): CPU 核心数限制 (如 `1.0`)。
        *   `memory_limit` (str): 内存限制 (如 `"512m"`, `"1g"`).
        *   `auto_remove` (bool): 停止后是否自动删除容器。
        *   `volumes` (dict): 挂载卷配置。
*   **DockerNotebook (类型: `docker_notebook`)**:
    *   继承自 DockerSandbox，内置 Jupyter Kernel Gateway。支持通过 HTTP/WebSocket 进行交互式代码执行（保持变量状态）。
    *   **主要配置**: 继承自 `DockerSandboxConfig`，额外包含内核通信端口配置。

## 2. 工具系统 (Tool System)

工具是 LLM 与沙箱交互的能力载体。

### Tool (工具基类)

*   **作用**: 抽象了具体的操作逻辑。必须实现 `execute(sandbox_context, **kwargs)` 方法。
*   **Schema**: 每个工具通过 `schema` 属性暴露符合 OpenAI Function Calling 标准的定义，方便 LLM 决策。

### ToolFactory (工具工厂)

*   **作用**: 集中管理工具的实例化。
*   **机制**: 通过 `@register_tool("name")` 进行注册。在创建沙箱配置时，可以通过工具名称列表启用特定工具。

### 常用工具
工具主要分为通用工具和特定环境工具：

*   **PythonExecutor**: 在沙箱内执行 Python 代码片段（非交互式，或通过 Notebook 交互）。
*   **ShellExecutor**: 执行 Bash 命令。
*   **FileOperation**: 提供 `read_file`, `write_file`, `list_dir` 等文件操作。

## 3. 管理层 (Management Layer)

管理器用于编排沙箱的生命周期，是用户通过代码直接交互的对象。

### SandboxManager (概念)
定义了 `create_sandbox`, `get_sandbox`, `stop_sandbox` 等标准管理接口。

### LocalSandboxManager (本地管理器)

*   **位置**: `ms_enclave.manager.local_manager`
*   **作用**: 在当前 Python 进程中直接管理沙箱对象。
*   **特性**:
    *   **自动清理**: 内置后台线程，定期清理超时 (`RUNNING` > 48h) 或异常 (`ERROR/STOPPED` > 1h) 的沙箱，防止资源泄露。
    *   适合开发调试、单机部署或作为 Server 端的内部实现。

### HttpSandboxManager (HTTP 管理器)

*   **位置**: `ms_enclave.manager.http_manager`
*   **作用**: 一个客户端代理，负责与远程的 `ms-enclave` Server (FastAPI) 通信。
*   **特性**: API 签名与本地管理器保持高度一致，使得从本地模式切换到远程服务模式几乎无需修改业务代码。
