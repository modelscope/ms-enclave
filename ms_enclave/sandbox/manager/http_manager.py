"""HTTP-based sandbox manager for remote sandbox services."""

from typing import Any, Dict, List, Optional, Union

import aiohttp

from ms_enclave.utils import get_logger

from ..model import SandboxConfig, SandboxInfo, SandboxStatus, SandboxType, ToolExecutionRequest, ToolResult
from .base import SandboxManager

logger = get_logger()


class HttpSandboxManager(SandboxManager):
    """HTTP-based sandbox manager for remote services.
    """

    def __init__(self, base_url: str, timeout: int = 30, api_key: Optional[str] = None):
        """Initialize HTTP sandbox manager.

        Args:
            base_url: Base URL of the sandbox service
            timeout: Request timeout in seconds
            api_key: Optional API key to include as ``X-API-Key`` header for all requests
        """
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._default_headers: Optional[Dict[str, str]] = {'X-API-Key': api_key} if api_key else None
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        """Start the HTTP sandbox manager."""
        if self._running:
            return

        self._connector = aiohttp.TCPConnector()
        self._session = aiohttp.ClientSession(
            connector=self._connector, timeout=self.timeout, headers=self._default_headers
        )
        self._running = True
        logger.info(f'HTTP sandbox manager started, connected to {self.base_url}')

    async def stop(self) -> None:
        """Stop the HTTP sandbox manager."""
        if not self._running:
            return

        self._running = False

        # Clean up all sandboxes created by this manager
        if self._sandboxes:
            logger.info(f'Cleaning up {len(self._sandboxes)} sandboxes created by this manager')
            await self.cleanup_all_sandboxes()

        if self._session:
            await self._session.close()
            self._session = None
        logger.info('HTTP sandbox manager stopped')

    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None
    ) -> str:
        """Create a new sandbox via HTTP API.

        Args:
            sandbox_type: Type of sandbox to create
            config: Sandbox configuration
            sandbox_id: Optional sandbox ID

        Returns:
            Sandbox ID

        Raises:
            ValueError: If sandbox type is not supported
            RuntimeError: If sandbox creation fails
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        # Match server's endpoint format: POST /sandbox/create
        params = {'sandbox_type': sandbox_type.value if isinstance(sandbox_type, SandboxType) else sandbox_type}
        if isinstance(config, SandboxConfig):
            payload = config.model_dump(exclude_none=True)
        elif isinstance(config, dict):
            payload = config
        else:
            payload = {}

        try:
            async with self._session.post(f'{self.base_url}/sandbox/create', params=params, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    sandbox_id = data['sandbox_id']

                    # Get sandbox info and store in _sandboxes
                    sandbox_info = await self.get_sandbox_info(sandbox_id)
                    if sandbox_info:
                        self._sandboxes[sandbox_id] = sandbox_info

                    logger.info(f'Created sandbox {sandbox_id} via HTTP API')
                    return sandbox_id
                else:
                    error_data = await response.json()
                    raise RuntimeError(f"HTTP {response.status}: {error_data.get('detail', 'Unknown error')}")

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error creating sandbox: {e}')
            raise RuntimeError(f'Failed to create sandbox: {e}')

    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Get sandbox information via HTTP API.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            Sandbox information or None if not found
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Match server's endpoint format: GET /sandbox/{sandbox_id}
            async with self._session.get(f'{self.base_url}/sandbox/{sandbox_id}') as response:
                if response.status == 200:
                    data = await response.json()
                    return SandboxInfo.model_validate(data)
                elif response.status == 404:
                    return None
                else:
                    error_data = await response.json()
                    logger.error(f'Error getting sandbox info: HTTP {response.status}: {error_data}')
                    return None

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error getting sandbox info: {e}')
            return None

    async def list_sandboxes(self, status_filter: Optional[SandboxStatus] = None) -> List[SandboxInfo]:
        """List all sandboxes via HTTP API.

        Args:
            status_filter: Optional status filter

        Returns:
            List of sandbox information
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        params = {}
        if status_filter:
            params['status'] = status_filter.value

        try:
            # Match server's endpoint format: GET /sandboxes
            async with self._session.get(f'{self.base_url}/sandboxes', params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return [SandboxInfo.model_validate(item) for item in data]
                else:
                    error_data = await response.json()
                    logger.error(f'Error listing sandboxes: HTTP {response.status}: {error_data}')
                    return []

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error listing sandboxes: {e}')
            return []

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        """Stop a sandbox via HTTP API.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if stopped successfully, False if not found
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Match server's endpoint format: POST /sandbox/{sandbox_id}/stop
            async with self._session.post(f'{self.base_url}/sandbox/{sandbox_id}/stop') as response:
                if response.status == 200:
                    logger.info(f'Stopped sandbox {sandbox_id} via HTTP API')
                    return True
                elif response.status == 404:
                    logger.warning(f'Sandbox {sandbox_id} not found for stopping')
                    return False
                else:
                    error_data = await response.json()
                    logger.error(f'Error stopping sandbox: HTTP {response.status}: {error_data}')
                    return False

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error stopping sandbox: {e}')
            return False

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Delete a sandbox via HTTP API.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if deleted successfully, False if not found
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Match server's endpoint format: DELETE /sandbox/{sandbox_id}
            async with self._session.delete(f'{self.base_url}/sandbox/{sandbox_id}') as response:
                if response.status == 200:
                    # Remove from tracking when successfully deleted
                    self._sandboxes.pop(sandbox_id, None)
                    logger.info(f'Deleted sandbox {sandbox_id} via HTTP API')
                    return True
                elif response.status == 404:
                    # Also remove from tracking if not found (already deleted)
                    self._sandboxes.pop(sandbox_id, None)
                    logger.warning(f'Sandbox {sandbox_id} not found for deletion')
                    return False
                else:
                    error_data = await response.json()
                    logger.error(f'Error deleting sandbox: HTTP {response.status}: {error_data}')
                    return False

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error deleting sandbox: {e}')
            return False

    async def execute_tool(self, sandbox_id: str, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute tool in sandbox via HTTP API.

        Args:
            sandbox_id: Sandbox ID
            tool_name: Tool name to execute
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            ValueError: If sandbox or tool not found
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        # Create proper request object to match server expectations
        request = ToolExecutionRequest(sandbox_id=sandbox_id, tool_name=tool_name, parameters=parameters)
        payload = request.model_dump()

        try:
            # Match server's endpoint format: POST /sandbox/tool/execute
            async with self._session.post(f'{self.base_url}/sandbox/tool/execute', json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return ToolResult.model_validate(data)
                elif response.status == 404:
                    error_data = await response.json()
                    raise ValueError(error_data.get('detail', f'Sandbox {sandbox_id} not found'))
                elif response.status == 500:
                    error_data = await response.json()
                    raise RuntimeError(error_data.get('detail', 'Internal server error'))
                else:
                    error_data = await response.json()
                    raise RuntimeError(f"HTTP {response.status}: {error_data.get('detail', 'Unknown error')}")

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error executing tool: {e}')
            raise RuntimeError(f'Failed to execute tool: {e}')

    async def get_sandbox_tools(self, sandbox_id: str) -> Dict[str, Any]:
        """Get available tools for a sandbox via HTTP API.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            List of available tool types

        Raises:
            ValueError: If sandbox not found
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Match server's endpoint format: GET /sandbox/{sandbox_id}/tools
            async with self._session.get(f'{self.base_url}/sandbox/{sandbox_id}/tools') as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 404:
                    error_data = await response.json()
                    raise ValueError(error_data.get('detail', f'Sandbox {sandbox_id} not found'))
                else:
                    error_data = await response.json()
                    raise RuntimeError(f"HTTP {response.status}: {error_data.get('detail', 'Unknown error')}")

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error getting sandbox tools: {e}')
            raise RuntimeError(f'Failed to get sandbox tools: {e}')

    async def cleanup_all_sandboxes(self) -> None:
        """Clean up all sandboxes created by this manager via HTTP API."""
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Clean up only the sandboxes created by this manager
            sandbox_ids = list(self._sandboxes.keys())
            deleted_count = 0

            for sandbox_id in sandbox_ids:
                try:
                    if await self.delete_sandbox(sandbox_id):
                        deleted_count += 1
                except Exception as e:
                    logger.error(f'Error deleting sandbox {sandbox_id}: {e}')

            logger.info(f'Cleaned up {deleted_count} sandboxes created by this manager')

        except Exception as e:
            logger.error(f'HTTP client error cleaning up sandboxes: {e}')

    async def get_stats(self) -> Dict[str, Any]:
        """Get server statistics via HTTP API.

        Returns:
            Server statistics dictionary
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Get server stats
            async with self._session.get(f'{self.base_url}/stats') as response:
                if response.status == 200:
                    server_stats = await response.json()
                else:
                    error_data = await response.json()
                    logger.error(f'Error getting server stats: HTTP {response.status}: {error_data}')
                    server_stats = {}

            # Add local tracking stats
            from collections import Counter
            status_counter = Counter()
            type_counter = Counter()

            for sandbox_info in self._sandboxes.values():
                status_counter[sandbox_info.status.value] += 1
                type_counter[sandbox_info.sandbox_type.value] += 1

            local_stats = {
                'manager_type': 'http',
                'base_url': self.base_url,
                'tracked_sandboxes': len(self._sandboxes),
                'tracked_status_counts': dict(status_counter),
                'tracked_sandbox_types': dict(type_counter),
                'running': self._running,
            }

            # Combine server and local stats
            return {**server_stats, **local_stats}

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error getting server stats: {e}')
            return {
                'manager_type': 'http',
                'base_url': self.base_url,
                'tracked_sandboxes': len(self._sandboxes),
                'running': self._running,
                'error': str(e)
            }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check via HTTP API.

        Returns:
            Health check result
        """
        if not self._session:
            raise RuntimeError('Manager not started')

        try:
            # Match server's endpoint format: GET /health
            async with self._session.get(f'{self.base_url}/health') as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_data = await response.json()
                    logger.error(f'Health check failed: HTTP {response.status}: {error_data}')
                    return {'healthy': False, 'error': f'HTTP {response.status}'}

        except aiohttp.ClientError as e:
            logger.error(f'HTTP client error during health check: {e}')
            return {'healthy': False, 'error': str(e)}
