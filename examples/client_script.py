import asyncio

from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType


async def main():
    # 连接到远程服务器
    async with SandboxManagerFactory.create_manager(base_url='http://127.0.0.1:8000') as manager:

        # 创建沙箱（在服务器端创建 Docker 容器）
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)
        print(f'远程沙箱 ID: {sandbox_id}')

        # 执行工具
        result = await manager.execute_tool(sandbox_id, 'python_executor', {
            'code': 'import platform; print(platform.node())'
        })
        print(f'远程执行结果: {result.output}')


if __name__ == '__main__':
    asyncio.run(main())
