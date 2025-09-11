# ms-enclave

模块化且稳定的沙箱运行时环境

## 概述

ms-enclave 是一个模块化且稳定的沙箱运行时环境，为应用程序提供安全的隔离执行环境。它支持多种编程语言和框架，确保代码在基于Docker的容器化控制环境中安全运行。

## 特性

- 🔒 **安全隔离**: 使用Docker容器实现完全隔离
- 🧩 **模块化设计**: 基于插件的架构，具有可扩展的工具系统
- ⚡ **高性能**: 优化的运行时性能，具备资源监控功能
- 📊 **资源监控**: 实时CPU、内存和资源使用情况跟踪
- 🛡️ **安全策略**: 可配置的安全策略和权限控制
- 🌐 **HTTP API**: RESTful API用于远程沙箱管理
- 🔧 **工具系统**: 可扩展的工具系统，适用于不同的执行环境

## 系统要求

- Python >= 3.9
- 操作系统：Linux、macOS或支持Docker的Windows

## 安装

### 从PyPI安装

```bash
pip install ms-enclave
```

### 从源码安装

```bash
git clone https://github.com/modelscope/ms-enclave.git
cd ms-enclave
pip install -e .
```

## 快速开始

### 基本用法

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 创建Docker沙箱配置
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        timeout=30,
        memory_limit='512m',
        tools_config={'python_executor': {}}
    )

    # 使用上下文管理器创建和使用沙箱
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 执行Python代码
        result = await sandbox.execute_tool('python_executor', {
            'code': "print('Hello from sandbox!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')"
        })
        print(f'结果: {result.output}')

asyncio.run(main())
```

### HTTP服务器用法

```python
from ms_enclave.sandbox import create_server

# 启动沙箱服务器
server = create_server(cleanup_interval=300)
server.run(host='127.0.0.1', port=8000)
```
或者
```shell
python -m ms_enclave.run_server
```

### HTTP管理器客户端

```python
import asyncio
from ms_enclave.sandbox.manager import HttpSandboxManager
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():

    async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as manager:
        # 创建沙箱
        config = DockerSandboxConfig(image='python:3.11-slim', tools_config={'python_executor': {}})
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        # 执行代码
        result = await manager.execute_tool(
            sandbox_id, 'python_executor',
            {'code': 'print("Hello from remote sandbox!")'}
        )
        print(result.model_dump())

asyncio.run(main())
```

## API参考

### SandboxFactory

#### create_sandbox(sandbox_type, config)

创建新的沙箱实例。

```python
sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)
```

### 沙箱方法

#### execute_tool(tool_name, parameters)

在沙箱内执行工具。

```python
result = await sandbox.execute_tool('python_executor', {
    'code': 'print("Hello World")',
    'timeout': 30
})
```

#### get_available_tools()

获取可用工具列表。

```python
tools = sandbox.get_available_tools()
```

#### start() / stop() / cleanup()

管理沙箱生命周期。

```python
await sandbox.start()
await sandbox.stop()
await sandbox.cleanup()
```

### HttpSandboxManager

通过HTTP API进行远程沙箱管理。

#### create_sandbox(sandbox_type, config)

```python
sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
```

#### execute_tool(sandbox_id, tool_name, parameters)

```python
result = await manager.execute_tool(sandbox_id, 'python_executor', params)
```

#### list_sandboxes(status_filter=None)

```python
sandboxes = await manager.list_sandboxes()
```

## 示例

### 高级Python执行

```python
async def advanced_example():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        memory_limit='1g'
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 数据处理示例
        code = '''
import json
import statistics

data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
result = {
    "mean": statistics.mean(data),
    "median": statistics.median(data),
    "stdev": statistics.stdev(data)
}
print(json.dumps(result, indent=2))
'''

        result = await sandbox.execute_tool('python_executor', {'code': code})
        print(result.output)
```

### 错误处理

```python
async def error_handling_example():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}},
        timeout=5
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 处理语法错误
        result = await sandbox.execute_tool('python_executor', {
            'code': 'print("Missing quote'
        })

        if result.error:
            print(f"错误: {result.error}")
        else:
            print(f"输出: {result.output}")
```

## 开发

### 本地开发环境设置

```bash
# 克隆仓库
git clone https://github.com/your-username/ms-enclave.git
cd ms-enclave

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows系统：venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 运行示例
python examples/usage_examples.py
python examples/server_example.py
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行覆盖率测试
pytest --cov=ms_enclave

# 运行特定测试文件
pytest tests/test_sandbox.py
```

## 工具

### Python执行器

执行Python代码，在多次调用之间保持持久状态。

```python
result = await sandbox.execute_tool('python_executor', {
    'code': 'x = 42\nprint(f"Value: {x}")',
    'timeout': 30
})
```

### 可用工具

- `python_executor`: 执行Python代码
- `bash`: 执行bash命令
- 自定义工具可通过工具工厂系统添加

## 贡献

我们欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

### 贡献步骤

1. Fork仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 进行更改并添加测试
4. 运行测试：`pytest`
5. 提交更改：`git commit -m 'Add amazing feature'`
6. 推送到分支：`git push origin feature/amazing-feature`
7. 提交Pull Request

## 许可证

本项目采用MIT许可证。详细信息请参见 [LICENSE](LICENSE) 文件。
