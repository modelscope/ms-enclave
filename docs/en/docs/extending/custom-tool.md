# Custom Tool

## Must implement

- `required_sandbox_types`: list of sandbox types this tool can run in (`None` = any).
- `async def execute(self, sandbox_context, **kwargs)`: the tool logic. Return a `ToolResult` or a plain dict (the framework will wrap it).
- Optional constructor args: `name / description / parameters / enabled / timeout`.

Compatibility between a tool and a sandbox is decided by `Tool.is_compatible_with_sandbox`, which combines `required_sandbox_types` with `SandboxType.is_compatible`.

## Example A: minimal tool (no sandbox commands)

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
        return None  # any sandbox

    async def execute(self, sandbox_context: Any, name: str = 'world', **kwargs) -> Dict[str, Any]:
        return {'message': f'Hello, {name}!'}
```

Enable and call:

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

## Example B: prefer in-sandbox commands

Declare `required_sandbox_types=[SandboxType.DOCKER]` and run commands via `sandbox_context.execute_command`; fall back to local logic when not available.

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
        return [SandboxType.DOCKER]  # DOCKER and its subtypes (e.g. DOCKER_NOTEBOOK)

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

## Strict parameter validation

For validated / documented parameters when the model calls the tool, pass `parameters` (a Pydantic model — see `tools/tool_info.py`) to the Tool constructor. The schema is automatically reflected in the OpenAI function definition.

Skip it when not needed — `parameters` in the schema becomes `{}`.
