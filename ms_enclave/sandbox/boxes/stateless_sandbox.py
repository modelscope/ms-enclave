"""Reusable base class for stateless remote sandboxes (no long-lived container).

Stateless remote sandboxes (e.g. VolcEngine/SandboxFusion, E2B, Daytona, ...)
expose execution through an HTTP service managed externally. A "sandbox" here
is just a logical handle into that remote service, so the base class only owns
the pieces that are truly common to any such backend:

- Lifecycle that is effectively no-op (``start`` / ``stop`` / ``cleanup``):
  no container to spawn; the only resource is a shared ``aiohttp.ClientSession``.
- Session management: the manager typically injects a shared session; when none
  is provided the sandbox creates (and owns) a private one.
- Generic HTTP helpers (``_post_json`` / ``_request_json``) that subclasses can
  use to talk to whatever endpoints their vendor exposes.
- A default ``_health_check`` hook that subclasses may override for a startup
  probe.
- ``execute_command`` raises :class:`NotImplementedError`, since stateless
  remotes typically don't expose free-form shell access.

Vendor/protocol-specific concerns (e.g. SandboxFusion's ``/run_code`` API,
language identifier rewriting, response → :class:`ToolResult` mapping) are
deliberately **NOT** implemented here; they belong to concrete subclasses such
as :class:`~ms_enclave.sandbox.boxes.volcengine.VolcengineSandbox`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import aiohttp

from ms_enclave.utils import get_logger

from ..model import CommandResult, SandboxConfig, SandboxStatus
from .base import Sandbox

logger = get_logger()


class StatelessSandbox(Sandbox):
    """Reusable base class for stateless HTTP-backed sandboxes.

    Subclasses are responsible for implementing any vendor-specific execution
    protocol on top of the HTTP helpers provided here, and for advertising
    their concrete :class:`SandboxType` via the ``sandbox_type`` property.
    """

    def __init__(
        self,
        config: SandboxConfig,
        *,
        base_url: str,
        request_timeout: float = 30.0,
        verify_ssl: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
        sandbox_id: Optional[str] = None,
    ) -> None:
        super().__init__(config, sandbox_id)
        if not base_url:
            raise ValueError('StatelessSandbox requires a non-empty base_url')
        self._base_url: str = base_url.rstrip('/')
        self._request_timeout: float = float(request_timeout)
        self._verify_ssl: bool = bool(verify_ssl)
        self._api_key: Optional[str] = api_key
        self._extra_headers: Dict[str, str] = dict(extra_headers) if extra_headers else {}

        # If a session is injected by the manager, we don't own it and must not close it.
        self._session: Optional[aiohttp.ClientSession] = session
        self._owns_session: bool = session is None

    # --------------------------------------------------------------------- #
    # Accessors                                                             #
    # --------------------------------------------------------------------- #
    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        return self._session

    # --------------------------------------------------------------------- #
    # Lifecycle                                                             #
    # --------------------------------------------------------------------- #
    async def start(self) -> None:
        """Start the stateless sandbox (no container to spawn)."""
        try:
            self.update_status(SandboxStatus.INITIALIZING)

            # Create a private session if none was injected.
            if self._session is None:
                timeout = aiohttp.ClientTimeout(total=self._request_timeout)
                headers = self._build_default_headers()
                self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
                self._owns_session = True

            # Optional subclass-provided health check; failures should not block startup.
            try:
                await self._health_check()
            except Exception as e:
                logger.warning(f'Stateless sandbox health check failed (non-fatal): {e}')

            await self.initialize_tools()
            self.update_status(SandboxStatus.RUNNING)
        except Exception as e:
            self.update_status(SandboxStatus.ERROR)
            self.metadata['error'] = str(e)
            logger.error(f'Failed to start stateless sandbox: {e}')
            raise

    async def stop(self) -> None:
        """Stop the stateless sandbox; close private session if owned."""
        try:
            self.update_status(SandboxStatus.STOPPING)
            await self._close_private_session()
            self.update_status(SandboxStatus.STOPPED)
        except Exception as e:
            logger.error(f'Error stopping stateless sandbox: {e}')
            self.update_status(SandboxStatus.ERROR)
            raise

    async def cleanup(self) -> None:
        """Clean up resources; identical to stop for stateless sandboxes."""
        await self._close_private_session()

    async def get_execution_context(self) -> Any:
        """Tools receive the sandbox itself as the execution context."""
        return self

    async def execute_command(
        self, command: Union[str, List[str]], timeout: Optional[int] = None, stream: bool = True
    ) -> CommandResult:
        raise NotImplementedError('stateless sandbox does not support execute_command')

    # --------------------------------------------------------------------- #
    # Subclass hooks                                                        #
    # --------------------------------------------------------------------- #
    async def _health_check(self) -> None:
        """Optional startup probe. Default: no-op. Subclasses may override."""
        return None

    # --------------------------------------------------------------------- #
    # HTTP helpers (generic, protocol-agnostic)                             #
    # --------------------------------------------------------------------- #
    def _build_default_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {'Content-Type': 'application/json'}
        if self._api_key:
            headers['Authorization'] = self._api_key
        if self._extra_headers:
            headers.update(self._extra_headers)
        return headers

    def _build_url(self, path: str) -> str:
        """Join ``base_url`` and ``path`` (absolute URL in ``path`` is honored)."""
        if path.startswith('http://') or path.startswith('https://'):
            return path
        suffix = path if path.startswith('/') else f'/{path}'
        return f'{self._base_url}{suffix}'

    async def _close_private_session(self) -> None:
        if self._session is not None and self._owns_session:
            try:
                await self._session.close()
            except Exception as e:  # noqa: BLE001
                logger.warning(f'Error closing stateless sandbox session: {e}')
            finally:
                self._session = None
                self._owns_session = False

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Issue an HTTP request and return the parsed JSON body.

        This is intentionally low-level: subclasses use it to implement their
        own vendor-specific APIs without reimplementing session / timeout / SSL
        plumbing.
        """
        if self._session is None:
            raise RuntimeError('StatelessSandbox session is not initialized; did you call start()?')

        url = self._build_url(path)
        request_kwargs: Dict[str, Any] = {}
        if json is not None:
            request_kwargs['json'] = json
        if params is not None:
            request_kwargs['params'] = params
        if timeout is not None:
            request_kwargs['timeout'] = aiohttp.ClientTimeout(total=float(timeout))
        if not self._verify_ssl:
            request_kwargs['ssl'] = False

        async with self._session.request(method, url, **request_kwargs) as response:
            response.raise_for_status()
            data = await response.json()
            if not isinstance(data, dict):
                raise ValueError(f'Expected JSON object from {method} {url}, got {type(data).__name__}')
            return data

    async def _post_json(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Convenience wrapper around ``_request_json('POST', ...)``."""
        return await self._request_json('POST', path, json=payload, timeout=timeout)
