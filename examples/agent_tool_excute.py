import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType


async def run_agent_with_sandbox() -> None:
    """
    Create a sandbox, bind tools to an agent (qwen-plus via DashScope), and execute tool calls.
    Prints final model output and minimal tool execution results.
    """

    client = OpenAI(
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        api_key=os.environ.get('DASHSCOPE_API_KEY')
    )

    async with SandboxManagerFactory.create_manager() as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={
                'python_executor': {},
                'shell_executor': {},
                'file_operation': {}
            },
            volumes={os.path.abspath('./output'): {'bind': '/sandbox/data', 'mode': 'rw'}},
        )

        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        # Fetch available tools from the sandbox and convert to OpenAI format
        available_tools = await manager.get_sandbox_tools(sandbox_id)

        messages: List[Dict[str, Any]] = [
            {
                'role': 'system',
                'content': (
                    'You can run Python code and shell commands inside a managed sandbox using provided tools. '
                    'Always use tools to perform code execution or shell operations, then summarize results concisely.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    "1) Run Python to print 'hi from sandbox' and compute 123456*654321.\n"
                    '2) Run a shell command to list /sandbox/data directory.\n'
                    'Finally, summarize the outputs.'
                ),
            },
        ]

        # First model call with tools bound
        completion = client.chat.completions.create(
            model='qwen-plus', messages=messages, tools=list(available_tools.values()), tool_choice='auto'
        )
        msg = completion.choices[0].message

        messages.append(msg.model_dump())

        # Handle tool calls; execute in sandbox and feed results back to the model
        tool_summaries: List[str] = []
        if getattr(msg, 'tool_calls', None):
            for call in msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or '{}')
                tool_result = await manager.execute_tool(sandbox_id, name, args)
                tool_summaries.append(f'{name} => {args} => {tool_result.status}')
                messages.append(
                    {
                        'role': 'tool',
                        'content': tool_result.model_dump_json(),
                        'tool_call_id': call.id,
                        'name': name,
                    }
                )

            # Ask the model to produce the final answer after tool results are added
            final = client.chat.completions.create(model='qwen-plus', messages=messages)
            final_text = final.choices[0].message.content or ''
            print('Model output:' + '=' * 20)
            print(final_text)
        else:
            # If no tool calls were made, just print the model output
            print('Model output:' + '=' * 20)
            print(msg.content or '')

        # Minimal summary of executed tools
        if tool_summaries:
            print('Executed tools:' + '=' * 20)
            for s in tool_summaries:
                print(f'- {s}')


def main() -> None:
    """Entry point."""
    asyncio.run(run_agent_with_sandbox())



if __name__ == '__main__':
    main()
