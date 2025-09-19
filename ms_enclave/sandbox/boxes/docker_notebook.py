# flake8: noqa E501
import asyncio
import json
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
class DockerNotebookSandbox(DockerSandbox):
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
        self.config.ports['8888/tcp'] = (self.host, self.port)
        self.config.network_enabled = True  # Ensure network is enabled for Jupyter

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
            logger.error(f'Failed to start Jupyter Docker sandbox: {e}')
            raise RuntimeError(f'Failed to start Jupyter Docker sandbox: {e}')

    async def _setup_jupyter(self) -> None:
        """Setup Jupyter Kernel Gateway services in the container."""
        try:
            # Wait for Jupyter Kernel Gateway to be ready
            await self._wait_for_jupyter_ready()

            # Create kernel and establish websocket connection
            await self._create_kernel()

        except Exception as e:
            logger.error(f'Failed to setup Jupyter: {e}')
            raise

    async def _wait_for_jupyter_ready(self) -> None:
        """Wait for Jupyter Kernel Gateway to be ready."""
        import requests

        self.base_url = f'http://{self.host}:{self.port}'
        max_retries = 10  # Wait up to 30 seconds
        retry_interval = 3  # Check every 3 second

        for attempt in range(max_retries):
            try:
                # Try to get the API status
                response = requests.get(f'{self.base_url}/api', timeout=5)
                if response.status_code == 200:
                    logger.info(f'Jupyter Kernel Gateway is ready at {self.base_url}')
                    return
            except requests.exceptions.RequestException:
                # Connection failed, Jupyter not ready yet
                pass

            if attempt < max_retries - 1:
                logger.info(f'Waiting for Jupyter Kernel Gateway to be ready... (attempt {attempt + 1}/{max_retries})')
                await asyncio.sleep(retry_interval)

        raise RuntimeError(f'Jupyter Kernel Gateway failed to become ready within {max_retries} seconds')

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

                RUN pip install jupyter_kernel_gateway jupyter_client ipykernel

                # Install and register the Python kernel
                RUN python -m ipykernel install --sys-prefix --name python3 --display-name "Python 3"

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

    async def _create_kernel(self) -> None:
        """Create a new kernel and establish websocket connection."""
        import requests

        # Create new kernel via HTTP
        response = requests.post(f'{self.base_url}/api/kernels')
        if response.status_code != 201:
            error_details = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'url': response.url,
                'body': response.text,
                'request_method': response.request.method,
                'request_headers': dict(response.request.headers),
                'request_body': response.request.body,
            }
            raise RuntimeError(f'Failed to create kernel: {json.dumps(error_details, indent=2)}')

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
