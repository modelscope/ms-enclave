"""Optional SDK boundary and connection settings for E2B services."""

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Self, TypeVar

import httpx
from pydantic import SecretStr

from ms_enclave.sandbox.model import E2BSandboxManagerConfig
from ms_enclave.sandbox.utils.e2b_helpers import BuildMode, E2BProvider
from ms_enclave.utils import get_logger

logger = get_logger()
E2B_REQUEST_TIMEOUT_S = 60.0
_DISPATCH_ATTEMPTS = 3
T = TypeVar('T')


def require_e2b() -> None:
    """Load the optional SDK only when an E2B backend is requested."""
    try:
        import e2b
    except ModuleNotFoundError as exc:
        if exc.name != 'e2b':
            raise
        raise ImportError(
            "The E2B sandbox requires the e2b SDK (Python >= 3.11): pip install 'ms-enclave[e2b]'"
        ) from exc


class E2BError(RuntimeError):
    """Public error context with SDK details protected from implicit logging."""

    def __init__(self, message: str, *, details: Optional[SecretStr] = None, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.details = details
        self.status_code = status_code

    @classmethod
    def from_exception(cls, operation: str, exc: Exception, *, run_id: Optional[str] = None) -> Self:
        """Keep diagnostic types/status visible without exposing SDK response text."""
        status = (
            exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else getattr(exc, 'status_code', None)
        )
        status = status if isinstance(status, int) else None
        context = [f'run_id={run_id}'] if run_id else []
        if status is not None:
            context.append(f'HTTP {status}')
        suffix = f' ({", ".join(context)})' if context else ''
        reason = str(exc) if isinstance(exc, E2BError) else type(exc).__name__
        details = exc.details if isinstance(exc, E2BError) else SecretStr(str(exc))
        return cls(f'E2B {operation} failed{suffix}: {reason}', details=details, status_code=status)


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

    def api_client(self) -> Any:
        """Create an SDK API client with this connection's settings."""
        from e2b.api.client_async import get_api_client
        from e2b.connection_config import ConnectionConfig

        return get_api_client(ConnectionConfig(**self.api_params(retries=0)))


async def retry_dispatch(op_name: str, call: Callable[[], Awaitable[T]], *, run_id: str) -> T:
    """Retry only connection establishment failures and explicit rate limits."""
    from e2b import RateLimitException

    retryable = (ConnectionError, httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, RateLimitException)
    for attempt in range(1, _DISPATCH_ATTEMPTS + 1):
        try:
            return await call()
        except Exception as exc:
            error = E2BError.from_exception(op_name, exc, run_id=run_id)
            rate_limited = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
            if (not isinstance(exc, retryable) and not rate_limited) or attempt == _DISPATCH_ATTEMPTS:
                raise error from None
            logger.warning(f'{error}; attempt={attempt}, retrying')
            await asyncio.sleep(2 ** (attempt - 1))
