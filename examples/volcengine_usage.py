"""Example: use the VolcEngine / SandboxFusion stateless sandbox.

Prerequisite — start the SandboxFusion HTTP service manually::

    docker run -it -p 8080:8080 \
        vemlp-cn-beijing.cr.volces.com/preset-images/code-sandbox:server-20250609

Then run::

    python examples/volcengine_usage.py
"""

from __future__ import annotations

import asyncio

from ms_enclave.sandbox.manager import VolcengineSandboxManager
from ms_enclave.sandbox.model import SandboxType, VolcengineSandboxConfig, VolcengineSandboxManagerConfig


async def main() -> None:
    manager_config = VolcengineSandboxManagerConfig(
        base_url='http://localhost:8080',
        max_concurrency=4,
        request_timeout=30.0,
    )

    sandbox_config = VolcengineSandboxConfig(
        tools_config=['python_executor', 'shell_executor', 'multi_code_executor'],
    )

    async with VolcengineSandboxManager(config=manager_config) as manager:
        sandbox_id = await manager.create_sandbox(SandboxType.VOLCENGINE, sandbox_config)
        print(f'Created sandbox: {sandbox_id}')
        print('Available tools:', list((await manager.get_sandbox_tools(sandbox_id)).keys()))

        # 1) Python
        r = await manager.execute_tool(
            sandbox_id,
            'python_executor',
            {'code': 'print("hello from python:", 1 + 2)'},
        )
        print('\n[python_executor]', r.status.value)
        print('stdout:', r.output)
        if r.error:
            print('stderr:', r.error)

        # 2) Shell
        r = await manager.execute_tool(
            sandbox_id,
            'shell_executor',
            {'command': 'echo hello from bash && uname -a'},
        )
        print('\n[shell_executor]', r.status.value)
        print('stdout:', r.output)
        if r.error:
            print('stderr:', r.error)

        # 3) Multi-language: C++
        cpp_code = (
            '#include <iostream>\n'
            'int main() {\n'
            '    std::cout << "hello from c++" << std::endl;\n'
            '    return 0;\n'
            '}\n'
        )
        r = await manager.execute_tool(
            sandbox_id,
            'multi_code_executor',
            {'language': 'cpp', 'code': cpp_code},
        )
        print('\n[multi_code_executor / cpp]', r.status.value)
        print('stdout:', r.output)
        if r.error:
            print('stderr:', r.error)


if __name__ == '__main__':
    asyncio.run(main())
