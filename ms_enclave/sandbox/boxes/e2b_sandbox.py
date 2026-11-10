"""Stateful remote sandbox backed by the optional E2B SDK."""

import asyncio
import posixpath
import shlex
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from ms_enclave.sandbox.boxes.base import Sandbox, register_sandbox
from ms_enclave.sandbox.boxes.e2b_connection import E2BConnection, require_e2b, retry_dispatch
from ms_enclave.sandbox.boxes.e2b_template import E2BTemplateResolver
from ms_enclave.sandbox.model import (
    CommandResult,
    E2BSandboxConfig,
    E2BSandboxManagerConfig,
    ExecutionStatus,
    SandboxStatus,
    SandboxType,
)
from ms_enclave.utils import get_logger

logger = get_logger()


@register_sandbox(SandboxType.E2B)
class E2BSandbox(Sandbox):
    """Execute commands and transfer archives without a local Docker daemon."""

    def __init__(
        self,
        config: E2BSandboxConfig,
        sandbox_id: Optional[str] = None,
        *,
        connection: Optional[E2BConnection] = None,
        templates: Optional[E2BTemplateResolver] = None,
        run_id: Optional[str] = None,
    ) -> None:
        require_e2b()
        super().__init__(config, sandbox_id)
        self.config: E2BSandboxConfig = config
        self._conn = connection
        self._templates = templates
        self._run_id = run_id or uuid.uuid4().hex[:12]
        self._sbx: Any = None
        self._started = 0.0
        self._lifecycle_lock = asyncio.Lock()

    @property
    def sandbox_type(self) -> SandboxType:
        """Return the registered E2B type."""
        return SandboxType.E2B

    async def start(self) -> None:
        """Create the remote sandbox with a fixed lifetime and run metadata."""
        async with self._lifecycle_lock:
            try:
                await self._start()
            except BaseException:
                try:
                    await self._stop()
                except Exception as exc:
                    logger.warning(self._conn.redact(f'E2B startup cleanup failed: {exc}'))
                self.update_status(SandboxStatus.ERROR)
                raise

    async def _start(self) -> None:
        from e2b import AsyncSandbox

        if self._sbx is not None:
            if self.status in (SandboxStatus.RUNNING, SandboxStatus.IDLE, SandboxStatus.BUSY):
                return
            raise RuntimeError('Delete the existing E2B sandbox before starting it again')
        if self._conn is None:
            cfg = E2BSandboxManagerConfig()
            self._conn = E2BConnection.from_config(cfg)
        if self._templates is None:
            self._templates = E2BTemplateResolver(self._conn, {}, 4)
        self.update_status(SandboxStatus.INITIALIZING)
        self._started = time.monotonic()
        template = self.config.template or self.config.image
        try:
            template = await self._templates.resolve(self.config, run_id=self._run_id)
            creation = asyncio.create_task(
                retry_dispatch(
                    'create sandbox',
                    lambda: AsyncSandbox.create(
                        template=template,
                        timeout=self.config.sandbox_timeout,
                        metadata={'created_by': 'ms-enclave', 'run_id': self._run_id},
                        allow_internet_access=self.config.allow_internet_access,
                        **self._conn.api_params(retries=0),
                    ),
                    run_id=self._run_id,
                    redactor=self._conn.redact,
                )
            )
            try:
                self._sbx = await asyncio.shield(creation)
            except asyncio.CancelledError:
                # Keep ownership of a late create response so cancellation can clean it up.
                try:
                    self._sbx = await creation
                except Exception as exc:
                    logger.warning(self._conn.redact(f'E2B create interrupted run_id={self._run_id}: {exc}'))
                raise
        except Exception as exc:
            self.update_status(SandboxStatus.ERROR)
            message = (
                f'Failed to create E2B sandbox (template={template}, run_id={self._run_id}, '
                f'sandbox_timeout={self.config.sandbox_timeout}): {exc}'
            )
            if 'cannot be greater than' in str(exc):
                message += (
                    '; sandbox_timeout may exceed the plan limit (e2b official Hobby: 3600s); '
                    'lower E2BSandboxConfig.sandbox_timeout or upgrade the plan.'
                )
            raise RuntimeError(self._conn.redact(message)) from None
        self.metadata.update(remote_id=self._sbx.sandbox_id, template=template, run_id=self._run_id)
        await self.initialize_tools()
        self.update_status(SandboxStatus.RUNNING)
        logger.info(
            f'E2B sandbox {self.id} remote={self._sbx.sandbox_id} template={template} '
            f'run_id={self._run_id} elapsed={time.monotonic() - self._started:.1f}s'
        )

    async def stop(self) -> None:
        """Keep the remote reference until deletion is confirmed, allowing retries."""
        async with self._lifecycle_lock:
            await self._stop()

    async def _stop(self) -> None:
        remote = self._sbx
        if remote is not None:
            try:
                await remote.kill(**self._conn.api_params(retries=0))
            except Exception as exc:
                self.update_status(SandboxStatus.ERROR)
                raise RuntimeError(
                    self._conn.redact(f'E2B sandbox {self.id} remote={remote.sandbox_id}: kill failed: {exc}')
                ) from None
            self._sbx = None
            logger.info(
                f'E2B sandbox {self.id} stopped run_id={self._run_id} lifetime={time.monotonic() - self._started:.1f}s'
            )
        self.update_status(SandboxStatus.STOPPED)

    async def cleanup(self) -> None:
        """Destroy the sandbox."""
        await self.stop()

    async def get_execution_context(self) -> Any:
        """Return the underlying SDK sandbox."""
        return self._sbx

    def _result(
        self,
        command: Union[str, List[str]],
        status: ExecutionStatus,
        code: int,
        stdout: str,
        stderr: str,
        started: float,
    ) -> CommandResult:
        return CommandResult(
            command=command,
            status=status,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            execution_time=time.monotonic() - started,
        )

    async def execute_command(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        stream: bool = True,
        *,
        user: Optional[str] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Run once, preserve command output and kill the process on local timeout."""
        from e2b import CommandExitException

        if self._sbx is None:
            raise RuntimeError('E2B sandbox is not running')
        if self.status == SandboxStatus.ERROR:
            raise RuntimeError('E2B sandbox is in an error state; delete it before reuse')
        cmd = command if isinstance(command, str) else shlex.join(command)
        started = time.monotonic()
        handle = None
        try:
            async with asyncio.timeout(timeout if timeout and timeout > 0 else None):
                handle = await self._sbx.commands.run(
                    cmd,
                    background=True,
                    user=user if user is not None else self.config.user,
                    cwd=cwd if cwd is not None else self.config.working_dir,
                    envs={**self.config.env_vars, **(env or {})} or None,
                    timeout=0,
                )
                result = await handle.wait()
            return self._result(command, ExecutionStatus.SUCCESS, 0, result.stdout, result.stderr, started)
        except CommandExitException as exc:
            return self._result(command, ExecutionStatus.ERROR, exc.exit_code, exc.stdout, exc.stderr, started)
        except asyncio.TimeoutError:
            await self._kill_command(handle)
            stderr = (handle.stderr if handle else '') or f'Command timed out after {timeout} seconds'
            return self._result(command, ExecutionStatus.TIMEOUT, -1, handle.stdout if handle else '', stderr, started)
        except asyncio.CancelledError:
            await self._kill_command(handle)
            raise
        except Exception as exc:
            # Dispatch/read failures can leave a process running with no completion witness.
            await self._kill_command(handle)
            return self._result(command, ExecutionStatus.ERROR, -1, '', self._conn.redact(str(exc)), started)

    async def _kill_command(self, handle: Any) -> None:
        if handle is None:
            self.update_status(SandboxStatus.ERROR)
            return
        try:
            await handle.kill()
        except Exception as exc:
            self.update_status(SandboxStatus.ERROR)
            logger.warning(self._conn.redact(f'E2B sandbox {self.id}: process kill failed: {exc}'))

    async def put_archive(self, target_dir: str, data: bytes) -> bool:
        """Upload a tar archive, extract as the configured user, and remove it."""
        if not posixpath.isabs(target_dir):
            raise ValueError(f'target_dir must be an absolute path: {target_dir}')
        if self._sbx is None:
            raise RuntimeError('E2B sandbox is not running')
        tmp = f'/tmp/ms-enclave-upload-{uuid.uuid4().hex}.tar'
        try:
            await self._sbx.files.write(tmp, data, user=self.config.user)
        except Exception as exc:
            logger.error(self._conn.redact(f'E2B sandbox {self.id}: upload to {target_dir} failed: {exc}'))
            return False
        q = shlex.quote
        result = await self.execute_command(
            f'mkdir -p {q(target_dir)} && tar -xf {q(tmp)} -C {q(target_dir)}; rc=$?; rm -f {q(tmp)}; exit $rc',
            timeout=300,
        )
        if result.exit_code != 0:
            logger.error(
                self._conn.redact(f'E2B sandbox {self.id}: extracting into {target_dir} failed: {result.stderr}')
            )
            return False
        return True
