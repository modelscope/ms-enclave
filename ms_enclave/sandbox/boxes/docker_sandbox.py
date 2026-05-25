"""Docker-based sandbox implementation."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union

import docker
from docker import DockerClient
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
from docker.models.containers import Container

from ms_enclave.utils import get_logger

from ..model import CommandResult, DockerSandboxConfig, ExecutionStatus, SandboxStatus, SandboxType
from .base import Sandbox, register_sandbox

logger = get_logger()

_QUEUE_SENTINEL = object()


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
        self.client: Optional[DockerClient] = None
        self.container: Optional[Container] = None
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=config.docker_executor_workers,
            thread_name_prefix=f'docker-sb-{self.id[:8]}',
        )

    @property
    def sandbox_type(self) -> SandboxType:
        """Return sandbox type."""
        return SandboxType.DOCKER

    async def _run_blocking(self, func: Callable, *args, **kwargs):
        """Run a blocking docker SDK call on the dedicated thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: func(*args, **kwargs))

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
            raise RuntimeError(f'Failed to start Docker sandbox: {e}')

    async def stop(self) -> None:
        """Stop the Docker container without removing it unless configured.

        When remove_on_exit is False, this method stops the container but keeps
        the container reference so get_execution_context() can return it.
        """
        if not self.container:
            self.update_status(SandboxStatus.STOPPED)
            return

        try:
            self.update_status(SandboxStatus.STOPPING)
            await self.stop_container()

            # If configured to remove on exit, perform full cleanup (removes container and closes client)
            if self.config.remove_on_exit:
                await self.cleanup()

            self.update_status(SandboxStatus.STOPPED)
        except Exception as e:
            logger.error(f'Error stopping container: {e}')
            self.update_status(SandboxStatus.ERROR)
            raise

    async def cleanup(self) -> None:
        """Clean up Docker resources.

        - Always stops the container if it is running.
        - Removes the container only when remove_on_exit is True.
        - Preserves container reference and client when remove_on_exit is False.
        """
        if self.container:
            try:
                await self._run_blocking(self.container.remove, force=True)
                logger.debug(f'Container {self.container.id} removed')
            except Exception as e:
                logger.error(f'Error cleaning up container: {e}')
            finally:
                # Only drop the reference when we actually removed it
                self.container = None

        # Close Docker client only if we dropped the container reference
        if self.client:
            try:
                await self._run_blocking(self.client.close)
            except Exception as e:
                logger.warning(f'Error closing Docker client: {e}')
            finally:
                self.client = None

        # Tear down the dedicated thread pool last so the calls above can use it.
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(f'Error shutting down docker executor: {e}')

    async def stop_container(self) -> None:
        """Stop the container if it is running."""
        if not self.container:
            return
        try:
            await self._run_blocking(self.container.reload)
            if self.container.status == SandboxStatus.RUNNING:
                await self._run_blocking(self.container.stop, timeout=10)
        except NotFound:
            logger.warning('Container not found while stopping')
        except Exception as e:
            logger.error(f'Error stopping container: {e}')
            raise

    async def get_execution_context(self) -> Any:
        """Return the container for tool execution."""
        return self.container

    async def _aiter_exec_output(self, exec_id: str) -> AsyncIterator[Tuple[Optional[bytes], Optional[bytes]]]:
        """Bridge ``exec_start(stream=True)`` chunks from a worker thread to async.

        The producer thread iterates the blocking docker generator and pushes each
        (stdout, stderr) tuple onto an unbounded ``asyncio.Queue``. The async caller
        consumes the queue. When the caller stops iterating (cancel/timeout), it is
        responsible for invoking ``exec_kill`` so the producer's iterator unblocks.
        """
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _producer():
            try:
                for chunk in self.client.api.exec_start(exec_id, stream=True, demux=True):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _QUEUE_SENTINEL)

        self._executor.submit(_producer)

        while True:
            item = await queue.get()
            if item is _QUEUE_SENTINEL:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    async def _kill_exec_safe(self, exec_id: str) -> None:
        """Best-effort exec_kill so the producer iterator unblocks."""
        try:
            await self._run_blocking(self.client.api.exec_kill, exec_id, 'SIGKILL')
        except Exception as e:
            logger.debug(f'exec_kill failed (likely already finished): {e}')

    def _run_buffered(self, command: Union[str, List[str]]) -> Tuple[int, str, str]:
        """Execute command and return buffered output using high-level API.

        Returns:
            A tuple of (exit_code, stdout, stderr)
        """
        if not self.container:
            raise RuntimeError('Container is not running')

        res = self.container.exec_run(command, tty=False, stream=False, demux=True)
        out_tuple = res.output
        if isinstance(out_tuple, tuple):
            out_bytes, err_bytes = out_tuple
        else:
            # Fallback: when demux was not honored, treat all as stdout
            out_bytes, err_bytes = out_tuple, b''

        stdout = out_bytes.decode('utf-8', errors='replace') if out_bytes else ''
        stderr = err_bytes.decode('utf-8', errors='replace') if err_bytes else ''
        return res.exit_code, stdout, stderr

    async def execute_command(
        self, command: Union[str, List[str]], timeout: Optional[int] = None, stream: bool = True
    ) -> CommandResult:
        """Execute a command in the container.

        When stream=True (default), logs are printed in real-time through the logger,
        while stdout/stderr are still accumulated and returned in the result.
        When stream=False, the command is executed and buffered, returning the full output at once.

        Args:
            command: Command to run (str or list)
            timeout: Optional timeout in seconds
            stream: Whether to stream logs in real time

        Returns:
            CommandResult with status, exit_code, stdout and stderr
        """
        if not self.container or not self.client:
            raise RuntimeError('Container is not running')

        if not stream:
            try:
                exit_code, stdout, stderr = await asyncio.wait_for(
                    self._run_blocking(self._run_buffered, command), timeout=timeout
                )
                status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.ERROR
                return CommandResult(command=command, status=status, exit_code=exit_code, stdout=stdout, stderr=stderr)
            except asyncio.TimeoutError:
                return CommandResult(
                    command=command,
                    status=ExecutionStatus.TIMEOUT,
                    exit_code=-1,
                    stdout='',
                    stderr=f'Command timed out after {timeout} seconds',
                )
            except Exception as e:
                return CommandResult(
                    command=command, status=ExecutionStatus.ERROR, exit_code=-1, stdout='', stderr=str(e)
                )

        # Streaming path: keep exec_id so we can exec_kill on cancel/timeout.
        exec_meta = await self._run_blocking(
            self.client.api.exec_create, container=self.container.id, cmd=command, tty=False
        )
        exec_id = exec_meta['Id']

        stdout_parts: List[str] = []
        stderr_parts: List[str] = []

        async def _consume() -> None:
            async for out, err in self._aiter_exec_output(exec_id):
                if out:
                    text = out.decode('utf-8', errors='replace')
                    stdout_parts.append(text)
                    for line in text.splitlines():
                        logger.info(f'[📦 {self.id}] {line}')
                if err:
                    text = err.decode('utf-8', errors='replace')
                    stderr_parts.append(text)
                    for line in text.splitlines():
                        logger.error(f'[📦 {self.id}] {line}')

        try:
            await asyncio.wait_for(_consume(), timeout=timeout)
            inspect = await self._run_blocking(self.client.api.exec_inspect, exec_id)
            exit_code = inspect.get('ExitCode')
            if exit_code is None:
                exit_code = -1
            status = ExecutionStatus.SUCCESS if exit_code == 0 else ExecutionStatus.ERROR
            return CommandResult(
                command=command,
                status=status,
                exit_code=exit_code,
                stdout=''.join(stdout_parts),
                stderr=''.join(stderr_parts),
            )
        except asyncio.TimeoutError:
            await self._kill_exec_safe(exec_id)
            return CommandResult(
                command=command,
                status=ExecutionStatus.TIMEOUT,
                exit_code=-1,
                stdout=''.join(stdout_parts),
                stderr=f'Command timed out after {timeout} seconds',
            )
        except asyncio.CancelledError:
            await self._kill_exec_safe(exec_id)
            raise
        except Exception as e:
            await self._kill_exec_safe(exec_id)
            return CommandResult(
                command=command,
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                stdout=''.join(stdout_parts),
                stderr=str(e),
            )

    async def _ensure_image_exists(self) -> None:
        """Ensure Docker image exists."""
        try:
            await self._run_blocking(self.client.images.get, self.config.image)
            return
        except ImageNotFound:
            pass

        try:
            pull_kwargs: Dict[str, Any] = {}
            if self.config.platform:
                pull_kwargs['platform'] = self.config.platform
            if self.config.pull_progress:
                await self._pull_image_with_progress()
            else:
                await self._run_blocking(self.client.images.pull, self.config.image, **pull_kwargs)
        except Exception as e:
            raise RuntimeError(f'Failed to pull image {self.config.image}: {e}')

    async def _aiter_pull_events(self, repo: str, tag: str) -> AsyncIterator[Dict[str, Any]]:
        """Bridge ``client.api.pull(stream=True, decode=True)`` events to async.

        Note: docker SDK does not expose a way to abort an in-flight pull. If the
        async caller is cancelled, the worker thread will continue draining the
        HTTP response until the pull completes or the connection breaks.
        """
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _producer():
            try:
                pull_kwargs: Dict[str, Any] = {'stream': True, 'decode': True}
                if self.config.platform:
                    pull_kwargs['platform'] = self.config.platform
                for evt in self.client.api.pull(repo, tag=tag, **pull_kwargs):
                    loop.call_soon_threadsafe(queue.put_nowait, evt)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _QUEUE_SENTINEL)

        self._executor.submit(_producer)

        while True:
            item = await queue.get()
            if item is _QUEUE_SENTINEL:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    async def _pull_image_with_progress(self) -> None:
        """Stream pull progress and log periodic aggregates.

        Aggregates per-layer Downloading/Extracting bytes and emits one summary
        line every ``pull_progress_interval`` seconds. Final line shows totals.
        """
        ref = self.config.image
        if ':' in ref and '/' not in ref.rsplit(':', 1)[1]:
            repo, tag = ref.rsplit(':', 1)
        else:
            repo, tag = ref, 'latest'

        interval = float(self.config.pull_progress_interval)
        layers: Dict[str, Dict[str, Any]] = {}
        last_log = time.time()
        start = last_log
        logger.info(f'Pulling image {ref} (streaming progress every {interval:.1f}s)...')

        def _fmt_bytes(n: float) -> str:
            for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
                if n < 1024.0:
                    return f'{n:.1f}{unit}'
                n /= 1024.0
            return f'{n:.1f}PB'

        def _emit(final: bool = False) -> None:
            dl_cur = sum(l.get('dl_cur', 0) for l in layers.values())
            dl_tot = sum(l.get('dl_tot', 0) for l in layers.values())
            ex_cur = sum(l.get('ex_cur', 0) for l in layers.values())
            ex_tot = sum(l.get('ex_tot', 0) for l in layers.values())
            done = sum(1 for l in layers.values() if l.get('done'))
            elapsed = time.time() - start
            prefix = '[pull done]' if final else '[pull]'
            logger.info(
                f'{prefix} {ref} layers={done}/{len(layers)} '
                f'download={_fmt_bytes(dl_cur)}/{_fmt_bytes(dl_tot)} '
                f'extract={_fmt_bytes(ex_cur)}/{_fmt_bytes(ex_tot)} '
                f'elapsed={elapsed:.1f}s'
            )

        async for evt in self._aiter_pull_events(repo, tag):
            if 'error' in evt:
                raise RuntimeError(evt['error'])
            lid = evt.get('id')
            status = evt.get('status', '')
            if not lid or ':' in lid:  # skip overall status / digest lines
                continue
            layer = layers.setdefault(lid, {})
            pd = evt.get('progressDetail') or {}
            cur = pd.get('current')
            tot = pd.get('total')
            if status.startswith('Downloading'):
                if cur is not None:
                    layer['dl_cur'] = cur
                if tot:
                    layer['dl_tot'] = tot
            elif status.startswith('Extracting'):
                if cur is not None:
                    layer['ex_cur'] = cur
                if tot:
                    layer['ex_tot'] = tot
            elif status in ('Download complete', 'Pull complete', 'Already exists'):
                if 'dl_tot' in layer:
                    layer['dl_cur'] = layer['dl_tot']
                if 'ex_tot' in layer:
                    layer['ex_cur'] = layer['ex_tot']
                if status in ('Pull complete', 'Already exists'):
                    layer['done'] = True

            now = time.time()
            if interval > 0 and now - last_log >= interval:
                _emit()
                last_log = now

        for layer in layers.values():
            layer['done'] = True
        _emit(final=True)

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

            # Extra /etc/hosts entries (e.g. host.docker.internal -> host-gateway
            # on Linux so containerised agents can reach services on the host).
            if self.config.extra_hosts:
                container_config['extra_hosts'] = dict(self.config.extra_hosts)

            # Privileged mode
            container_config['privileged'] = self.config.privileged

            # Platform (e.g. linux/amd64 for amd64 images on Apple Silicon)
            if self.config.platform:
                container_config['platform'] = self.config.platform

            # Create container (run sync docker SDK off the event loop)
            self.container = await self._run_blocking(self.client.containers.create, **container_config)
            self.metadata['container_id'] = self.container.id

        except Exception as e:
            raise RuntimeError(f'Failed to create container: {e}')

    async def _start_container(self) -> None:
        """Start Docker container."""
        try:
            await self._run_blocking(self.container.start)

            # Wait for container to be ready
            timeout = 30
            start_time = time.time()

            while time.time() - start_time < timeout:
                await self._run_blocking(self.container.reload)
                if self.container.status == 'running':
                    break
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError('Container failed to start within timeout')

        except Exception as e:
            raise RuntimeError(f'Failed to start container: {e}')
