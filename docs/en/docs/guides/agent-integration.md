# LLM Agent Integration (OpenAI Tools)

`ms-enclave` tool schemas are OpenAI Function Calling-compatible, so any model that supports OpenAI Tools (OpenAI, DashScope/Qwen, self-hosted OpenAI-compatible servers, etc.) can call sandbox tools directly.

## Flow

1. Create a manager and a sandbox (enable the needed tools)
2. `get_sandbox_tools(sandbox_id)` returns an OpenAI-compatible schema
3. Call the model with `tools=...`
4. Parse each `tool_call` and run it inside the sandbox
5. Append a `tool`-role message with the result to `messages`
6. Call the model again to get the final answer

## Full example (DashScope / qwen-plus)

```python
import asyncio
import json
import os
from openai import OpenAI

from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def run_agent():
    client = OpenAI(
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        api_key=os.environ['DASHSCOPE_API_KEY'],
    )

    async with SandboxManagerFactory.create_manager() as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={
                'python_executor': {},
                'shell_executor': {},
                'file_operation': {},
            },
            volumes={os.path.abspath('./output'): {'bind': '/sandbox/data', 'mode': 'rw'}},
        )
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        # 1) Fetch tool schemas
        tools = await manager.get_sandbox_tools(sandbox_id)

        messages = [
            {'role': 'system', 'content':
                'You can run Python and shell commands inside a managed sandbox '
                'via the provided tools. Always use tools to compute and summarize results.'},
            {'role': 'user', 'content':
                '1) Use Python to compute 123456 * 654321.\n'
                '2) Use shell to list /sandbox/data.\n'
                'Then summarize.'},
        ]

        # 2) First call: model decides which tools to invoke
        completion = client.chat.completions.create(
            model='qwen-plus',
            messages=messages,
            tools=list(tools.values()),
            tool_choice='auto',
        )
        msg = completion.choices[0].message
        messages.append(msg.model_dump())

        # 3) Execute tool_calls one by one
        for call in (msg.tool_calls or []):
            args = json.loads(call.function.arguments or '{}')
            result = await manager.execute_tool(sandbox_id, call.function.name, args)
            messages.append({
                'role': 'tool',
                'tool_call_id': call.id,
                'name': call.function.name,
                'content': result.model_dump_json(),
            })

        # 4) Let the model produce the final answer based on tool results
        final = client.chat.completions.create(model='qwen-plus', messages=messages)
        print(final.choices[0].message.content)

asyncio.run(run_agent())
```

## Other models

Any OpenAI-Tools-compatible endpoint works. Just swap `base_url` and `model`:

- Self-hosted vLLM / Ollama: `base_url='http://localhost:8000/v1'`
- OpenAI: drop `base_url`, `model='gpt-4o-mini'`
- DashScope (shown above): `qwen-plus`, `qwen-max`, etc.

## Practical tips

- **Limit the toolset**: fewer tools → better routing decisions. Only enable tools the task actually needs.
- **Truncate results**: `ToolResult.output` can be large. Trim or summarize before feeding it back if it would blow the context window.
- **Multi-round calls**: if the first round isn't enough, loop on `tool_calls` until the model returns a plain text answer.
- **Error feedback**: include the `error` field in the `tool` message so the model can decide whether to retry or change strategy.
