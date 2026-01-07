import asyncio

from ms_enclave.sandbox.boxes import SandboxFactory
from ms_enclave.sandbox.model import DockerSandboxConfig, SandboxType


async def main():
    # 1. 配置沙箱
    # 指定镜像和需要启用的工具（如 python_executor, file_operation）
    config = DockerSandboxConfig(
        image='python:3.11-slim',
        tools_config={
            'python_executor': {},  # 启用代码执行工具
            'file_operation': {},   # 启用文件操作工具
        }
    )

    print('正在启动沙箱...')
    # 2. 创建并启动沙箱
    # 使用 async with 自动管理生命周期（结束时自动销毁容器）
    async with SandboxFactory.create_sandbox(SandboxType.DOCKER, config) as sandbox:
        print(f'沙箱已就绪 ID: {sandbox.id}')

        # 3. 写入文件
        # 调用 file_operation 工具
        print('正在写入文件...')
        await sandbox.execute_tool('file_operation', {
            'operation': 'write',
            'file_path': '/sandbox/hello.txt',
            'content': 'Hello from ms-enclave!'
        })

        # 4. 执行 Python 代码
        # 调用 python_executor 工具读取刚才写入的文件
        print('正在执行代码...')
        result = await sandbox.execute_tool('python_executor', {
            'code': """
print('正在读取文件...')
with open('/sandbox/hello.txt', 'r') as f:
    content = f.read()
print(f'文件内容: {content}')
"""
        })

        # 5. 查看输出
        print('执行结果:', result.output)

if __name__ == '__main__':
    asyncio.run(main())
