"""Optional SDK boundary and connection settings for E2B services."""

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

import httpx
from pydantic import SecretStr

from ms_enclave.utils import get_logger

from ..model import E2BSandboxManagerConfig
from ..utils.e2b_helpers import BuildMode, E2BProvider, redact


class _MissingE2BError(Exception):
    """Placeholder exception when the optional SDK is unavailable."""


try:
    from e2b import AsyncSandbox, AsyncTemplate, CommandExitException, RateLimitException
    from e2b.api.client_async import get_api_client
    from e2b.connection_config import ConnectionConfig

    _E2B_IMPORT_ERROR: Optional[ImportError] = None
except ImportError as exc:
    AsyncSandbox = AsyncTemplate = get_api_client = ConnectionConfig = None
    CommandExitException = RateLimitException = _MissingE2BError
    _E2B_IMPORT_ERROR = exc

logger = get_logger()
E2B_REQUEST_TIMEOUT_S = 60.0
_DISPATCH_ATTEMPTS = 3
T = TypeVar('T')


def require_e2b() -> None:
    """Fail with an installation hint when E2B was not installed."""
    if _E2B_IMPORT_ERROR is not None:
        raise ImportError(
            "The E2B sandbox requires the e2b SDK (Python >= 3.11): pip install 'ms-enclave[e2b]'"
        ) from _E2B_IMPORT_ERROR


@dataclass(frozen=True)
class E2BConnection:
    """Resolved settings shared by the manager, sandboxes and template resolver."""

    api_key: SecretStr
    api_url: Optional[str]
    domain: Optional[str]
    provider: E2BProvider
    region: Optional[str]
    build_mode: BuildMode

    @classmethod
    def from_config(cls, config: E2BSandboxManagerConfig) -> 'E2BConnection':
        """Resolve a validated manager configuration."""
        return cls(
            config.api_key,
            config.api_url,
            config.domain,
            config.provider,
            config.target_region,
            config.resolved_build_mode,
        )

    def api_params(self, **extra: Any) -> Dict[str, Any]:
        """Build SDK options, omitting unset endpoints to preserve SDK defaults."""
        params = {'api_key': self.api_key.get_secret_value(), 'request_timeout': E2B_REQUEST_TIMEOUT_S}
        if self.api_url:
            params['api_url'] = self.api_url
        if self.domain:
            params['domain'] = self.domain
        return {**params, **extra}

    def redact(self, text: str) -> str:
        """Remove the connection key from diagnostic text."""
        return redact(text, self.api_key.get_secret_value())


async def retry_dispatch(
    op_name: str, call: Callable[[], Awaitable[T]], *, run_id: str, redactor: Callable[[str], str]
) -> T:
    """Retry only connection establishment failures and explicit rate limits."""
    retryable = (ConnectionError, httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, RateLimitException)
    for attempt in range(1, _DISPATCH_ATTEMPTS + 1):
        try:
            return await call()
        except Exception as exc:
            reason = redactor(str(exc))
            rate_limited = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
            if (not isinstance(exc, retryable) and not rate_limited) or attempt == _DISPATCH_ATTEMPTS:
                raise RuntimeError(f'E2B {op_name} failed (run_id={run_id}): {reason}') from None
            logger.warning(f'E2B {op_name} attempt={attempt} run_id={run_id}: {reason}; retrying')
            await asyncio.sleep(2 ** (attempt - 1))
