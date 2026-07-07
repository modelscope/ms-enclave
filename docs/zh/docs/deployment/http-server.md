# HTTP 服务

`ms-enclave` 内置一个基于 FastAPI 的 HTTP 服务，把沙箱能力暴露给远程调用者。适合分布式部署或多语言客户端接入场景。

## 启动方式

### 命令行

```bash
ms-enclave server --host 0.0.0.0 --port 8000
```

### 代码方式（可自定义鉴权 / 清理策略）

```python
from ms_enclave.sandbox.server import create_server
from ms_enclave.sandbox.model import SandboxManagerConfig

server = create_server(config=SandboxManagerConfig(
    cleanup_interval=600,
    api_key='your-secret-key',   # 可选，开启鉴权
))
server.run(host='0.0.0.0', port=8000)
```

## 鉴权

当 `api_key` 非空时，所有请求需带上：

- HTTP Header：`X-API-Key: your-secret-key`
- 或查询参数：`?api_key=your-secret-key`

否则返回 `401 Unauthorized`。`HttpSandboxManager` 客户端可通过 `api_key` 字段配置。

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET`  | `/health` | 健康检查（含活跃沙箱统计） |
| `GET`  | `/stats`  | 系统统计 |
| `POST` | `/sandbox/create` | 创建沙箱 |
| `GET`  | `/sandboxes` | 列出全部沙箱（可按 `status` 过滤） |
| `GET`  | `/sandbox/{id}` | 查询沙箱信息 |
| `POST` | `/sandbox/{id}/stop` | 停止沙箱 |
| `DELETE` | `/sandbox/{id}` | 删除沙箱 |
| `GET`  | `/sandbox/{id}/tools` | 该沙箱已启用工具（OpenAI schema） |
| `POST` | `/sandbox/tool/execute` | 在指定沙箱执行工具 |
| `POST` | `/pool/initialize` | 预热沙箱池 |
| `POST` | `/pool/execute` | 从池中借沙箱执行工具 |

### 创建沙箱

```bash
curl -X POST 'http://localhost:8000/sandbox/create?sandbox_type=docker' \
  -H 'Content-Type: application/json' \
  -d '{"image":"python:3.11-slim","tools_config":{"python_executor":{}}}'
# => {"sandbox_id":"abc123"}
```

### 执行工具

```bash
curl -X POST http://localhost:8000/sandbox/tool/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "sandbox_id": "abc123",
    "tool_name": "python_executor",
    "parameters": {"code": "print(40 + 2)"}
  }'
```

## Docker 部署建议

服务端需要访问宿主机 Docker，最常见做法是把宿主的 docker socket 挂进去：

```bash
docker run -d --name ms-enclave-server \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  python:3.11-slim \
  bash -c 'pip install "ms-enclave[docker]" && ms-enclave server --host 0.0.0.0'
```

> ⚠️ 把 docker socket 挂进容器等同于赋予容器主机 root 权限，**仅限受信任的网络环境使用**。生产环境优先考虑：
> - 单独的物理 / 虚拟机器部署服务端
> - 配合反向代理（Nginx / Traefik）启用 HTTPS 与限流

## 客户端

服务端启动后，使用 [`HttpSandboxManager`](http-client.md) 远程调用。
