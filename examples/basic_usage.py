import asyncio
import os
import shutil

from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.manager import HttpSandboxManager, LocalSandboxManager, SandboxManagerFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxManagerConfig, SandboxManagerType, SandboxType

# ==========================================
# 1. 典型使用场景
# ==========================================

async def demo_sandbox_factory():
    """
    1.1 快速开始：SandboxFactory (最轻量)
    适合脚本或一次性任务。
    """
    print('\n--- Demo: SandboxFactory ---')
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}}
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        result = await sandbox.execute_tool('python_executor', {
            'code': 'import sys; print(f"Python {sys.version.split()[0]}")'
        })
        print(f'[SandboxFactory] Output: {result.output.strip()}')


async def demo_manager_factory():
    """
    1.2 统一管理入口：SandboxManagerFactory
    自动选择本地或远程管理器。
    """
    print('\n--- Demo: SandboxManagerFactory ---')
    cfg = SandboxManagerConfig(cleanup_interval=600)
    async with SandboxManagerFactory.create_manager(
        manager_type=SandboxManagerType.LOCAL, config=cfg
    ) as manager:
        print(f'[ManagerFactory] Created manager: {type(manager).__name__}')


async def demo_local_manager():
    """
    1.3 本地编排：LocalSandboxManager (多任务并行)
    适合在同一进程内需要创建、管理多个沙箱。
    """
    print('\n--- Demo: LocalSandboxManager ---')
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(tools_config={'shell_executor': {}})
        # 创建沙箱
        sandbox_id = await manager.create_sandbox(SandboxType.DOCKER, config)

        # 执行工具
        res = await manager.execute_tool(
            sandbox_id, 'shell_executor', {'command': 'echo "Hello Local Manager"'}
        )
        print(f'[LocalManager] Output: {res.output.strip()}')

        # 获取列表
        sandboxes = await manager.list_sandboxes()
        print(f'[LocalManager] Active sandboxes: {len(sandboxes)}')

        # 手动清理（在 async with 退出时其实也会清理，这里演示显式调用）
        await manager.delete_sandbox(sandbox_id)


async def demo_http_manager():
    """
    1.4 远程管理：HttpSandboxManager
    需要先启动 server。这里加了 try-except 以防止未启动 server 导致脚本 crash。
    """
    print('\n--- Demo: HttpSandboxManager ---')
    try:
        # 假设服务运行在本地 8000 端口
        async with HttpSandboxManager(base_url='http://127.0.0.1:8000') as manager:
            # 简单的连通性测试，如果连不上 create_sandbox 会报错
            config = DockerSandboxConfig(tools_config={'python_executor': {}})
            sid = await manager.create_sandbox(SandboxType.DOCKER, config)
            res = await manager.execute_tool(sid, 'python_executor', {'code': 'print("Remote Hello")'})
            print(f'[HttpManager] Output: {res.output.strip()}')
            await manager.delete_sandbox(sid)
    except Exception as e:
        print(f'[HttpManager] Skipped or Failed: {e}')


async def demo_sandbox_pool():
    """
    1.5 高性能模式：Sandbox Pool (预热复用)
    """
    print('\n--- Demo: Sandbox Pool ---')
    async with LocalSandboxManager() as manager:
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'python_executor': {}}
        )
        # 初始化池，预热 1 个沙箱 (为了演示速度设为1)
        print('[Pool] Initializing pool...')
        await manager.initialize_pool(pool_size=1, sandbox_type=SandboxType.DOCKER, config=config)

        # 借用沙箱执行任务
        result = await manager.execute_tool_in_pool(
            'python_executor',
            {'code': 'print("Executed in pool")'},
            timeout=30
        )
        print(f'[Pool] Output: {result.output.strip()}')

        stats = await manager.get_stats()
        print(f'[Pool] Stats: {stats}')


# ==========================================
# 2. 高级功能
# ==========================================

async def demo_install_dependencies():
    """
    2.1 在 Sandbox 中安装额外依赖
    """
    print('\n--- Demo: Install Dependencies ---')
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={'python_executor': {}, 'file_operation': {}, 'shell_executor': {}}
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print('[Deps] Installing dependencies (this may take a moment)...')
        # 1. 写入 requirements.txt
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/requirements.txt',
            'content': 'packaging' # 使用一个较小的包演示
        })

        # 2. 执行安装命令
        try:
            # 注意：实际环境中可能需要网络权限，默认 DockerSandbox 是开启网络的
            install_res = await sandbox.execute_command('pip install -r /sandbox/requirements.txt')
            if install_res.exit_code != 0:
                print(f'[Deps] Install failed: {install_res.stderr} {install_res.stdout}')
            else:
                # 3. 验证安装
                res = await sandbox.execute_tool('python_executor', {
                    'code': 'import packaging; print(f"Packaging version: {packaging.__version__}")'
                })
                print(f'[Deps] Result: {res.output.strip()}')
        except Exception as e:
            print(f'[Deps] Error: {e}')


async def demo_host_volume():
    """
    2.2 读写宿主机文件
    """
    print('\n--- Demo: Host Volume Mounting ---')
    # 在宿主机创建一个临时目录用于测试
    host_dir = os.path.abspath('./temp_sandbox_data')
    os.makedirs(host_dir, exist_ok=True)
    try:
        with open(os.path.join(host_dir, 'host_file.txt'), 'w') as f:
            f.write('Hello from Host')

        # 配置挂载：宿主机路径 -> 容器内路径
        config = DockerSandboxConfig(
            image='python:3.11-slim',
            tools_config={'shell_executor': {}},
            volumes={host_dir: {'bind': '/sandbox/data', 'mode': 'rw'}}
        )

        async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
            # 读取宿主机文件
            res = await sandbox.execute_tool('shell_executor', {
                'command': 'cat /sandbox/data/host_file.txt'
            })
            print(f'[Volume] Read from host: {res.output.strip()}')

            # 写入文件回宿主机
            await sandbox.execute_tool('shell_executor', {
                'command': 'echo "Response from Sandbox" > /sandbox/data/sandbox_file.txt'
            })

        # 验证宿主机上的文件
        if os.path.exists(os.path.join(host_dir, 'sandbox_file.txt')):
            with open(os.path.join(host_dir, 'sandbox_file.txt'), 'r') as f:
                print(f'[Volume] Read from sandbox write: {f.read().strip()}')
        else:
            print('[Volume] File not written back to host.')

    finally:
        # 清理
        if os.path.exists(host_dir):
            shutil.rmtree(host_dir)

# ==========================================
# 3. 工具使用详解
# ==========================================

async def demo_tools_usage():
    """
    展示常用工具
    """
    print('\n--- Demo: Tools Usage ---')
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},
            'shell_executor': {},
            'file_operation': {}
        }
    )

    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sb:
        # 1. Python Executor
        py_res = await sb.execute_tool('python_executor', {'code': 'print(100 * 2)'})
        print(f'[Tool] Python: {py_res.output.strip()}')

        # 2. Shell Executor
        sh_res = await sb.execute_tool('shell_executor', {'command': 'echo "shell works"'})
        print(f'[Tool] Shell: {sh_res.output.strip()}')

        # 3. File Operation
        await sb.execute_tool('file_operation', {
            'operation': 'write', 'file_path': '/sandbox/test.txt', 'content': 'file content'
        })
        read_res = await sb.execute_tool('file_operation', {
            'operation': 'read', 'file_path': '/sandbox/test.txt'
        })
        print(f'[Tool] File Read: {read_res.output}')

# ==========================================
# 4. 手动生命周期管理
# ==========================================

async def demo_manual_lifecycle():
    """
    不使用 async with
    """
    print('\n--- Demo: Manual Lifecycle ---')
    config = DockerSandboxConfig(tools_config={'shell_executor': {}})

    # 1. 创建实例
    sandbox = SandboxFactory.create_sandbox(SandboxType.DOCKER, config)

    try:
        # 2. 显式启动
        await sandbox.start()
        print('[Manual] Sandbox started')

        # 3. 执行操作
        res = await sandbox.execute_tool('shell_executor', {'command': 'echo manual'})
        print(f'[Manual] Output: {res.output.strip()}')

    finally:
        # 4. 显式停止
        await sandbox.stop()
        print('[Manual] Cleanup done')


async def main():
    print('Starting ms-enclave basic usage demos...')

    # 典型场景
    # await demo_sandbox_factory()
    # await demo_manager_factory()
    # await demo_local_manager()
    # # await demo_http_manager() # 需要手动开启 Server，默认注释
    # await demo_sandbox_pool()

    # # 高级功能
    # await demo_install_dependencies()
    # await demo_host_volume()

    # # 工具详解
    # await demo_tools_usage()

    # 手动生命周期
    await demo_manual_lifecycle()

    print('\nAll demos finished.')

if __name__ == '__main__':
    asyncio.run(main())
