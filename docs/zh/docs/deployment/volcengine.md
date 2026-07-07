# Volcengine 云沙箱（SandboxFusion）

`ms-enclave` 内置对 [火山引擎 SandboxFusion](https://www.volcengine.com/) 无状态沙箱的支持。与 Docker 沙箱不同，Volcengine 沙箱通过远程 HTTP 服务 `/run_code` 提交代码执行，无需在本地启 Docker。

## 适用场景

- 不想本地维护 Docker 守护进程
- 需要快速跑多语言代码（python / cpp / go / rust / java / nodejs …）
- 高并发场景借助远端集群弹性

## 前置：启动 SandboxFusion 服务

火山官方预置镜像可直接运行：

```bash
docker run -it -p 8080:8080 \
  vemlp-cn-beijing.cr.volces.com/preset-images/code-sandbox:server-20250609
```

服务启动后默认监听 `http://localhost:8080`。

## 通过 Manager 使用（推荐）

```python
import asyncio
from ms_enclave.sandbox.manager import VolcengineSandboxManager
from ms_enclave.sandbox.model import (
    SandboxType, VolcengineSandboxConfig, VolcengineSandboxManagerConfig,
)

async def main():
    manager_config = VolcengineSandboxManagerConfig(
        base_url='http://localhost:8080',
        max_concurrency=4,
        request_timeout=30.0,
    )
    sandbox_config = VolcengineSandboxConfig(
        tools_config=['python_executor', 'shell_executor', 'multi_code_executor'],
    )

    async with VolcengineSandboxManager(config=manager_config) as manager:
        sandbox_id = await manager.create_sandbox(SandboxType.VOLCENGINE, sandbox_config)

        # 1) Python
        r = await manager.execute_tool(sandbox_id, 'python_executor', {
            'code': 'print("hello from python:", 1 + 2)',
        })
        print(r.output)

        # 2) Shell
        r = await manager.execute_tool(sandbox_id, 'shell_executor', {
            'command': 'echo hello && uname -a',
        })
        print(r.output)

        # 3) 多语言：C++
        cpp = (
            '#include <iostream>\n'
            'int main() { std::cout << "hi from c++"; return 0; }\n'
        )
        r = await manager.execute_tool(sandbox_id, 'multi_code_executor', {
            'language': 'cpp',
            'code': cpp,
        })
        print(r.output)

asyncio.run(main())
```

## 通过 SandboxFactory 使用

如果只是一次性脚本，也可以直接走工厂模式，把 `base_url` 写在 `VolcengineSandboxConfig` 上：

```python
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, VolcengineSandboxConfig

config = VolcengineSandboxConfig(
    base_url='http://localhost:8080',
    tools_config=['python_executor'],
)
async with SandboxFactory.create_sandbox(SandboxType.VOLCENGINE, config) as sb:
    res = await sb.execute_tool('python_executor', {'code': 'print(42)'})
    print(res.output)
```

## 主要配置项

`VolcengineSandboxManagerConfig`：

| 字段 | 默认 | 说明 |
|---|---|---|
| `base_url` | 必填 | SandboxFusion 服务地址 |
| `api_key` | None | 可选，作为 `Authorization` 头 |
| `request_timeout` | 30.0 | 单次请求超时（秒） |
| `verify_ssl` | True | 是否校验 SSL |
| `run_code_path` | `/run_code` | 端点路径 |
| `max_concurrency` | 16 | manager 内最大并发请求数 |
| `extra_headers` | None | 自定义 HTTP 头 |
| `dataset_language_map` | None | 语言名重映射，如 `{"r": "R"}` |

## 与 Docker 沙箱的差异

| 特性 | DOCKER | VOLCENGINE |
|---|---|---|
| 本地需要 Docker | ✅ | ❌ |
| 状态保留 | 容器存活期间 | **无状态**，每次调用独立 |
| 文件操作 | 支持 `file_operation` | 仅多语言代码执行 |
| 多语言支持 | 需 `multi_code_executor` + 特定镜像 | 原生支持 |
| 资源限制 | CPU/内存/网络可控 | 由远端服务决定 |

> 由于 Volcengine 沙箱是无状态的，**不要在多次调用之间依赖变量、文件或 import 状态**。
