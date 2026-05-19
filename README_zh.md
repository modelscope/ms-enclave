<p align="center">
    <br>
    <img src="docs/asset/image/logo.png"/>
    <br>
<p>

<p align="center">
  中文 &nbsp ｜ &nbsp <a href="README.md">English</a> &nbsp
</p>

<p align="center">
<img src="https://img.shields.io/badge/python-%E2%89%A53.10-5be.svg">
<a href="https://badge.fury.io/py/ms-enclave"><img src="https://badge.fury.io/py/ms-enclave.svg" alt="PyPI version" height="18"></a>
<a href="https://pypi.org/project/ms-enclave"><img alt="PyPI - Downloads" src="https://static.pepy.tech/badge/ms-enclave"></a>
<a href="https://github.com/modelscope/ms-enclave/pulls"><img src="https://img.shields.io/badge/PR-welcome-55EB99.svg"></a>
<p>

<p align="center">
<a href="https://ms-enclave.readthedocs.io/zh-cn/latest"> 📖  中文文档</a> &nbsp ｜ &nbsp <a href="https://ms-enclave.readthedocs.io/en/latest/"> 📖  English Documents</a>
<p>


> ⭐ 如果你喜欢这个项目，请点击右上角的 "Star" 按钮支持我们。你的支持是我们前进的动力！


## 简介

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
# 如果需要 Docker 支持，安装额外依赖
pip install 'ms-enclave[docker]'
```

### 从源码安装

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
# 如果需要 Docker 支持，安装额外依赖
pip install -e '.[docker]'
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

## Agent 模型工具调用（OpenAI Tools）

将沙箱工具以 OpenAI Tools 形式暴露给 Agent，模型触发工具后在沙箱中安全执行。

````python
import asyncio, os, json
from openai import OpenAI
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def demo():
    client = OpenAI(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=os.getenv("DASHSCOPE_API_KEY")
    )
    async with SandboxManagerFactory.create_manager() as m:
        cfg = DockerSandboxConfig(image="python:3.11-slim", tools_config={"python_executor": {}, "shell_executor": {}})
        sid = await m.create_sandbox(SandboxType.DOCKER, cfg)

        tools = list((await m.get_sandbox_tools(sid)).values())
        messages = [{"role": "user", "content": "Print 'hello' in Python, then list /sandbox via shell."}]

        rsp = client.chat.completions.create(model="qwen-plus", messages=messages, tools=tools, tool_choice="auto")
        msg = rsp.choices[0].message
        messages.append(msg.model_dump())

        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                result = await m.execute_tool(sid, name, args)
                messages.append({"role": "tool", "content": result.model_dump_json(), "tool_call_id": tc.id, "name": name})
            final = client.chat.completions.create(model="qwen-plus", messages=messages)
            print(final.choices[0].message.content or "")
        else:
            print(msg.content or "")

asyncio.run(demo())
````

说明：
- 使用 `get_sandbox_tools(sandbox_id)` 获取工具 schema（OpenAI 兼容）
- 将 `tools=...` 传入模型，处理返回的 `tool_calls` 并在沙箱执行
- 再次调用模型生成最终答案

---

## 典型使用方式与示例


- 直接使用 SandboxFactory：在单进程内创建/销毁沙箱，最轻量；适合脚本或一次性任务
- 使用 LocalSandboxManager：在本机统一编排多个沙箱的生命周期/清理；适合服务化、多任务并行场景
- 使用 HttpSandboxManager：通过远程 HTTP 服务统一管理沙箱；适合跨机/分布式或隔离更强的部署

### 0) 管理器工厂：SandboxManagerFactory（自动选择本地/HTTP）

适用场景：
- 希望用一个入口根据参数自动选择本地或 HTTP 管理器
- 需要查询已注册的管理器类型，或统一构造逻辑

要点：
- 显式传入 manager_type 时，按类型创建
- 当提供 base_url（在 config 或 kwargs）时，创建 HTTP 管理器
- 两者都未提供时，默认创建本地管理器

示例：通过 base_url 隐式选择 HTTP 管理器
```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory

async def main():
    async with SandboxManagerFactory.create_manager(base_url='http://127.0.0.1:8000') as m:
        # 与 HttpSandboxManager 用法一致
        # 例如：创建 DOCKER 沙箱并执行工具
        # ... 你的代码 ...
        pass

asyncio.run(main())
```

示例：显式选择 + 自定义配置
```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import SandboxManagerConfig, SandboxManagerType

async def main():
    cfg = SandboxManagerConfig(cleanup_interval=600)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, config=cfg
    ) as m:
        # 与 LocalSandboxManager 用法一致
        # ... 你的代码 ...
        pass

asyncio.run(main())
```

查看已注册类型：
```python
from ms_enclave.sandbox.manager import SandboxManagerFactory
print(SandboxManagerFactory.get_registered_types())
```

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

### 4) 沙箱池：预热复用的工作进程（Sandbox Pool）

为何使用：
- 通过预热固定数量的沙箱，摊销容器启动开销，提高吞吐。
- 每次执行从池中借出沙箱并在完成后归还；当全部忙碌时按 FIFO 排队。

本地管理示例：

```python
import asyncio
from ms_enclave.sandbox.manager import LocalSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with LocalSandboxManager() as m:
        cfg = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        # 预热 2 个沙箱
        await m.initialize_pool(pool_size=2, sandbox_type=SandboxType.DOCKER, config=cfg)

        # 多次执行；忙时按 FIFO 排队，执行完成后归还至池中
        tasks = [
            m.execute_tool_in_pool('python_executor', {'code': f'print("task {i}")', 'timeout': 30})
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        print([r.output.strip() for r in results])

        # 查看统计
        stats = await m.get_stats()
        print('pool_size =', stats['pool_size'])

asyncio.run(main())
```

HTTP 管理示例：

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as m:
        cfg = DockerSandboxConfig(image='python:3.11-slim', tools_config={'python_executor': {}})
        await m.initialize_pool(pool_size=2, sandbox_type=SandboxType.DOCKER, config=cfg)

        r = await m.execute_tool_in_pool('python_executor', {'code': 'print("hello from pool")', 'timeout': 30})
        print(r.output)

asyncio.run(main())
```

说明：
- 等待超时：`await m.execute_tool_in_pool(..., timeout=1.0)` 若在超时时间内无可用沙箱将抛出 `TimeoutError`。
- FIFO 行为：在并发负载下，借还顺序遵循 FIFO。
- 错误处理：即使执行失败，沙箱也会归还至池中。

---

## 沙箱类型与工具支持

当前内置沙箱类型：

- DOCKER（通用容器执行）
  - 支持工具：
    - python_executor（执行 Python 代码）
    - shell_executor（执行 Shell 命令）
    - file_operation（读/写/删/列 文件）
    - multi_code_executor（多语言代码执行，支持 python, cpp, csharp, go, java, nodejs, ts, rust, php, bash, pytest, jest, go_test, lua, r, perl, d_ut, ruby, scala, julia, kotlin_script, verilog, lean, swift, racket）需要指定镜像 `volcengine/sandbox-fusion:server-20250609`
  - 特性：可配置内存/CPU 限制、卷挂载、网络开关、特权模式、端口映射

- DOCKER_NOTEBOOK（Jupyter Kernel Gateway 环境）
  - 支持工具：
    - notebook_executor（通过 Jupyter 内核执行代码，支持保存代码上下文）
  - 注意：该类型只加载 notebook_executor，其他 DOCKER 专属工具不会在此沙箱启用
  - 依赖：暴露 8888 端口、启用网络

工具加载规则：

- 仅当在 `tools_config` 中显式声明时，工具才会初始化并可用
- 工具会校验 `required_sandbox_types`，不匹配则自动忽略

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

管理器配置（SandboxManagerConfig）：
- `base_url`：若设置则自动选择 HttpSandboxManager
- `cleanup_interval`：本地管理器的后台清理间隔（秒）

**Sandbox中安装额外依赖示例**
```python
async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
    # 1) Write a file
    requirements_file = '/sandbox/requirements.txt'
    await sandbox.execute_tool('file_operation', {
        'operation': 'write', 'file_path': f'{requirements_file}', 'content': 'numpy\npandas\nmodelscope\n'
    })
    # 2) Execute Python code
    result = await sandbox.execute_tool('python_executor', {
        'code': f"print('Hello from sandbox!')\nprint(open(f'{requirements_file}').read())"
    })
    print(result.output)

    # 3) Execute CLI
    result_cli = await sandbox.execute_command(f'pip install -r {requirements_file}')
    print(result_cli.stdout, flush=True)
```

**Sandbox中读写宿主机文件示例**
```python
async with LocalSandboxManager() as manager:
    # Create sandbox
    config = DockerSandboxConfig(
        # image='python-sandbox',
        image='python:3.11-slim',
        tools_config={'python_executor': {}, 'file_operation': {}},
        volumes={'~/Code/ms-enclave/output': {'bind': '/sandbox/data', 'mode': 'rw'}}
    )
    sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

    # Write file
    result = await manager.execute_tool(
        sandbox_id, 'file_operation', {'operation': 'write', 'file_path': '/sandbox/data/hello.txt', 'content': 'Hello, Sandbox!'}
    )
    print(result.model_dump())
```

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
conda create -n ms-enclave python=3.10 -y
conda activate ms-enclave

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
