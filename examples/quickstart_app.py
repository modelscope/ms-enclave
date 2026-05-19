import asyncio

from ms_enclave.sandbox.manager import SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxManagerConfig, SandboxManagerType, SandboxType


async def main():
    # 1. 配置管理器
    # 如需使用远程服务，可配置 base_url；这里演示本地模式
    manager_config = SandboxManagerConfig(cleanup_interval=600)  # 每10分钟后台清理一次过期沙箱

    print('正在初始化管理器...')
    # 2. 创建管理器
    # 显式指定 Local 类型，或者不传参也会默认使用 Local
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL,
        config=manager_config
    ) as manager:

        # 3. 配置沙箱
        sb_config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )

        # 4. 通过管理器创建沙箱
        # 管理器会跟踪这个沙箱的状态，并返回 sandbox_id
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, sb_config)
        print(f'沙箱已创建 ID: {sandbox_id}')

        # 5. 执行工具
        # 所有的操作都通过 manager 代理进行，需传入 sandbox_id
        print('正在执行代码...')
        result = await manager.execute_tool(
            sandbox_id,
            'python_executor',
            {'code': 'import sys; print(f"Python Version: {sys.version}")'}
        )
        print(f'输出结果:\n{result.output.strip()}')

        # 6. 获取沙箱列表
        # 查看当前管理器纳管的所有沙箱
        sandboxes = await manager.list_sandboxes()
        print(f'当前活跃沙箱数: {len(sandboxes)}')

if __name__ == '__main__':
    asyncio.run(main())
