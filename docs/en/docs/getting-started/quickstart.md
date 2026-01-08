# Quickstart

`ms-enclave` offers two primary usage patterns to fit different integration needs:

1. SandboxFactory: create a sandbox instance directly — minimal overhead, ideal for scripts, tests, or one-off tasks.
2. SandboxManagerFactory: orchestrate sandboxes via a manager — suitable for services and background apps, with lifecycle management, pool prewarm, and auto-cleanup.

Both approaches are shown below.

## Option 1: Lightweight script

Create a sandbox instance and use `async with` to ensure cleanup on exit.

### When to use

- Single-run jobs and quick scripts
- Unit tests requiring a fresh, clean environment per case
- Small experiments
- Need direct access to low-level sandbox methods

### Example

Save as `quickstart_script.py`:

```python
import asyncio
from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType

async def main():
    # 1) Configure sandbox and enable tools
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},
            'file_operation': {},
        }
    )

    print("Starting sandbox...")
    # 2) Create and start sandbox
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print(f"Sandbox ready ID: {sandbox.id}")

        # 3) Write a file
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/hello.txt',
            'content': 'Hello from ms-enclave!'
        })
        
        # 4) Execute Python code
        result = await sandbox.execute_tool('python_executor', {
            'code': """
print('Reading file...')
with open('/sandbox/hello.txt', 'r') as f:
    content = f.read()
print(f'Content: {content}')
"""
        })
        
        # 5) Check output
        print("Execution result:", result.output)

if __name__ == '__main__':
    asyncio.run(main())
```

### Notes

1. `SandboxFactory` returns an async context manager for the sandbox.
2. `DockerSandboxConfig`:
   - `image`: Docker image to ensure consistent environment.
   - `tools_config`: only tools explicitly enabled here can be used inside the sandbox.
3. `execute_tool(name, params)`: call tool by name with its parameters.
4. Lifecycle: `async with` guarantees `stop()` and container cleanup.

### Run

```bash
python quickstart_script.py
```

The first run may pull `python:3.11-slim`, which can take a while.

---

## Option 2: Application integration (Manager)

For web services or long-running apps, use a manager. It supports local mode and seamless switch to remote HTTP mode, plus pool prewarming.

### When to use

- Backend services serving concurrent requests
- Long-running processes with auto-cleanups
- Performance-sensitive scenarios (pool prewarming)
- Distributed deployments (remote HTTP server)

### Example

Save as `quickstart_app.py`:

```python
import asyncio
from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType, SandboxManagerConfig, SandboxManagerType

async def main():
    # 1) Manager config
    manager_config = SandboxManagerConfig(cleanup_interval=600)

    print("Initializing manager...")
    # 2) Create local manager (or set base_url for HTTP mode)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, 
        config=manager_config
    ) as manager:
        
        # 3) Sandbox config
        sb_config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # 4) Create sandbox and get id
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, sb_config)
        print(f"Sandbox ID: {sandbox_id}")

        # 5) Execute a tool via manager
        result = await manager.execute_tool(
            sandbox_id, 
            'python_executor', 
            {'code': 'import sys; print(f"Python Version: {sys.version}")'}
        )
        print(f"Output:\n{result.output.strip()}")

        # 6) List sandboxes
        sandboxes = await manager.list_sandboxes()
        print(f"Active sandboxes: {len(sandboxes)}")

if __name__ == '__main__':
    asyncio.run(main())
```

### Notes

- `SandboxManagerFactory` creates a local or HTTP manager depending on `manager_type` or `base_url`.
- Manager API returns `sandbox_id` (string) instead of sandbox object.
- `LocalSandboxManager` includes a background cleaner for stale/errored sandboxes.

### Run

```bash
python quickstart_app.py
```
---

## Method 3: Agent Tool Execution

When your Agent supports OpenAI Tools (function calling), you can expose sandbox tools as callable functions, allowing the model to trigger tools and execute them in the sandbox.

### Use Cases
- Need the LLM to autonomously decide when to run Python code or Shell commands
- Want to inject safely controlled code execution capabilities into the Agent

### Usage Steps
1) Create a manager and sandbox, and enable tools
2) Retrieve the sandbox's tool schema (OpenAI-compatible format)
3) Call the model (tools=...), collect tool_calls
4) Execute corresponding tools in the sandbox and append tool messages
5) Let the model generate the final answer again

### Code Example
````python
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
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", 
        api_key=os.environ.get("DASHSCOPE_API_KEY")
    )

    async with SandboxManagerFactory.create_manager() as manager:
        config = DockerSandboxConfig(
            image="python:3.11-slim",
            tools_config={
                "python_executor": {}, 
                "shell_executor": {}, 
                "file_operation": {}
            },
            volumes={os.path.abspath("./output"): {"bind": "/sandbox/data", "mode": "rw"}},
        )

        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        # Fetch available tools from the sandbox and convert to OpenAI format
        available_tools = await manager.get_sandbox_tools(sandbox_id)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You can run Python code and shell commands inside a managed sandbox using provided tools. "
                    "Always use tools to perform code execution or shell operations, then summarize results concisely."
                ),
            },
            {
                "role": "user",
                "content": (
                    "1) Run Python to print 'hi from sandbox' and compute 123456*654321.\n"
                    "2) Run a shell command to list /sandbox/data directory.\n"
                    "Finally, summarize the outputs."
                ),
            },
        ]

        # First model call with tools bound
        completion = client.chat.completions.create(
            model="qwen-plus", messages=messages, tools=list(available_tools.values()), tool_choice="auto"
        )
        msg = completion.choices[0].message

        messages.append(msg.model_dump())

        # Handle tool calls; execute in sandbox and feed results back to the model
        tool_summaries: List[str] = []
        if getattr(msg, "tool_calls", None):
            for call in msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                tool_result = await manager.execute_tool(sandbox_id, name, args)
                tool_summaries.append(f"{name} => {args} => {tool_result.status}")
                messages.append(
                    {
                        "role": "tool",
                        "content": tool_result.model_dump_json(),
                        "tool_call_id": call.id,
                        "name": name,
                    }
                )

            # Ask the model to produce the final answer after tool results are added
            final = client.chat.completions.create(model="qwen-plus", messages=messages)
            final_text = final.choices[0].message.content or ""
            print("Model output:" + "=" * 20)
            print(final_text)
        else:
            # If no tool calls were made, just print the model output
            print("Model output:" + "=" * 20)
            print(msg.content or "")

        # Minimal summary of executed tools
        if tool_summaries:
            print("Executed tools:" + "=" * 20)
            for s in tool_summaries:
                print(f"- {s}")


def main() -> None:
    """Entry point."""
    asyncio.run(run_agent_with_sandbox())

if __name__ == "__main__":
    main()

````

> Tip: Any model/service compatible with OpenAI Tools can use this pattern; you need to pass the sandbox tool schema to tools and execute each tool_call sequentially.

Output Example:
```text
[INFO:ms_enclave] Local sandbox manager started
[INFO:ms_enclave] Created and started sandbox a3odo8es of type docker
[INFO:ms_enclave] [📦 a3odo8es] hi from sandbox
[INFO:ms_enclave] [📦 a3odo8es] hello.txt
Model output:====================
- Python printed: `hi from sandbox`
- Computed `123456 * 654321 = 80779853376`
- The `/sandbox/data` directory contains one file: `hello.txt`

Summary: The sandbox successfully executed the print and multiplication tasks, and the data directory listing revealed a single file named `hello.txt`.
Executed tools:====================
- python_executor => {'code': "print('hi from sandbox')\n123456 * 654321"} => success
- shell_executor => {'command': 'ls /sandbox/data'} => success
[INFO:ms_enclave] Cleaning up 1 sandboxes
[INFO:ms_enclave] Deleted sandbox a3odo8es
[INFO:ms_enclave] Local sandbox manager stopped
```

## Summary

- **For experiments, scripts, unit tests** -> Recommended: **SandboxFactory**.
- **For backend services, task scheduling, production environments** -> Recommended: **SandboxManagerFactory**.
- **Need model to autonomously call tools** -> Use **SandboxManager** combined with OpenAI Tools.