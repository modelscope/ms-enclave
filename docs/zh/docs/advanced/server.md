# 部署 HTTP 服务

ms-enclave 内置了一个基于 FastAPI 的 HTTP 服务器，运行该服务可以将沙箱能力暴露给远程调用者。这在构建分布式系统或需要微服务化沙箱能力时非常有用。

## 启动服务器

### 命令行启动

ms-enclave 提供了一个简单的入口来启动服务器：

```bash
ms-enclave server --host 0.0.0.0 --port 8000
```


## 使用 HttpSandboxManager 客户端

一旦服务器启动，您就可以使用 `HttpSandboxManager` 像操作本地管理器一样操作远程沙箱。

```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 连接到远程服务器
    async with SandboxManagerFactory.create_manager(base_url='http://127.0.0.1:8000') as manager:

        # 创建沙箱（在服务器端创建 Docker 容器）
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
        print(f"远程沙箱 ID: {sandbox_id}")
        
        # 执行工具
        result = await manager.execute_tool(sandbox_id, 'python_executor', {
            'code': 'import platform; print(platform.node())'
        })
        print(f"远程执行结果: {result.output}")
    

if __name__ == '__main__':
    asyncio.run(main())
```

## API 概览

HTTP 服务器主要提供以下 API：

*   `POST /sandbox/create`: 创建沙箱
*   `GET /sandboxes`: 列出所有沙箱
*   `GET /sandbox/{sandbox_id}`: 获取沙箱详情
*   `POST /sandbox/{sandbox_id}/stop`: 停止沙箱
*   `DELETE /sandbox/{sandbox_id}`: 删除沙箱
*   `POST /sandbox/tool/execute`: 执行工具 (Body: `ToolExecutionRequest`)
*   `GET /sandbox/{sandbox_id}/tools`: 列出沙箱可用工具
