# 常见问题与故障排查

## 安装与环境

### Q：`pip install ms-enclave` 后调用提示 `docker` 模块缺失？
A：基础安装不带 Docker SDK。请安装可选依赖：

```bash
pip install 'ms-enclave[docker]'
```

### Q：macOS / Apple Silicon 上拉到的是 amd64 镜像，运行很慢或报错。
A：在 `DockerSandboxConfig` 上指定平台，或直接换 arm64 镜像：

```python
DockerSandboxConfig(image='python:3.11-slim', platform='linux/arm64')
```

### Q：Docker 启动报 `permission denied while trying to connect to the Docker daemon socket`？
A：当前用户没有 `/var/run/docker.sock` 访问权限。Linux 上把用户加到 `docker` 组：

```bash
sudo usermod -aG docker $USER
newgrp docker
```

或用 `sudo` 运行（不推荐）。

## 沙箱使用

### Q：调用 `execute_tool` 抛 `Tool 'xxx' not found`？
A：忘记在 `tools_config` 里声明这个工具。**只有显式声明才会注册**。

```python
DockerSandboxConfig(tools_config={'python_executor': {}, 'shell_executor': {}})
```

### Q：执行命令超时了。
A：默认 `timeout=30` 秒。给工具调用传入更大的 `timeout`，或在 `SandboxConfig.timeout` 设置全局默认值。

### Q：容器残留没清理？
A：常见原因：

- 用 `SandboxFactory` 时没用 `async with`，且忘了 `await sandbox.stop()`
- 进程被 SIGKILL，`async with` 也没机会清理

推荐改用 `LocalSandboxManager`：它带后台清理协程，会回收超时（默认 48h）和异常状态的沙箱。

或者手动清理：

```bash
docker ps -a --filter "label=ms-enclave" -q | xargs -r docker rm -f
```

### Q：怎么让 Python 代码在多次调用之间保留变量？
A：用 [Notebook 沙箱](guides/notebook-sandbox.md)（`SandboxType.DOCKER_NOTEBOOK` + `notebook_executor`），它共享同一个 Jupyter Kernel。`python_executor` 是无状态的。

## Notebook 沙箱

### Q：`Jupyter Kernel Gateway failed to become ready within 30 seconds`。
A：通常是首次自动构建镜像耗时较长（要下 jupyter-kernel-gateway 等依赖）。等 build 完成后再试；或提前手动 build 一个标记为 `jupyter-kernel-gateway` 的镜像。

### Q：`websocket-client package is required`。
A：客户端需要额外依赖：

```bash
pip install websocket-client requests
```

### Q：端口 8888 被占用。
A：把 `DockerNotebookConfig.port` 改成别的空闲端口。

## HTTP 服务

### Q：所有请求 401 Unauthorized。
A：服务端启用了 `api_key`。客户端调用时需带：

- Header：`X-API-Key: your-secret-key`
- 或在 `HttpSandboxManager(base_url=..., api_key='...')`

### Q：服务端拉镜像很慢，客户端调用超时。
A：客户端默认 HTTP 超时较短。提高它：

```python
HttpSandboxManager(base_url='...', timeout=120)
```

或在服务端预先 `docker pull` 好镜像。

## Volcengine 云沙箱

### Q：调用报连接拒绝。
A：检查 SandboxFusion 服务是否启动（`docker run -p 8080:8080 ...`），以及 `base_url` 是否正确（默认 `http://localhost:8080`）。

### Q：第二次调用变量丢了。
A：Volcengine 沙箱**无状态**，每次 `execute_tool` 都是独立执行。需要状态请用 Docker 或 DockerNotebook 沙箱。

## 性能

### Q：沙箱启动太慢。
A：

- 预先 `docker pull` 镜像，避免实时下载
- 用 [沙箱池](guides/sandbox-pool.md) 提前预热
- 构建瘦身基础镜像（只装必要依赖）

### Q：高并发时部分请求超时。
A：

- 调大 `pool_size`，并设置合理 `timeout` 让超时请求快速失败
- 监控 `get_stats()` 中的活跃数 / 池占用，定位瓶颈

## 还没解决？

提交 issue：<https://github.com/modelscope/ms-enclave/issues>，附上：

- 复现代码（最简版本即可）
- `pip show ms-enclave` 输出
- `docker version` 输出
- 错误堆栈完整文本
