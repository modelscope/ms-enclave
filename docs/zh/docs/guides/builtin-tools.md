# 内置工具一览

本节列出内置工具的参数与典型用法。工具必须先在 `tools_config` 中声明才会注册。

## python_executor

在沙箱中以脚本方式执行 Python 代码（无状态：每次独立进程，变量不跨调用保留）。

| 参数 | 类型 | 说明 |
|---|---|---|
| `code` | str | 必填，要执行的 Python 代码 |

```python
result = await sandbox.execute_tool('python_executor', {
    'code': 'print(sum(range(100)))'
})
print(result.output)  # 4950
```

> 若需要跨多次调用保留变量（例如训练 / 数据探索场景），改用 [Notebook 沙箱](notebook-sandbox.md) 的 `notebook_executor`。

## shell_executor

执行 Shell 命令（默认 `/bin/bash`）。

| 参数 | 类型 | 说明 |
|---|---|---|
| `command` | str | 必填，命令字符串 |
| `timeout` | int | 可选，超时秒数 |

```python
result = await sandbox.execute_tool('shell_executor', {
    'command': 'uname -a && date',
})
print(result.output)
```

## file_operation

对沙箱内文件系统做读 / 写 / 列出 / 删除。

| 参数 | 类型 | 说明 |
|---|---|---|
| `operation` | str | 必填，`read` / `write` / `list` / `delete` |
| `file_path` | str | 必填，沙箱内路径，通常以 `/sandbox/` 开头 |
| `content` | str | `write` 时必填 |

```python
# 写文件
await sandbox.execute_tool('file_operation', {
    'operation': 'write',
    'file_path': '/sandbox/hello.txt',
    'content': 'hello',
})

# 读文件
res = await sandbox.execute_tool('file_operation', {
    'operation': 'read',
    'file_path': '/sandbox/hello.txt',
})
print(res.output)  # hello
```

## multi_code_executor

多语言代码执行，依赖 `volcengine/sandbox-fusion` 镜像。支持 python / cpp / csharp / go / java / nodejs / ts / rust / php / bash / pytest / jest / go_test / lua / r / perl / d_ut / ruby / scala / julia / kotlin_script / verilog / lean / swift / racket。

| 参数 | 类型 | 说明 |
|---|---|---|
| `language` | str | 必填，语言标识 |
| `code` | str | 必填，源码 |

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

仅在 `SandboxType.DOCKER_NOTEBOOK` 中可用。详见 [Notebook 沙箱](notebook-sandbox.md)。

## ToolResult

所有工具返回 `ToolResult`：

| 字段 | 含义 |
|---|---|
| `status` | `success` / `error` 等枚举 |
| `output` | 标准输出（字符串） |
| `error` | 错误信息（失败时） |
| `tool_name` | 触发的工具名 |

序列化使用 `result.model_dump_json()`（兼容 Pydantic）。
