# ms-enclave

模块化且稳定的沙箱运行时环境

## 概述

ms-enclave 是一个模块化且稳定的沙箱运行时环境，为应用程序提供安全的隔离执行环境。它通过 Docker 容器实现强隔离，配套本地/HTTP 管理器与可扩展工具系统，帮助你在受控环境中安全、高效地执行代码。


- 🔒 安全隔离：基于 Docker 的完全隔离与资源限制
- 🧩 模块化：沙箱与工具均可扩展（注册工厂）
- ⚡ 稳定性能：简洁实现，快速启动，带生命周期管理
- 🌐 远程管理：内置 FastAPI 服务，支持 HTTP 管理
- 🔧 工具体系：按沙箱类型启用的标准化工具（OpenAI 风格 schema）

## 系统要求

- Python >= 3.10
- 操作系统：Linux、macOS 或支持 Docker 的 Windows
- 需本机可用的 Docker 守护进程（Notebook 沙箱需开放 8888 端口）

## 安装

### 从 PyPI 安装

```bash
pip install ms-enclave
```

### 从源码安装

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
```

## 快速开始：最小可用示例（SandboxFactory）

> 工具需要在配置的 tools_config 中显式启用，否则不会被注册。

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        memory_limit='512m',
        tools_config={
            'python_executor': {},
            'file_operation': {},
            'shell_executor': {}
        }
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 1) 写文件
        await sandbox.execute_tool('file_operation', {
            'operation': 'write', 'file_path': '/sandbox/hello.txt', 'content': 'hi from enclave'
        })
        # 2) 执行 Python 代码
        result = await sandbox.execute_tool('python_executor', {
            'code': "print('Hello from sandbox!')\nprint(open('/sandbox/hello.txt').read())"
        })
        print(result.output)

asyncio.run(main())
```

---

## 典型使用方式与示例


- 直接使用 SandboxFactory：在单进程内创建/销毁沙箱，最轻量；适合脚本或一次性任务
- 使用 LocalSandboxManager：在本机统一编排多个沙箱的生命周期/清理；适合服务化、多任务并行场景
- 使用 HttpSandboxManager：通过远程 HTTP 服务统一管理沙箱；适合跨机/分布式或隔离更强的部署

### 1) 直接创建沙箱：SandboxFactory（轻量、临时）

适用场景：

- 脚本或微服务中临时跑一段代码
- 对沙箱生命周期有细粒度把控（上下文退出即清理）

示例（Docker 沙箱 + Python 执行）：

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    cfg = DockerSandboxConfig(
        tools_config={'python_executor': {}}
    )
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, cfg) as sb:
        r = await sb.execute_tool('python_executor', {
            'code': 'import platform; print(platform.python_version())'
        })
        print(r.output)

asyncio.run(main())
```

### 2) 本地统一编排：LocalSandboxManager（多沙箱、生命周期管理）

适用场景：

- 同一进程内需要创建/管理多个沙箱（创建、查询、停止、定期清理）
- 想要统一查看状态、统计与健康度

示例：

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with LocalSandboxManager() as manager:
        cfg = DockerSandboxConfig(tools_config={'shell_executor': {}})
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, cfg)

        # 执行命令
        res = await manager.execute_tool(sandbox_id, 'shell_executor', {'command': 'echo hello'})
        print(res.output.strip())  # hello

        # 查看列表
        infos = await manager.list_sandboxes()
        print([i.id for i in infos])

        # 停止并删除
        await manager.stop_sandbox(sandbox_id)
        await manager.delete_sandbox(sandbox_id)

asyncio.run(main())
```

### 3) 远程统一管理：HttpSandboxManager（跨机/隔离部署）

适用场景：

- 将沙箱服务跑在独立主机/容器中，通过 HTTP 远程调用
- 多个应用共享一套安全受控的沙箱集群

先启动服务（二选一）：

```bash
# 方式 A：命令行
ms-enclave server --host 0.0.0.0 --port 8000

# 方式 B：Python 启动
python -c "from ms_enclave.sandbox import create_server; create_server().run(host='0.0.0.0', port=8000)"
```

客户端示例：

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as m:
        cfg = DockerSandboxConfig(tools_config={'python_executor': {}})
        sid = await m.create_sandbox(SandboxType.DOCKER, cfg)
        r = await m.execute_tool(sid, 'python_executor', {'code': 'print("Hello remote")'})
        print(r.output)
        await m.delete_sandbox(sid)

asyncio.run(main())
```

---

## 沙箱类型与工具支持

当前内置沙箱类型：

- DOCKER（通用容器执行）
  - 支持工具：
    - python_executor（执行 Python 代码）
    - shell_executor（执行 Shell 命令）
    - file_operation（读/写/删/列 文件）
  - 特性：可配置内存/CPU 限制、卷挂载、网络开关、特权模式、端口映射

- DOCKER_NOTEBOOK（Jupyter Kernel Gateway 环境）
  - 支持工具：
    - notebook_executor（通过 Jupyter 内核执行代码，支持保存代码上下文）
  - 注意：该类型只加载 notebook_executor，其他 DOCKER 专属工具不会在此沙箱启用
  - 依赖：暴露 8888 端口、启用网络

工具加载规则：

- 仅当在 `tools_config` 中显式声明时，工具才会初始化并可用
- 工具会校验 `required_sandbox_type`，不匹配则自动忽略

示例：

```python
DockerSandboxConfig(tools_config={'python_executor': {}, 'shell_executor': {}, 'file_operation': {}})
DockerNotebookConfig(tools_config={'notebook_executor': {}})
```

---

## 常用配置项

- `image`: Docker 镜像名（如 `python:3.11-slim` 或 `jupyter-kernel-gateway`）
- `memory_limit`: 内存限制（如 `512m`/`1g`）
- `cpu_limit`: CPU 限制（float，>0）
- `volumes`: 卷挂载，形如 `{host_path: {"bind": "/container/path", "mode": "rw"}}`
- `ports`: 端口映射，形如 `{ "8888/tcp": ("127.0.0.1", 8888) }`
- `network_enabled`: 是否启用网络（Notebook 沙箱需 True）
- `remove_on_exit`: 退出后是否删除容器（默认 True）

---

## 错误处理与调试

```python
result = await sandbox.execute_tool('python_executor', {'code': 'print(1/0)'})
if result.error:
    print('错误信息:', result.error)
else:
    print('输出:', result.output)
```

---

## 开发与测试

```bash
# 克隆仓库
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 运行示例（仓库自带）
python examples/sandbox_usage_examples.py
python examples/local_manager_example.py
python examples/server_manager_example.py
```

---

## 可用工具一览

- `python_executor`：执行 Python 代码（DOCKER）
- `shell_executor`：执行 Shell 命令（DOCKER）
- `file_operation`：读/写/删/列 文件（DOCKER）
- `notebook_executor`：在 Jupyter Kernel 中执行（DOCKER_NOTEBOOK）
- 你也可以通过 Tool 工厂（`@register_tool`）注册自定义工具

---

## 贡献

我们欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

### 贡献步骤

1. Fork 仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 开发与补充测试
4. 本地运行测试：`pytest`
5. 提交更改：`git commit -m 'Add amazing feature'`
6. 推送分支：`git push origin feature/amazing-feature`
7. 提交 Pull Request

## 许可证

本项目采用 Apache 2.0 许可证。详见 [LICENSE](LICENSE)。
