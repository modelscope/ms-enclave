# 挂载宿主机目录

通过 Docker Volume 让沙箱读写宿主机的文件。适合：

- 把待处理的大文件喂给沙箱
- 把沙箱产物（图表、报告、模型）持久化回宿主机
- 多个沙箱共享同一份只读数据

## 语法

`DockerSandboxConfig.volumes` 接受字典：

```python
volumes = {
    '/host/path': {
        'bind': '/container/path',
        'mode': 'rw',   # 或 'ro' 只读
    },
}
```

`/host/path` 必须是宿主机的**绝对路径**。

## 示例：双向读写

```python
import asyncio
import os
import shutil
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    host_dir = os.path.abspath('./sandbox_data')
    os.makedirs(host_dir, exist_ok=True)
    with open(os.path.join(host_dir, 'host.txt'), 'w') as f:
        f.write('hello from host')

    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'shell_executor': {}},
        volumes={host_dir: {'bind': '/sandbox/data', 'mode': 'rw'}},
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sb:
        # 读
        res = await sb.execute_tool('shell_executor', {
            'command': 'cat /sandbox/data/host.txt',
        })
        print(res.output.strip())  # hello from host

        # 写
        await sb.execute_tool('shell_executor', {
            'command': 'echo "from sandbox" > /sandbox/data/sandbox.txt',
        })

    with open(os.path.join(host_dir, 'sandbox.txt')) as f:
        print(f.read().strip())  # from sandbox

    shutil.rmtree(host_dir)

asyncio.run(main())
```

## 常见用例

### 1. 只读输入

把数据集挂为只读，避免沙箱误改：

```python
volumes={'/data/datasets/squad': {'bind': '/sandbox/input', 'mode': 'ro'}}
```

### 2. 收集产物

固定一个 `output/` 目录用于回收沙箱生成的文件：

```python
volumes={os.path.abspath('./output'): {'bind': '/sandbox/output', 'mode': 'rw'}}
```

### 3. 共享 pip / huggingface 缓存

避免重复下载：

```python
volumes={
    os.path.expanduser('~/.cache/huggingface'): {'bind': '/root/.cache/huggingface', 'mode': 'rw'},
}
```

## 安全提示

挂载会把宿主机权限暴露给沙箱内运行的代码。生产环境务必：

- 优先使用 `ro` 模式
- 不要挂载敏感目录（`/etc`、`/home`、SSH 密钥目录等）
- 必要时配合 `network_enabled=False` 关闭沙箱网络
