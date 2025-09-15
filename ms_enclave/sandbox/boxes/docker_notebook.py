# flake8: noqa E501
import asyncio
import json
import time
import uuid
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Optional

from docker import DockerClient

from ..model import CommandResult, DockerSandboxConfig, ExecutionStatus, SandboxType
from .docker_sandbox import DockerSandbox
from .base import register_sandbox

from ms_enclave.utils import get_logger
logger = get_logger()


@register_sandbox(SandboxType.DOCKER_NOTEBOOK)
class JupyterDockerSandbox(DockerSandbox):
    """
    Docker sandbox that executes Python code using Jupyter Kernel Gateway.
    """

    def __init__(
        self,
        config: DockerSandboxConfig,
        sandbox_id: Optional[str] = None,
        host: str = '127.0.0.1',
        port: int = 8888,
    ):
        """
        Initialize the Docker-based Jupyter Kernel Gateway executor.

        Args:
            config: Docker sandbox configuration
            sandbox_id: Optional sandbox ID
            host: Host to bind to.
            port: Port to bind to.
        """
        # Set up Jupyter-specific image if not provided
        if not config.image:
            config.image = 'jupyter-kernel-gateway'

        # Ensure port mapping for Jupyter
        if not config.ports:
            config.ports = {}
        config.ports['8888/tcp'] = (host, port)

        super().__init__(config, sandbox_id)

        self.host = host
        self.port = port
        self.kernel_id = None
        self.ws = None
        self.base_url = None
        self.client: DockerClient = None  # type: ignore

    async def start(self) -> None:
        """Start the Docker container with Jupyter Kernel Gateway."""
        # First start the base container
        await super().start()

        # Setup Jupyter kernel gateway
        await self._setup_jupyter()

    async def _setup_jupyter(self) -> None:
        """Setup Jupyter Kernel Gateway in the container."""
        try:
            # Build Jupyter image if needed
            await self._build_jupyter_image()

            # Start Jupyter Kernel Gateway
            await self._start_jupyter_service()

            # Create kernel and establish websocket connection
            await self._create_kernel()

        except Exception as e:
            logger.error(f'Failed to setup Jupyter: {e}')
            raise

    async def _build_jupyter_image(self) -> None:
        """Build or ensure Jupyter image exists."""
        try:
            # Check if image exists
            self.client.images.get(self.config.image)
            logger.info(f'Using existing Docker image: {self.config.image}')
        except Exception:
            logger.info(f'Building Docker image {self.config.image}...')

            # Create Dockerfile
            dockerfile_content = dedent(
                """\
                FROM python:3.12-slim

                RUN pip install jupyter_kernel_gateway jupyter_client requests websocket-client

                EXPOSE 8888
                CMD ["jupyter", "kernelgateway", "--KernelGatewayApp.ip='0.0.0.0'", "--KernelGatewayApp.port=8888", "--KernelGatewayApp.allow_origin='*'"]
                """
            )

            dockerfile_path = Path('/tmp/jupyter_dockerfile')
            dockerfile_path.write_text(dockerfile_content)

            # Build image
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.client.images.
                build(path=str(dockerfile_path.parent), dockerfile='jupyter_dockerfile', tag=self.config.image)
            )

    async def _start_jupyter_service(self) -> None:
        """Start Jupyter Kernel Gateway service in container."""
        # Start Jupyter service
        start_cmd = 'jupyter kernelgateway --KernelGatewayApp.ip="0.0.0.0" --KernelGatewayApp.port=8888 --KernelGatewayApp.allow_origin="*" &'  # noqa: E501
        result = await self.execute_command(start_cmd)

        if not result or result.exit_code != 0:
            raise RuntimeError(
                f'Failed to start Jupyter Kernel Gateway: {result.stderr if result else "Unknown error"}'
            )

        # Wait for service to be ready
        self.base_url = f'http://{self.host}:{self.port}'

        # Wait for Jupyter to be ready
        for _ in range(30):  # 30 second timeout
            try:
                import requests
                response = requests.get(f'{self.base_url}/api/kernels', timeout=1)
                if response.status_code == 200:
                    logger.info('Jupyter Kernel Gateway is ready')
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Jupyter Kernel Gateway failed to start')

    async def _create_kernel(self) -> None:
        """Create a new kernel and establish websocket connection."""
        import requests

        # Create new kernel via HTTP
        response = requests.post(f'{self.base_url}/api/kernels')
        if response.status_code != 201:
            raise RuntimeError(f'Failed to create kernel: {response.text}')

        self.kernel_id = response.json()['id']

        # Establish websocket connection
        try:
            from websocket import create_connection
            ws_url = f'ws://{self.host}:{self.port}/api/kernels/{self.kernel_id}/channels'
            self.ws = create_connection(ws_url)
            logger.info(f'Kernel {self.kernel_id} created and connected')
        except ImportError:
            raise RuntimeError('websocket-client package is required. Install with: pip install websocket-client')

    async def execute_python_code(self, code: str, timeout: Optional[int] = None) -> CommandResult:
        """Execute Python code in the Jupyter kernel."""
        if not self.ws or not self.kernel_id:
            raise RuntimeError('Jupyter kernel is not ready')

        try:
            # Send execute request
            msg_id = self._send_execute_request(code)

            # Collect output and results
            outputs = []
            result = None
            error_occurred = False

            actual_timeout = timeout or 30
            start_time = time.time()

            while time.time() - start_time < actual_timeout:
                try:
                    msg = json.loads(self.ws.recv())
                    parent_msg_id = msg.get('parent_header', {}).get('msg_id')

                    # Skip unrelated messages
                    if parent_msg_id != msg_id:
                        continue

                    msg_type = msg.get('msg_type', '')
                    msg_content = msg.get('content', {})

                    if msg_type == 'stream':
                        outputs.append(msg_content['text'])
                    elif msg_type == 'execute_result':
                        result = msg_content['data'].get('text/plain', '')
                    elif msg_type == 'error':
                        error_occurred = True
                        error_msg = '\n'.join(msg_content.get('traceback', []))
                        outputs.append(error_msg)
                    elif msg_type == 'status' and msg_content['execution_state'] == 'idle':
                        break

                except Exception as e:
                    logger.error(f'Error receiving message: {e}')
                    break

            output_text = ''.join(outputs)
            if result:
                output_text += f'\nResult: {result}'

            return CommandResult(
                command=code,
                status=ExecutionStatus.ERROR if error_occurred else ExecutionStatus.SUCCESS,
                exit_code=1 if error_occurred else 0,
                stdout=output_text,
                stderr='' if not error_occurred else output_text
            )

        except Exception as e:
            return CommandResult(
                command=code, status=ExecutionStatus.ERROR, exit_code=1, stdout='', stderr=f'Execution failed: {e}'
            )

    def _send_execute_request(self, code: str) -> str:
        """Send code execution request to kernel."""
        # Generate a unique message ID
        msg_id = str(uuid.uuid4())

        # Create execute request
        execute_request = {
            'header': {
                'msg_id': msg_id,
                'username': 'anonymous',
                'session': str(uuid.uuid4()),
                'msg_type': 'execute_request',
                'version': '5.0',
            },
            'parent_header': {},
            'metadata': {},
            'content': {
                'code': code,
                'silent': False,
                'store_history': True,
                'user_expressions': {},
                'allow_stdin': False,
            },
        }

        self.ws.send(json.dumps(execute_request))
        return msg_id

    async def cleanup(self) -> None:
        """Clean up Jupyter resources and Docker container."""
        try:
            # Close websocket connection
            if self.ws:
                try:
                    self.ws.close()
                except Exception:
                    pass
                self.ws = None

            # Delete kernel
            if self.kernel_id and self.base_url:
                try:
                    import requests
                    requests.delete(f'{self.base_url}/api/kernels/{self.kernel_id}')
                except Exception:
                    pass
                self.kernel_id = None

        except Exception as e:
            logger.error(f'Error during Jupyter cleanup: {e}')

        # Call parent cleanup
        await super().cleanup()
