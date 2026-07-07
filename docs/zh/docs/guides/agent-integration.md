# 接入 LLM Agent（OpenAI Tools）

`ms-enclave` 的工具 schema 与 OpenAI Function Calling 格式兼容，因此任何支持 OpenAI Tools 的模型（OpenAI、DashScope/通义、本地兼容服务等）都可以直接把沙箱工具作为可调用函数注入。

## 流程概览

1. 创建管理器与沙箱（启用所需工具）
2. `get_sandbox_tools(sandbox_id)` 获取 OpenAI 兼容的 schema
3. 调用模型，传入 `tools=...`
4. 解析 `tool_calls`，在沙箱中执行每个调用
5. 把 `tool` 角色的结果消息追加回 `messages`
6. 再调用一次模型生成最终答复

## 完整示例（DashScope / qwen-plus）

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

        # 1) 拿工具 schema
        tools = await manager.get_sandbox_tools(sandbox_id)

        messages = [
            {'role': 'system', 'content':
                'You can run Python and shell commands inside a managed sandbox '
                'via provided tools. Always use tools to compute and summarize results.'},
            {'role': 'user', 'content':
                '1) Use Python to compute 123456 * 654321.\n'
                '2) Use shell to list /sandbox/data.\n'
                'Then summarize.'},
        ]

        # 2) 第一次调用，模型决定调哪些工具
        completion = client.chat.completions.create(
            model='qwen-plus',
            messages=messages,
            tools=list(tools.values()),
            tool_choice='auto',
        )
        msg = completion.choices[0].message
        messages.append(msg.model_dump())

        # 3) 逐个执行 tool_calls
        for call in (msg.tool_calls or []):
            args = json.loads(call.function.arguments or '{}')
            result = await manager.execute_tool(sandbox_id, call.function.name, args)
            messages.append({
                'role': 'tool',
                'tool_call_id': call.id,
                'name': call.function.name,
                'content': result.model_dump_json(),
            })

        # 4) 让模型基于工具结果生成最终答复
        final = client.chat.completions.create(model='qwen-plus', messages=messages)
        print(final.choices[0].message.content)

asyncio.run(run_agent())
```

## 替换为其他模型

任何兼容 OpenAI Tools 协议的服务都可以替换 `base_url` 与 `model`，例如：

- 自托管 vLLM / Ollama：`base_url='http://localhost:8000/v1'`
- OpenAI 原生：去掉 `base_url`，`model='gpt-4o-mini'`
- 阿里云 DashScope：示例中的 `qwen-plus`、`qwen-max` 等

## 实战建议

- **限制工具数量**：暴露给模型的工具越少，调用决策越准。按场景只启用必要的工具。
- **结果裁剪**：`ToolResult.output` 可能很长，超过模型上下文时先截断或摘要再喂回去。
- **多轮调用**：如果一次没完成，可循环检查 `tool_calls`，每轮都执行并回喂，直至模型返回纯文本答复。
- **错误返回**：工具执行失败时，把 `error` 字段也写进 `tool` 消息，让模型自行决定重试或换路径。
