# Built-in Tools

This page documents the parameters and typical usage of built-in tools. A tool must be declared in `tools_config` to be registered.

## python_executor

Run Python code in the sandbox as a script (stateless: a fresh process per call; variables don't persist between calls).

| Parameter | Type | Description |
|---|---|---|
| `code` | str | Required, the Python source to execute |

```python
result = await sandbox.execute_tool('python_executor', {
    'code': 'print(sum(range(100)))'
})
print(result.output)  # 4950
```

> To keep variables across calls (data exploration, training, etc.), use the [Notebook sandbox](notebook-sandbox.md)'s `notebook_executor`.

## shell_executor

Run shell commands (default `/bin/bash`).

| Parameter | Type | Description |
|---|---|---|
| `command` | str | Required, the command string |
| `timeout` | int | Optional, seconds |

```python
result = await sandbox.execute_tool('shell_executor', {
    'command': 'uname -a && date',
})
print(result.output)
```

## file_operation

Read / write / list / delete files inside the sandbox.

| Parameter | Type | Description |
|---|---|---|
| `operation` | str | Required, one of `read` / `write` / `list` / `delete` |
| `file_path` | str | Required, sandbox path, typically starts with `/sandbox/` |
| `content` | str | Required when `operation='write'` |

```python
# Write
await sandbox.execute_tool('file_operation', {
    'operation': 'write',
    'file_path': '/sandbox/hello.txt',
    'content': 'hello',
})

# Read
res = await sandbox.execute_tool('file_operation', {
    'operation': 'read',
    'file_path': '/sandbox/hello.txt',
})
print(res.output)  # hello
```

## multi_code_executor

Multi-language code execution, requires the `volcengine/sandbox-fusion` image. Supports python / cpp / csharp / go / java / nodejs / ts / rust / php / bash / pytest / jest / go_test / lua / r / perl / d_ut / ruby / scala / julia / kotlin_script / verilog / lean / swift / racket.

| Parameter | Type | Description |
|---|---|---|
| `language` | str | Required, language identifier |
| `code` | str | Required, source code |

```python
config = DockerSandboxConfig(
    image='volcengine/sandbox-fusion:server-20250609',
    tools_config={'multi_code_executor': {}},
)
async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sb:
    res = await sb.execute_tool('multi_code_executor', {
        'language': 'cpp',
        'code': '#include <iostream>\nint main(){std::cout<<"hi";}\n',
    })
    print(res.output)  # hi
```

## notebook_executor

Only available in `SandboxType.DOCKER_NOTEBOOK`. See [Notebook sandbox](notebook-sandbox.md).

## ToolResult

All tools return a `ToolResult`:

| Field | Meaning |
|---|---|
| `status` | `success` / `error` etc. enum |
| `output` | stdout (string) |
| `error` | error info (on failure) |
| `tool_name` | the triggered tool name |

Serialize via `result.model_dump_json()` (Pydantic-compatible).
