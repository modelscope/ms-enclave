# 自定义扩展

ms-enclave 采用高度模块化的设计，支持按需扩展 Tool、Sandbox 和 SandboxManager。本文给出所需接口、注册机制与可运行的最小示例，帮助你快速实现与验证。

## 注册机制总览

项目采用装饰器注册模式（Registry），便于按类型动态创建对象：

* Sandbox：

    * 装饰器：`@register_sandbox(SandboxType.XYZ)`
    * 工厂：`SandboxFactory.create_sandbox(sandbox_type, config, sandbox_id)`

* Tool：

    * 装饰器：`@register_tool('tool_name')`
    * 工厂：`ToolFactory.create_tool('tool_name', **kwargs)`
  
* SandboxManager：

    * 装饰器：`@register_manager(SandboxManagerType.XYZ)`
    * 工厂：`SandboxManagerFactory.create_manager(manager_type, config, **kwargs)`

扩展类型建议：
- 新增 Sandbox 时，通常需要在 `ms_enclave/sandbox/model` 中为 `SandboxType` 扩展一个枚举值（例如：`LOCAL_PROCESS`）。
- 新增 SandboxManager 时，通常需要在 `ms_enclave/sandbox/model` 中为 `SandboxManagerType` 扩展一个枚举值（例如：`LOCAL_INMEM`）。

> 提示：本文所有代码示例均使用英文注释与完整类型标注，符合项目的代码风格。

---

## 自定义 Tool

必须实现/覆写：
- `required_sandbox_type`：声明该工具可运行的沙箱类型（返回 `None` 表示所有类型均可）。
- `async def execute(self, sandbox_context, **kwargs)`：执行工具逻辑，返回 `ToolResult`（字典即可）。
- 可选：构造函数参数 `name/description/parameters/enabled/timeout`。若不需要参数，可以不设置 `parameters`。

注意：
- 框架会通过 `Tool.schema` 暴露 OpenAI 风格的 function schema。若需要严格的参数校验，可传入 `parameters`（Pydantic 模型，参见 `tools/tool_info.py`）。
- 工具与沙箱兼容性：`Tool.is_compatible_with_sandbox` 会根据 `required_sandbox_type` 与 `SandboxType.is_compatible` 判定。

### 示例 A：最小可用工具（不依赖沙箱命令）

```python
# 最少依赖：返回问候语，任何沙箱可用
from typing import Any, Dict, Optional
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.model import SandboxType  # 仅用于类型声明

@register_tool('hello')
class HelloTool(Tool):
    def __init__(self, name: str = 'hello', description: str = 'Say hello', enabled: bool = True):
        super().__init__(name=name, description=description, enabled=enabled)

    @property
    def required_sandbox_type(self) -> Optional[SandboxType]:
        # None => 任何沙箱可用
        return None

    async def execute(self, sandbox_context: Any, name: str = 'world', **kwargs) -> Dict[str, Any]:
        return {'message': f'Hello, {name}!'}
```

使用（以 Docker 沙箱为例）：
```python
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, DockerSandboxConfig
import asyncio

async def main():
    sb = SandboxFactory.create_sandbox(SandboxType.DOCKER, DockerSandboxConfig(image='python:3.11-slim'))
    async with sb:
        await sb.initialize_tools()  # 若你的 start() 未做初始化，这里手动初始化
        result = await sb.execute_tool('hello', {'name': 'ms-enclave'})
        print(result)  # {'message': 'Hello, ms-enclave!'}

asyncio.run(main())
```

### 示例 B：优先在沙箱内执行命令的工具（可回退到本地逻辑）

```python
# 在沙箱内执行 `date` 命令；若不可用则回退到 Python 计算当前时间
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.model import SandboxType

@register_tool('time_teller')
class TimeTellerTool(Tool):
    def __init__(self, name: str = 'time_teller', description: str = 'Tell current time', enabled: bool = True):
        super().__init__(name=name, description=description, enabled=enabled)

    @property
    def required_sandbox_type(self) -> Optional[SandboxType]:
        # DOCKER 工具在 DOCKER、DOCKER_NOTEBOOK 等兼容类型中可用
        return SandboxType.DOCKER

    async def execute(self, sandbox_context: Any, timezone_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        cmd = 'date'
        if timezone_name:
            cmd = f'TZ={timezone_name} date'
        try:
            # 约定：execute_command 返回 (exit_code, stdout, stderr)
            exit_code, out, err = await sandbox_context.execute_command(cmd, timeout=5)
            if exit_code == 0:
                return {'time': out.strip()}
            return {'error': err.strip() or 'unknown error'}
        except Exception:
            # 回退到 Python 计算
            tz = timezone.utc if (timezone_name or '').upper() == 'UTC' else None
            return {'time': datetime.now(tz=tz).isoformat()}
```

启用工具（配置即可注入构造参数；此处无需参数）：
```python
from ms_enclave.sandbox.model import DockerSandboxConfig

config = DockerSandboxConfig(
    image='debian:stable-slim',
    tools_config={
        'hello': {},
        'time_teller': {}
    }
)
```

---

## 自定义 Sandbox

必须实现：
- `sandbox_type`：返回该实现的 `SandboxType`。
- `async def start(self)`：启动沙箱并将 `status` 置为 `RUNNING`，建议在此调用 `await self.initialize_tools()`。
- `async def stop(self)`：停止沙箱，将 `status` 置为 `STOPPED`。
- `async def cleanup(self)`：释放资源。
- `async def execute_command(self, command, timeout=None, stream=True)`：在沙箱内执行命令（若不支持可抛出 `NotImplementedError`）。
- `async def get_execution_context(self)`：返回供工具使用的执行上下文（容器/进程句柄等，若无可返回 `None`）。

最小实现示例：本地进程型沙箱（演示用途）
> 假设你已在 `SandboxType` 中新增 `LOCAL_PROCESS` 枚举值。

```python
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union
from ms_enclave.sandbox.boxes.base import Sandbox, register_sandbox
from ms_enclave.sandbox.model import SandboxType, SandboxStatus, SandboxConfig

CommandResult = Tuple[int, str, str]

@register_sandbox(SandboxType.LOCAL_PROCESS)  # 需先扩展枚举
class LocalProcessSandbox(Sandbox):
    """Run host commands as a 'sandbox' (for demo/dev only)."""

    @property
    def sandbox_type(self) -> SandboxType:
        return SandboxType.LOCAL_PROCESS

    async def start(self) -> None:
        self.update_status(SandboxStatus.RUNNING)
        await self.initialize_tools()

    async def stop(self) -> None:
        self.update_status(SandboxStatus.STOPPED)

    async def cleanup(self) -> None:
        # Nothing to cleanup for this simple demo
        return

    async def execute_command(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        stream: bool = True
    ) -> CommandResult:
        # Run command on host (demo): DO NOT use in production
        if isinstance(command, list):
            shell_cmd = ' '.join(command)
        else:
            shell_cmd = command

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

快速验证：
```python
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, SandboxConfig
import asyncio

async def main():
    sb = SandboxFactory.create_sandbox(SandboxType.LOCAL_PROCESS, SandboxConfig())
    async with sb:
        await sb.initialize_tools()
        # 直接运行 hello 工具（示例 A）
        print(await sb.execute_tool('hello', {'name': 'sandbox'}))
        # 直接运行命令
        print(await sb.execute_command('echo hi'))

asyncio.run(main())
```

> 注意：真实沙箱（如 Docker）需要实现镜像拉取、容器创建/启动、资源限制、挂载等。可参考 `ms_enclave/sandbox/boxes/docker_sandbox.py`。

---

## 自定义 SandboxManager

必须实现（抽象基类 `SandboxManager` 中定义）：
- 生命周期：`start()`, `stop()`
- 沙箱操作：`create_sandbox()`, `get_sandbox_info()`, `list_sandboxes()`, `stop_sandbox()`, `delete_sandbox()`
- 工具执行：`execute_tool()`, `get_sandbox_tools()`
- 统计：`get_stats()`
- 清理：`cleanup_all_sandboxes()`
- 连接池（可选但为抽象方法，需给出最小实现）：`initialize_pool()`, `execute_tool_in_pool()`

最小可运行示例：内存管理器
> 假设你已在 `SandboxManagerType` 中新增 `LOCAL_INMEM` 枚举值。

```python
import asyncio
from typing import Any, Dict, List, Optional, Union
from ms_enclave.sandbox.manager.base import SandboxManager, register_manager
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import (
    SandboxConfig, SandboxInfo, SandboxManagerConfig, SandboxManagerType,
    SandboxStatus, SandboxType, ToolResult
)

@register_manager(SandboxManagerType.LOCAL_INMEM)  # 需先扩展枚举
class LocalInMemoryManager(SandboxManager):
    """A minimal in-memory manager for demo/dev."""

    def __init__(self, config: Optional[SandboxManagerConfig] = None, **kwargs):
        super().__init__(config=config, **kwargs)
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        await self.cleanup_all_sandboxes()
        self._running = False

    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None
    ) -> str:
        sb = SandboxFactory.create_sandbox(sandbox_type, config, sandbox_id)
        await sb.start()
        await sb.initialize_tools()
        self._sandboxes[sb.id] = sb
        # 简单放入池（可选）
        async with self._pool_lock:
            self._sandbox_pool.append(sb.id)
        return sb.id

    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        sb = self._sandboxes.get(sandbox_id)
        return sb.get_info() if sb else None

    async def list_sandboxes(self, status_filter: Optional[SandboxStatus] = None) -> List[SandboxInfo]:
        infos = [sb.get_info() for sb in self._sandboxes.values()]
        if status_filter:
            return [i for i in infos if i.status == status_filter]
        return infos

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            return False
        await sb.stop()
        return True

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        sb = self._sandboxes.pop(sandbox_id, None)
        if not sb:
            return False
        await sb.cleanup()
        # 同步移出池
        async with self._pool_lock:
            try:
                self._sandbox_pool.remove(sandbox_id)
            except ValueError:
                pass
        return True

    async def execute_tool(self, sandbox_id: str, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            raise ValueError(f'Sandbox {sandbox_id} not found')
        if sb.status != SandboxStatus.RUNNING:
            raise ValueError('Sandbox not running')
        return await sb.execute_tool(tool_name, parameters)

    async def get_sandbox_tools(self, sandbox_id: str) -> Dict[str, Any]:
        sb = self._sandboxes.get(sandbox_id)
        if not sb:
            raise ValueError(f'Sandbox {sandbox_id} not found')
        return sb.get_available_tools()

    async def get_stats(self) -> Dict[str, Any]:
        total = len(self._sandboxes)
        running = sum(1 for s in self._sandboxes.values() if s.status == SandboxStatus.RUNNING)
        return {'total': total, 'running': running}

    async def cleanup_all_sandboxes(self) -> None:
        # 停止并清理所有沙箱
        for sb in list(self._sandboxes.values()):
            try:
                await sb.stop()
                await sb.cleanup()
            except Exception:
                pass
        self._sandboxes.clear()
        async with self._pool_lock:
            self._sandbox_pool.clear()

    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict]] = None
    ) -> List[str]:
        if self._pool_initialized:
            return list(self._sandbox_pool)
        size = pool_size or (self.config.pool_size if self.config else 0) or 0
        if size <= 0:
            self._pool_initialized = True
            return []
        st = sandbox_type or (self.config.sandbox_type if self.config else None)
        if not st:
            raise ValueError('sandbox_type required for pool initialization')
        ids: List[str] = []
        for _ in range(size):
            sb_id = await self.create_sandbox(st, config or (self.config.sandbox_config if self.config else None))
            ids.append(sb_id)
        self._pool_initialized = True
        return ids

    async def execute_tool_in_pool(
        self, tool_name: str, parameters: Dict[str, Any], timeout: Optional[float] = None
    ) -> ToolResult:
        # 简单 FIFO：取一个空闲沙箱，执行后归还队列
        async def acquire_one() -> str:
            start = asyncio.get_event_loop().time()
            while True:
                async with self._pool_lock:
                    if self._sandbox_pool:
                        return self._sandbox_pool.popleft()
                if timeout and (asyncio.get_event_loop().time() - start) > timeout:
                    raise TimeoutError('No sandbox available from pool')
                await asyncio.sleep(0.05)

        sandbox_id = await acquire_one()
        try:
            return await self.execute_tool(sandbox_id, tool_name, parameters)
        finally:
            async with self._pool_lock:
                # 若沙箱仍在管理器中，则归还
                if sandbox_id in self._sandboxes:
                    self._sandbox_pool.append(sandbox_id)
```

验证：
```python
from ms_enclave.sandbox.manager.base import SandboxManagerFactory
from ms_enclave.sandbox.model import SandboxManagerType, SandboxType, DockerSandboxConfig
import asyncio

async def main():
    mgr = SandboxManagerFactory.create_manager(SandboxManagerType.LOCAL_INMEM)
    async with mgr:
        sb_id = await mgr.create_sandbox(SandboxType.DOCKER, DockerSandboxConfig(image='python:3.11-slim'))
        print(await mgr.get_sandbox_tools(sb_id))
        print(await mgr.execute_tool(sb_id, 'hello', {'name': 'manager'}))

asyncio.run(main())
```

---

## 开发要点与最佳实践

- 生命周期与状态：
  - 只有在 `SandboxStatus.RUNNING` 时才应执行工具。
  - 在 `start()` 中调用 `await self.initialize_tools()`，确保工具就绪。
- 兼容性：
  - 工具应通过 `required_sandbox_type` 明确要求；若无要求，返回 `None`。
  - `SandboxType.is_compatible` 用于允许子类型复用父类型工具（例如：`DOCKER_NOTEBOOK` 兼容 `DOCKER` 工具）。
- 参数 Schema：
  - 若需要严格参数校验/文档化，在构造 Tool 时传入 `parameters`（Pydantic 模型）。未指定时，schema 的 `parameters` 为 `{}`。
- 简洁代码：
  - 小函数、清晰命名、英文注释、必要的 docstring。
  - 优先使用早返回，避免嵌套。
- 快速验证：
  - 从最小实现开始（如示例 A/B），先本地跑通，再增加复杂度（如连接池、网络、资源限制）。

> 实战建议：扩展新 Sandbox 可直接参考 `ms_enclave/sandbox/boxes/docker_sandbox.py`；扩展 HTTP API 对应修改 `server/server.py` 与 `manager/http_manager.py` 并保证 Pydantic 模型同步。
