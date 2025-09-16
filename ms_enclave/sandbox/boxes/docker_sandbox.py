"""Docker-based sandbox implementation."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Union

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound

from ms_enclave.utils import get_logger

from ..model import CommandResult, DockerSandboxConfig, ExecutionStatus, SandboxStatus, SandboxType
from .base import Sandbox, register_sandbox

logger = get_logger()


@register_sandbox(SandboxType.DOCKER)
class DockerSandbox(Sandbox):
    """Docker-based sandbox implementation."""

    def __init__(self, config: DockerSandboxConfig, sandbox_id: Optional[str] = None):
        """Initialize Docker sandbox.

        Args:
            config: Docker sandbox configuration
            sandbox_id: Optional sandbox ID
        """
        super().__init__(config, sandbox_id)
        self.config: DockerSandboxConfig = config
        self.client: Optional[docker.DockerClient] = None
        self.container: Optional[docker.models.containers.Container] = None

    @property
    def sandbox_type(self) -> SandboxType:
        """Return sandbox type."""
        return SandboxType.DOCKER

    async def start(self) -> None:
        """Start the Docker container."""
        try:
            self.update_status(SandboxStatus.INITIALIZING)

            # Initialize Docker client
            self.client = docker.from_env()

            # Ensure image exists
            await self._ensure_image_exists()

            # Create and start container
            await self._create_container()
            await self._start_container()

            # Initialize tools
            await self.initialize_tools()

            self.update_status(SandboxStatus.RUNNING)

        except Exception as e:
            self.update_status(SandboxStatus.ERROR)
            self.metadata['error'] = str(e)
            logger.error(f'Failed to start Docker sandbox: {e}')

    async def stop(self) -> None:
        """Stop the Docker container."""
        try:
            if self.container:
                self.update_status(SandboxStatus.STOPPING)
                self.container.stop(timeout=10)
                self.update_status(SandboxStatus.STOPPED)
        except Exception as e:
            logger.error(f'Error stopping container: {e}')
            self.update_status(SandboxStatus.ERROR)

    async def cleanup(self) -> None:
        """Clean up Docker resources."""
        try:

            if self.container:
                try:
                    # Remove container if configured to do so
                    if self.config.remove_on_exit:
                        self.container.remove(force=True)
                    else:
                        self.container.stop(timeout=5)
                except Exception as e:
                    logger.error(f'Error cleaning up container: {e}')
                finally:
                    self.container = None

            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                finally:
                    self.client = None

        except Exception as e:
            logger.error(f'Error during cleanup: {e}')

    async def get_execution_context(self) -> Any:
        """Return the container for tool execution."""
        return self.container

    async def execute_command(self, command: Union[str, List[str]], timeout: Optional[int] = None) -> CommandResult:
        """Execute a command in the container."""
        if not self.container:
            raise RuntimeError('Container is not running')

        try:
            # Determine actual timeout
            actual_timeout = timeout or 30

            # Execute command asynchronously
            exec_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.container.exec_run(command, tty=True, stream=False, demux=True)
                ),
                timeout=actual_timeout
            )

            stdout = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ''
            stderr = exec_result.output[1].decode('utf-8') if exec_result.output[1] else ''

            return CommandResult(
                command=command,
                status=ExecutionStatus.SUCCESS if exec_result.exit_code == 0 else ExecutionStatus.ERROR,
                exit_code=exec_result.exit_code,
                stdout=stdout,
                stderr=stderr
            )
        except asyncio.TimeoutError:
            return CommandResult(
                command=command,
                status=ExecutionStatus.TIMEOUT,
                exit_code=-1,
                stdout='',
                stderr=f'Command timed out after {actual_timeout} seconds'
            )
        except Exception as e:
            return CommandResult(command=command, status=ExecutionStatus.ERROR, exit_code=-1, stdout='', stderr=str(e))

    async def _ensure_image_exists(self) -> None:
        """Ensure Docker image exists."""
        try:
            self.client.images.get(self.config.image)
        except ImageNotFound:
            # Try to pull the image
            try:
                self.client.images.pull(self.config.image)
            except Exception as e:
                raise RuntimeError(f'Failed to pull image {self.config.image}: {e}')

    async def _create_container(self) -> None:
        """Create Docker container."""
        try:
            # Prepare container configuration
            container_config = {
                'image': self.config.image,
                'name': f'sandbox-{self.id}',
                'working_dir': self.config.working_dir,
                'environment': self.config.env_vars,
                'detach': True,
                'tty': True,
                'stdin_open': True,
            }

            # Add command if specified
            if self.config.command:
                container_config['command'] = self.config.command

            # Add resource limits
            if self.config.memory_limit:
                container_config['mem_limit'] = self.config.memory_limit

            if self.config.cpu_limit:
                container_config['cpu_quota'] = int(self.config.cpu_limit * 100000)
                container_config['cpu_period'] = 100000

            # Add volumes
            if self.config.volumes:
                container_config['volumes'] = self.config.volumes

            # Add ports
            if self.config.ports:
                container_config['ports'] = self.config.ports

            # Network configuration
            if not self.config.network_enabled:
                container_config['network_mode'] = 'none'
            elif self.config.network:
                container_config['network'] = self.config.network

            # Privileged mode
            container_config['privileged'] = self.config.privileged

            # Create container
            self.container = self.client.containers.create(**container_config)
            self.metadata['container_id'] = self.container.id

        except Exception as e:
            raise RuntimeError(f'Failed to create container: {e}')

    async def _start_container(self) -> None:
        """Start Docker container."""
        try:
            self.container.start()

            # Wait for container to be ready
            timeout = 30
            start_time = time.time()

            while time.time() - start_time < timeout:
                self.container.reload()
                if self.container.status == 'running':
                    break
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError('Container failed to start within timeout')

        except Exception as e:
            raise RuntimeError(f'Failed to start container: {e}')
