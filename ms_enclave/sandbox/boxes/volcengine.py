"""VolcEngine / SandboxFusion stateless sandbox.

Concrete :class:`StatelessSandbox` subclass that speaks the SandboxFusion HTTP
protocol (``POST {base_url}{run_code_path}`` with a JSON ``{code, language}``
body). All vendor/protocol specifics live here — the generic plumbing (shared
``aiohttp.ClientSession``, lifecycle, HTTP helpers) is inherited from
:class:`StatelessSandbox`.

A :class:`VolcengineSandbox` is normally created by
:class:`~ms_enclave.sandbox.manager.VolcengineSandboxManager`, which injects
the shared session and manager-level HTTP settings. It is also registered
with :class:`SandboxFactory` — when created via the factory, HTTP settings
are read from :class:`VolcengineSandboxConfig`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import aiohttp

from ..model import ExecutionStatus, SandboxType, ToolResult, VolcengineSandboxConfig
from .base import register_sandbox
from .stateless_sandbox import StatelessSandbox

# Default language mapping for MINOR_RUNNERS that require capitalised identifiers.
_DEFAULT_DATASET_LANGUAGE_MAP: Dict[str, str] = {
    'r': 'R',
    'd_ut': 'D_ut',
    'ts': 'typescript',
}


@register_sandbox(SandboxType.VOLCENGINE)
class VolcengineSandbox(StatelessSandbox):
    """Stateless sandbox backed by a SandboxFusion HTTP service."""

    def __init__(
        self,
        config: VolcengineSandboxConfig,
        sandbox_id: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        run_code_path: Optional[str] = None,
        request_timeout: Optional[float] = None,
        verify_ssl: Optional[bool] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None,
        dataset_language_map: Optional[Dict[str, str]] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        # When explicit kwargs are not provided, fall back to config values.
        _base_url = base_url if base_url is not None else (config.base_url or '')
        _run_code_path = run_code_path if run_code_path is not None else config.run_code_path
        _request_timeout = request_timeout if request_timeout is not None else config.request_timeout
        _verify_ssl = verify_ssl if verify_ssl is not None else config.verify_ssl
        _extra_headers = extra_headers if extra_headers is not None else config.extra_headers
        _api_key = api_key if api_key is not None else config.api_key
        _dataset_language_map = dataset_language_map if dataset_language_map is not None else config.dataset_language_map

        super().__init__(
            config,
            base_url=_base_url,
            request_timeout=_request_timeout,
            verify_ssl=_verify_ssl,
            extra_headers=_extra_headers,
            api_key=_api_key,
            session=session,
            sandbox_id=sandbox_id,
        )
        # Convenient reference to the typed sandbox config for tool dispatch.
        self.config: VolcengineSandboxConfig = config
        self._run_code_path: str = _run_code_path if _run_code_path.startswith('/') else f'/{_run_code_path}'
        # Merge user-provided map on top of the defaults so that explicit
        # entries take precedence, but MINOR_RUNNERS (r, d_ut, …) get their
        # required capitalisation even when the caller supplies nothing.
        _merged = dict(_DEFAULT_DATASET_LANGUAGE_MAP)
        if _dataset_language_map:
            _merged.update(_dataset_language_map)
        self._dataset_language_map: Dict[str, str] = _merged

    @property
    def sandbox_type(self) -> SandboxType:
        return SandboxType.VOLCENGINE

    @property
    def run_code_path(self) -> str:
        return self._run_code_path

    # --------------------------------------------------------------------- #
    # SandboxFusion protocol                                                #
    # --------------------------------------------------------------------- #
    async def run_code(
        self,
        code: str,
        language: str,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Issue ``POST {base_url}{run_code_path}`` and return the parsed JSON body.

        Applies ``dataset_language_map`` to translate language identifiers
        before sending, so e.g. ``r`` can be sent upstream as ``R``.
        """
        mapped_language = (
            self._dataset_language_map.get(language, language) if self._dataset_language_map else language
        )
        payload = {'code': code, 'language': mapped_language}
        return await self._post_json(self._run_code_path, payload, timeout=timeout)

    # --------------------------------------------------------------------- #
    # Response -> ToolResult helper                                         #
    # --------------------------------------------------------------------- #
    @staticmethod
    def parse_run_code_response(resp: Dict[str, Any]) -> Tuple[ExecutionStatus, str, Optional[str]]:
        """Parse a SandboxFusion-style ``/run_code`` response into ``(status, output, error)``.

        Merges stdout / stderr / ``compile_result.stderr`` / top-level message
        into a human-readable output; maps the overall status + non-zero
        ``return_code`` to :attr:`ExecutionStatus.ERROR`.
        """
        status_field = resp.get('status')
        message = resp.get('message') or ''

        compile_result = resp.get('compile_result') or {}
        run_result = resp.get('run_result') or {}

        stdout = run_result.get('stdout') or '' if isinstance(run_result, dict) else ''
        stderr = run_result.get('stderr') or '' if isinstance(run_result, dict) else ''
        return_code = run_result.get('return_code') if isinstance(run_result, dict) else None
        compile_stderr = compile_result.get('stderr') or '' if isinstance(compile_result, dict) else ''

        def _append(base: str, extra: str) -> str:
            if not extra:
                return base
            if not base:
                return extra
            return base + ('' if base.endswith('\n') else '\n') + extra

        output = stdout
        error_parts = ''
        error_parts = _append(error_parts, stderr)
        error_parts = _append(error_parts, compile_stderr)
        if message and message not in output and message not in error_parts:
            error_parts = _append(error_parts, message)

        ok = (status_field == 'Success') and (return_code in (0, '0', None))
        status = ExecutionStatus.SUCCESS if ok else ExecutionStatus.ERROR
        return status, output, (error_parts or None)

    def build_tool_result(self, tool_name: str, resp: Dict[str, Any]) -> ToolResult:
        """Convenience wrapper: turn a ``/run_code`` response into a :class:`ToolResult`."""
        status, output, error = self.parse_run_code_response(resp)
        return ToolResult(tool_name=tool_name, status=status, output=output, error=error)
