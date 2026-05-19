# 在沙箱内安装第三方依赖

沙箱默认仅含基础镜像里的包。若需要 `numpy`、`pandas` 等三方库，最简单的做法是通过 `file_operation` 写一份 `requirements.txt`，再用 `shell_executor` 运行 `pip install`。

## 示例

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},
            'file_operation': {},
            'shell_executor': {},
        },
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        # 1) 写 requirements.txt
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/requirements.txt',
            'content': 'numpy\npandas\n',
        })

        # 2) pip install
        install = await sandbox.execute_command(
            'pip install -r /sandbox/requirements.txt'
        )
        assert install.exit_code == 0, install.stderr

        # 3) 验证
        check = await sandbox.execute_tool('python_executor', {
            'code': 'import numpy, pandas; print(numpy.__version__, pandas.__version__)',
        })
        print(check.output.strip())

asyncio.run(main())
```

## 性能优化

每次创建新沙箱都重装一遍依赖会很慢。生产环境推荐两种方案，按需求选择：

### 方案一：自定义基础镜像（推荐）

预先构建包含依赖的 Docker 镜像，然后用 `image` 字段指定它：

```dockerfile
# Dockerfile
FROM python:3.11-slim
RUN pip install numpy pandas
```

```bash
docker build -t my-runtime:1.0 .
```

```python
config = DockerSandboxConfig(image='my-runtime:1.0', ...)
```

启动时间显著降低，也方便配合 [沙箱池](sandbox-pool.md) 预热。

### 方案二：挂载共享的 pip 缓存

```python
config = DockerSandboxConfig(
    image='python:3.11-slim',
    volumes={
        '/home/me/.cache/pip': {'bind': '/root/.cache/pip', 'mode': 'rw'},
    },
    ...
)
```

二次安装时直接命中本地 wheel 缓存，省去下载时间。

## 离线环境

若沙箱没有外网，需要先 `pip download` 把 wheel 放到宿主机目录，再用 [挂载宿主机目录](host-volumes.md) 暴露到容器内 `pip install --no-index --find-links /sandbox/wheels`。
