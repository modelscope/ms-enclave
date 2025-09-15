# flake8: noqa E501
import asyncio
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import Optional

from docker import DockerClient

from ms_enclave.utils import get_logger

from ..model import DockerNotebookConfig, SandboxStatus, SandboxType
from .base import register_sandbox
from .docker_sandbox import DockerSandbox

logger = get_logger()


@register_sandbox(SandboxType.DOCKER_NOTEBOOK)
class JupyterDockerSandbox(DockerSandbox):
    """
    Docker sandbox that executes Python code using Jupyter Kernel Gateway.
    """

    def __init__(
        self,
        config: DockerNotebookConfig,
        sandbox_id: Optional[str] = None,
    ):
        """
        Initialize the Docker-based Jupyter Kernel Gateway executor.

        Args:
            config: Docker sandbox configuration
            sandbox_id: Optional sandbox ID
            host: Host to bind to.
            port: Port to bind to.
        """
        super().__init__(config, sandbox_id)

        self.config: DockerNotebookConfig = config
        self.host = self.config.host
        self.port = self.config.port
        self.kernel_id = None
        self.ws = None
        self.base_url = None
        self.client: Optional[DockerClient] = None
        self.config.ports['8888/tcp'] = (self.host, self.port)

    @property
    def sandbox_type(self) -> SandboxType:
        """Return sandbox type."""
        return SandboxType.DOCKER_NOTEBOOK

    async def start(self) -> None:
        """Start the Docker container with Jupyter Kernel Gateway."""
        try:
            self.update_status(SandboxStatus.INITIALIZING)

            # Initialize Docker client first
            import docker
            self.client = docker.from_env()

            # Build Jupyter image if needed before creating container
            await self._build_jupyter_image()

            # Now start the base container with the Jupyter image
            await super().start()

            # Setup Jupyter kernel gateway services
            await self._setup_jupyter()

            self.update_status(SandboxStatus.RUNNING)

        except Exception as e:
            self.update_status(SandboxStatus.ERROR)
            self.metadata['error'] = str(e)
            raise RuntimeError(f'Failed to start Jupyter Docker sandbox: {e}')

    async def _setup_jupyter(self) -> None:
        """Setup Jupyter Kernel Gateway services in the container."""
        try:
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
                CMD ["jupyter", "kernelgateway", "--KernelGatewayApp.ip=0.0.0.0", "--KernelGatewayApp.port=8888", "--KernelGatewayApp.allow_origin=*"]
                """
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                dockerfile_path = Path(tmpdir) / 'Dockerfile'
                dockerfile_path.write_text(dockerfile_content)

                # Build image with output
                def build_image():
                    build_logs = self.client.images.build(
                        path=tmpdir, dockerfile='Dockerfile', tag=self.config.image, rm=True
                    )
                    # Process and log build output
                    for log in build_logs[1]:  # build_logs[1] contains the build log generator
                        if 'stream' in log:
                            logger.info(f"Docker build: {log['stream'].strip()}")
                        elif 'error' in log:
                            logger.error(f"Docker build error: {log['error']}")
                    return build_logs[0]  # Return the built image

                await asyncio.get_event_loop().run_in_executor(None, build_image)

    async def _start_jupyter_service(self) -> None:
        """Start Jupyter Kernel Gateway service in container."""
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
