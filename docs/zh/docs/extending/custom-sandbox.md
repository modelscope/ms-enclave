# 自定义 Sandbox

## 必须实现

- `sandbox_type`：返回对应的 `SandboxType` 枚举值。
- `async def start(self)`：启动沙箱、把 `status` 置为 `RUNNING`，建议在最后调用 `await self.initialize_tools()`。
- `async def stop(self)`：停止沙箱、`status` 置为 `STOPPED`。
- `async def cleanup(self)`：释放资源（容器删除、网络回收等）。
- `async def execute_command(self, command, timeout=None, stream=True)`：在沙箱内执行命令。不支持的实现可抛 `NotImplementedError`。
- `async def get_execution_context(self)`：返回供工具使用的执行上下文（容器/进程句柄等），无可返回 `None`。

新沙箱类型一般需要先扩展 `SandboxType` 枚举，例如新增 `LOCAL_PROCESS`。

## 完整示例：本地进程沙箱（仅演示）

> ⚠️ 直接在宿主机执行命令缺乏隔离，**不要用于生产**。这里只是演示需要实现哪些方法。

```python
import asyncio
from typing import Any, List, Optional, Tuple, Union
from ms_enclave.sandbox.boxes.base import Sandbox, register_sandbox
from ms_enclave.sandbox.model import SandboxType, SandboxStatus

CommandResult = Tuple[int, str, str]

@register_sandbox(SandboxType.LOCAL_PROCESS)  # 需先扩展枚举
class LocalProcessSandbox(Sandbox):
    """Run host commands as a 'sandbox' (demo only)."""

    @property
    def sandbox_type(self) -> SandboxType:
        return SandboxType.LOCAL_PROCESS

    async def start(self) -> None:
        self.update_status(SandboxStatus.RUNNING)
        await self.initialize_tools()

    async def stop(self) -> None:
        self.update_status(SandboxStatus.STOPPED)

    async def cleanup(self) -> None:
        return

    async def execute_command(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        stream: bool = True,
    ) -> CommandResult:
        shell_cmd = ' '.join(command) if isinstance(command, list) else command
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            if timeout:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            else:
                stdout, stderr = await proc.communicate()
        except asyncio.TimeoutError:
            proc.kill()
            return 124, '', 'command timed out'
        return proc.returncode, (stdout or b'').decode(), (stderr or b'').decode()

    async def get_execution_context(self) -> Any:
        return None
```

## 快速验证

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, SandboxConfig

async def main():
    sb = SandboxFactory.create_sandbox(SandboxType.LOCAL_PROCESS, SandboxConfig())
    async with sb:
        await sb.initialize_tools()
        print(await sb.execute_tool('hello', {'name': 'sandbox'}))
        print(await sb.execute_command('echo hi'))

asyncio.run(main())
```

## 真实实现要点

真实的沙箱通常还要：

- **镜像/资源准备**：拉镜像、检查 socket 权限、设置资源限制。
- **状态机健壮**：所有错误都要把 `status` 置为 `ERROR` 并记录 `metadata['error']`。
- **可观测性**：把容器 id、PID、关键事件写入日志，配合 `get_info()` 暴露给上层。
- **并发安全**：`execute_command` 可能被并发调用，注意是否需要锁。

参考实现：[`ms_enclave/sandbox/boxes/docker_sandbox.py`](https://github.com/modelscope/ms-enclave/blob/main/ms_enclave/sandbox/boxes/docker_sandbox.py)。
