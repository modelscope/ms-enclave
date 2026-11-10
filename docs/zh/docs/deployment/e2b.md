# E2B 远程沙箱

使用 E2B 官方服务或兼容的阿里云 Agent Sandbox，在远程环境中执行 Python、Shell 命令，无需本机 Docker。同一沙箱内的文件可跨调用使用；Python 工具每次启动独立进程，变量不会跨调用保留。

## 安装与准备

准备服务的 API Key 和一个可用的模板名称，然后安装依赖：

```bash
pip install 'ms-enclave[e2b]'
export E2B_API_KEY='your-api-key'
```

模板需要提供 `python` 命令；上传文件还需要 `tar`。默认执行用户为 `user`，工作目录为 `/home/user`，请确认模板中存在对应用户和目录。

## 运行第一个任务

将 `your-template` 替换为服务中已有的模板名称：

```python
import asyncio

from ms_enclave.sandbox.manager import E2BSandboxManager
from ms_enclave.sandbox.model import E2BSandboxConfig, SandboxType


async def main():
    config = E2BSandboxConfig(
        template='your-template',
        tools_config=['python_executor', 'shell_executor'],
        sandbox_timeout=300,
    )
    async with E2BSandboxManager() as manager:
        sid = await manager.create_sandbox(SandboxType.E2B, config)
        result = await manager.execute_tool(
            sid, 'python_executor', {'code': 'print(1 + 1)', 'timeout': 30}
        )
        if not result.success:
            raise RuntimeError(result.error)
        print(result.output)


asyncio.run(main())
```

输出为 `2`。离开 `async with` 时，管理器自动清理本次创建的沙箱。

这里的 `timeout=30` 限制单次命令的执行时间，`sandbox_timeout=300` 限制整个沙箱的存活时间。沙箱不会自动续期；到期后需要重新创建，时长也需符合服务套餐限制。

## 连接阿里云或其他兼容服务

使用阿里云时，还需设置服务控制台提供的域名：

```bash
export E2B_DOMAIN='your-service-domain'
```

如果服务提供单独的 API 地址，再设置 `E2B_API_URL`。也可以在代码中显式配置，覆盖对应的环境变量：

```python
from ms_enclave.sandbox.model import E2BSandboxManagerConfig

connection = E2BSandboxManagerConfig(
    domain='your-service-domain',
    max_sandboxes=4,
)
```

然后将上例中的 `E2BSandboxManager()` 改为 `E2BSandboxManager(connection)`。`api_key`、`api_url` 也可以通过此配置传入。通常无需手动设置构建模式或镜像地域。

## 使用自己的镜像

没有现成模板时，可以将 `template` 改为 `image`，由服务构建运行环境：

```python
config = E2BSandboxConfig(
    image='your-registry/your-image:tag',
    tools_config=['python_executor', 'shell_executor'],
    sandbox_timeout=300,
)
```

首次使用可能需要等待构建，之后会复用已有模板。只需设置 `template` 或 `image` 其中一个；同时设置时优先使用 `template`。

阿里云需要使用已转换的 `fc-e2b-registry.<region>.cr.aliyuncs.com/...` 镜像，不能直接使用 Docker Hub 镜像。已有源镜像与转换镜像的对应表时，可通过 `E2BSandboxManagerConfig.image_mapping` 配置映射。镜像转换和私有仓库访问权限需提前准备。

## 上传文件与执行命令

在上例的 `async with` 内，可以获取沙箱并上传本地目录：

```python
sandbox = await manager.get_sandbox(sid)
if not await sandbox.put_dir('./data', '/home/user/data'):
    raise RuntimeError('文件上传失败')

result = await sandbox.execute_command(
    ['ls', '/home/user/data'], timeout=30
)
print(result.stdout)
```

上传单个文本文件使用 `put_file`，上传 tar 归档使用 `put_archive`，目标路径需为可写的绝对路径。可以通过命令的 `user`、`cwd`、`env` 参数临时调整用户、目录和环境变量。

E2B 支持 `python_executor` 和 `shell_executor`；`file_operation`、Notebook 和多语言执行工具请使用支持它们的其他后端。详见[内置工具](../guides/builtin-tools.md)。

## 容量与清理

- `max_sandboxes` 默认是 16，限制同时运行或正在创建的沙箱数量。达到上限时，单独创建会等待；可用 `stop_sandbox` 或 `delete_sandbox` 释放不用的沙箱。
- `stop_sandbox` 终止远端沙箱并保留本地信息，成功返回 `True`；`delete_sandbox` 同时删除本地记录。停止或删除后，远端文件和进程不再保留。
- 使用[沙箱池](../guides/sandbox-pool.md)时，通过 `initialize_pool` 创建，默认类型为 E2B。池大小超过可用容量会报错；部分成员创建失败时，请检查返回的 ID 列表，确认实际可用数量。
- 提前释放单个沙箱可调用 `await manager.delete_sandbox(sid)`；通常用 `async with` 即可完成整体清理。可复用的模板不会随沙箱删除。

## 遇到问题时

| 问题 | 处理方式 |
|---|---|
| 提示缺少 API Key 或鉴权失败 | 检查 `E2B_API_KEY`，以及 Key 与服务地址是否匹配。 |
| 模板或镜像构建失败 | 核对模板名称、镜像和访问权限；修正后新建管理器再试。 |
| 命令超时或被取消 | 后端会尝试终止命令；如果沙箱已不可用，删除后重新创建。 |
| 停止返回 `False`，或删除、关闭管理器时报错 | 恢复服务连接后，重试 `delete_sandbox` 或 `manager.stop()`。 |

网络中断时，远端沙箱可能仍在运行。可结合日志中的沙箱 ID、`run_id` 到服务控制台确认和清理资源，不能仅凭本地任务结束判断清理完成。

更多参数及默认值见[配置 API](../api/config.md)。
