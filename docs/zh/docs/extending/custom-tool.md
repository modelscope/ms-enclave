# 自定义 Tool

## 必须实现

- `required_sandbox_types`：声明该工具可运行的沙箱类型列表（`None` 表示任意沙箱）。
- `async def execute(self, sandbox_context, **kwargs)`：执行逻辑，返回 `ToolResult` 或字典（框架会自动包装）。
- 可选：构造函数参数 `name / description / parameters / enabled / timeout`。

工具与沙箱的兼容性由 `Tool.is_compatible_with_sandbox` 根据 `required_sandbox_types` 和 `SandboxType.is_compatible` 共同判定。

## 示例 A：最小工具（不依赖沙箱命令）

```python
from typing import Any, Dict, List, Optional
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.model import SandboxType

@register_tool('hello')
class HelloTool(Tool):
    def __init__(self, name: str = 'hello', description: str = 'Say hello', enabled: bool = True):
        super().__init__(name=name, description=description, enabled=enabled)

    @property
    def required_sandbox_types(self) -> Optional[List[SandboxType]]:
        return None  # 任意沙箱可用

    async def execute(self, sandbox_context: Any, name: str = 'world', **kwargs) -> Dict[str, Any]:
        return {'message': f'Hello, {name}!'}
```

启用并调用：

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import SandboxType, DockerSandboxConfig

async def main():
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'hello': {}},
    )
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sb:
        print(await sb.execute_tool('hello', {'name': 'ms-enclave'}))
        # {'message': 'Hello, ms-enclave!'}

asyncio.run(main())
```

## 示例 B：优先调用沙箱内命令的工具

声明 `required_sandbox_types=[SandboxType.DOCKER]`，并通过 `sandbox_context.execute_command` 运行命令；若不可用就回退到本地逻辑。

```python
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ms_enclave.sandbox.tools.base import Tool, register_tool
from ms_enclave.sandbox.model import SandboxType

@register_tool('time_teller')
class TimeTellerTool(Tool):
    def __init__(self, name: str = 'time_teller', description: str = 'Tell current time', enabled: bool = True):
        super().__init__(name=name, description=description, enabled=enabled)

    @property
    def required_sandbox_types(self) -> Optional[List[SandboxType]]:
        return [SandboxType.DOCKER]  # DOCKER 与其子类型（如 DOCKER_NOTEBOOK）皆可

    async def execute(self, sandbox_context: Any, timezone_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        cmd = f'TZ={timezone_name} date' if timezone_name else 'date'
        try:
            exit_code, out, err = await sandbox_context.execute_command(cmd, timeout=5)
            if exit_code == 0:
                return {'time': out.strip()}
            return {'error': err.strip() or 'unknown error'}
        except Exception:
            tz = timezone.utc if (timezone_name or '').upper() == 'UTC' else None
            return {'time': datetime.now(tz=tz).isoformat()}
```

## 严格参数校验

如果希望模型调用时被校验/补全参数，给 Tool 构造传 `parameters`（Pydantic 模型，见 `tools/tool_info.py`）。schema 会自动反映到 OpenAI Function 定义里。

不需要校验时省略即可，schema 中 `parameters` 会被置为 `{}`。
