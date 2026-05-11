"""VolcEngine / SandboxFusion stateless sandbox.

Concrete :class:`StatelessSandbox` subclass that speaks the SandboxFusion HTTP
protocol (``POST {base_url}{run_code_path}`` with a JSON ``{code, language}``
body). All vendor/protocol specifics live here — the generic plumbing (shared
``aiohttp.ClientSession``, lifecycle, HTTP helpers) is inherited from
:class:`StatelessSandbox`.

A :class:`VolcengineSandbox` is normally created by
:class:`~ms_enclave.sandbox.manager.VolcengineSandboxManager`, which injects
the shared session and manager-level HTTP settings. It is also registered with
:class:`SandboxFactory` for introspection, but direct factory creation without
a ``base_url`` will fail fast in ``StatelessSandbox.__init__``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import aiohttp

from ..model import ExecutionStatus, SandboxType, ToolResult, VolcengineSandboxConfig
from .base import register_sandbox
from .stateless_sandbox import StatelessSandbox


@register_sandbox(SandboxType.VOLCENGINE)
class VolcengineSandbox(StatelessSandbox):
    """Stateless sandbox backed by a SandboxFusion HTTP service."""

    def __init__(
        self,
        config: VolcengineSandboxConfig,
        sandbox_id: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        run_code_path: str = '/run_code',
        request_timeout: float = 30.0,
        verify_ssl: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None,
        dataset_language_map: Optional[Dict[str, str]] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__(
            config,
            base_url=base_url or '',
            request_timeout=request_timeout,
            verify_ssl=verify_ssl,
            extra_headers=extra_headers,
            api_key=api_key,
            session=session,
            sandbox_id=sandbox_id,
        )
        # Convenient reference to the typed sandbox config for tool dispatch.
        self.config: VolcengineSandboxConfig = config
        self._run_code_path: str = run_code_path if run_code_path.startswith('/') else f'/{run_code_path}'
        self._dataset_language_map: Dict[str, str] = (dict(dataset_language_map) if dataset_language_map else {})

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
