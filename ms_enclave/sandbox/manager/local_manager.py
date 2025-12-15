"""Sandbox environment manager."""

import asyncio
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from ms_enclave.sandbox.model.constants import DEFAULT_POOL_EXECUTION_TIMEOUT
from ms_enclave.utils import get_logger

from ..boxes import Sandbox, SandboxFactory
from ..model import (
    SandboxConfig,
    SandboxInfo,
    SandboxManagerConfig,
    SandboxManagerType,
    SandboxStatus,
    SandboxType,
    ToolResult,
)
from .base import SandboxManager, register_manager

logger = get_logger()


@register_manager(SandboxManagerType.LOCAL)
class LocalSandboxManager(SandboxManager):
    """Manager for sandbox environments."""

    def __init__(self, config: Optional[SandboxManagerConfig] = None, **kwargs):
        """Initialize sandbox manager.

        Args:
            config: Sandbox manager configuration
        """
        super().__init__(config, **kwargs)
        self._cleanup_interval = self.config.cleanup_interval or kwargs.get('cleanup_interval', 300)
        self._cleanup_task: Optional[asyncio.Task] = None
        self._pool_condition: Optional[asyncio.Condition] = None

    async def start(self) -> None:
        """Start the sandbox manager."""
        if self._running:
            return

        self._running = True
        self._pool_condition = asyncio.Condition()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info('Local sandbox manager started')

    async def stop(self) -> None:
        """Stop the sandbox manager."""
        if not self._running:
            return

        self._running = False

        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop and cleanup all sandboxes
        await self.cleanup_all_sandboxes()
        logger.info('Local sandbox manager stopped')

    async def create_sandbox(
        self,
        sandbox_type: SandboxType,
        config: Optional[Union[SandboxConfig, Dict]] = None,
        sandbox_id: Optional[str] = None
    ) -> str:
        """Create a new sandbox.

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
        try:
            # Create sandbox instance
            sandbox = SandboxFactory.create_sandbox(sandbox_type, config, sandbox_id)

            # Start the sandbox
            await sandbox.start()

            # Store sandbox
            self._sandboxes[sandbox.id] = sandbox

            logger.info(f'Created and started sandbox {sandbox.id} of type {sandbox_type}')
            return sandbox.id

        except Exception as e:
            logger.error(f'Failed to create sandbox of type {sandbox_type}: {e}')
            raise RuntimeError(f'Failed to create sandbox: {e}')

    async def get_sandbox(self, sandbox_id: str) -> Optional[Sandbox]:
        """Get sandbox by ID.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            Sandbox instance or None if not found
        """
        return self._sandboxes.get(sandbox_id)

    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Get sandbox information.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            Sandbox information or None if not found
        """
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox:
            return sandbox.get_info()
        return None

    async def list_sandboxes(self, status_filter: Optional[SandboxStatus] = None) -> List[SandboxInfo]:
        """List all sandboxes.

        Args:
            status_filter: Optional status filter

        Returns:
            List of sandbox information
        """
        result = []
        for sandbox in self._sandboxes.values():
            info = sandbox.get_info()
            if status_filter is None or info.status == status_filter:
                result.append(info)
        return result

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        """Stop a sandbox.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if stopped successfully, False if not found
        """
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            logger.warning(f'Sandbox {sandbox_id} not found for stopping')
            return False

        try:
            await sandbox.stop()
            logger.info(f'Stopped sandbox {sandbox_id}')
            return True
        except Exception as e:
            logger.error(f'Error stopping sandbox {sandbox_id}: {e}')
            return False

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Delete a sandbox.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if deleted successfully, False if not found
        """
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            logger.warning(f'Sandbox {sandbox_id} not found for deletion')
            return False

        try:
            await sandbox.stop()
            del self._sandboxes[sandbox_id]
            logger.info(f'Deleted sandbox {sandbox_id}')
            return True
        except Exception as e:
            logger.error(f'Error deleting sandbox {sandbox_id}: {e}')
            return False

    async def execute_tool(self, sandbox_id: str, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute tool in sandbox.

        Args:
            sandbox_id: Sandbox ID
            tool_name: Tool name to execute
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            ValueError: If sandbox or tool not found
        """
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f'Sandbox {sandbox_id} not found')

        if sandbox.status != SandboxStatus.RUNNING:
            raise ValueError(f'Sandbox {sandbox_id} is not running (status: {sandbox.status})')

        result = await sandbox.execute_tool(tool_name, parameters)
        return result

    async def get_sandbox_tools(self, sandbox_id: str) -> Dict[str, Any]:
        """Get available tools for a sandbox.

        Args:
            sandbox_id: Sandbox ID

        Returns:
            Dictionary of available tool types

        Raises:
            ValueError: If sandbox not found
        """
        sandbox = self._sandboxes.get(sandbox_id)
        if not sandbox:
            raise ValueError(f'Sandbox {sandbox_id} not found')

        return sandbox.get_available_tools()

    async def cleanup_all_sandboxes(self) -> None:
        """Clean up all sandboxes."""
        sandbox_ids = list(self._sandboxes.keys())
        logger.info(f'Cleaning up {len(sandbox_ids)} sandboxes')

        for sandbox_id in sandbox_ids:
            try:
                await self.delete_sandbox(sandbox_id)
            except Exception as e:
                logger.error(f'Error cleaning up sandbox {sandbox_id}: {e}')

    async def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics.

        Returns:
            Statistics dictionary
        """
        status_counter = Counter()
        type_counter = Counter()

        for sandbox in self._sandboxes.values():
            status_counter[sandbox.status.value] += 1
            type_counter[sandbox.sandbox_type.value] += 1

        stats = {
            'manager_type': 'local',
            'total_sandboxes': len(self._sandboxes),
            'status_counts': dict(status_counter),
            'sandbox_types': dict(type_counter),
            'running': self._running,
            'cleanup_interval': self._cleanup_interval,
            'pool_size': len(self._sandbox_pool),
            'pool_enabled': self.config.pool_size > 0,
            'pool_initialized': self._pool_initialized,
        }

        return stats

    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while self._running:
            try:
                await self._cleanup_expired_sandboxes()
                await asyncio.sleep(self._cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Error in cleanup loop: {e}')
                await asyncio.sleep(self._cleanup_interval)

    async def _cleanup_expired_sandboxes(self) -> None:
        """Clean up expired sandboxes."""
        current_time = datetime.now()
        expired_sandboxes = []

        for sandbox_id, sandbox in self._sandboxes.items():
            # Check if sandbox is in error state or stopped for too long
            if sandbox.status in [SandboxStatus.ERROR, SandboxStatus.STOPPED]:
                # Clean up after 1 hour
                if current_time - sandbox.updated_at > timedelta(hours=1):
                    expired_sandboxes.append(sandbox_id)
            # Check for very old sandboxes (48 hours)
            elif current_time - sandbox.created_at > timedelta(hours=48):
                expired_sandboxes.append(sandbox_id)

        # Clean up expired sandboxes
        if expired_sandboxes:
            logger.info(f'Found {len(expired_sandboxes)} expired sandboxes to clean up')

        for sandbox_id in expired_sandboxes:
            try:
                logger.info(f'Cleaning up expired sandbox: {sandbox_id}')
                await self.delete_sandbox(sandbox_id)
            except Exception as e:
                logger.error(f'Error cleaning up expired sandbox {sandbox_id}: {e}')

    async def initialize_pool(
        self,
        pool_size: Optional[int] = None,
        sandbox_type: Optional[SandboxType] = None,
        config: Optional[Union[SandboxConfig, Dict]] = None
    ) -> List[str]:
        """Initialize sandbox pool.

        Args:
            pool_size: Number of sandboxes in pool (uses config if not provided)
            sandbox_type: Type of sandbox to create
            config: Sandbox configuration (uses config.sandbox_config if not provided)

        Returns:
            List of created sandbox IDs
        """
        pool_size = pool_size or self.config.pool_size
        if pool_size <= 0:
            logger.warning('Pool size is 0, pool not initialized')
            return []

        config = config or self.config.sandbox_config
        sandbox_type = sandbox_type or SandboxType.DOCKER

        async with self._pool_lock:
            created_ids = []
            logger.info(f'Initializing pool with {pool_size} sandboxes of type {sandbox_type}')

            for i in range(pool_size):
                try:
                    # Create and start sandbox
                    created_id = await self.create_sandbox(sandbox_type, config)

                    # Get sandbox and set to IDLE status
                    sandbox = self._sandboxes.get(created_id)
                    if sandbox:
                        sandbox.status = SandboxStatus.IDLE
                        sandbox.updated_at = datetime.now()

                    # Add to pool
                    self._sandbox_pool.append(created_id)
                    created_ids.append(created_id)

                    logger.info(f'Added sandbox {created_id} to pool')
                except Exception as e:
                    logger.error(f'Failed to create sandbox {i} for pool: {e}')

            if created_ids:
                self._pool_initialized = True

            logger.info(f'Pool initialized with {len(created_ids)} sandboxes')
            return created_ids

    async def execute_tool_in_pool(
        self, tool_name: str, parameters: Dict[str, Any], timeout: Optional[float] = None
    ) -> ToolResult:
        """Execute tool using an available sandbox from the pool.

        Uses FIFO queue to get an idle sandbox, marks it as busy during execution,
        then returns it to the pool as idle. Multiple concurrent requests are queued
        and served in order as sandboxes become available.

        Args:
            tool_name: Tool name to execute
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            ValueError: If pool is empty or no sandbox available
            TimeoutError: If timeout waiting for available sandbox
        """
        if not self._pool_initialized:
            raise ValueError('Sandbox pool is empty, call initialize_pool first')

        if not self._pool_condition:
            raise RuntimeError('Sandbox manager not started')

        timeout = timeout or self.config.timeout or DEFAULT_POOL_EXECUTION_TIMEOUT

        async with self._pool_condition:
            # Wait for an available sandbox
            start_time = asyncio.get_event_loop().time()

            while True:
                # Try to find an idle sandbox
                sandbox_id = None
                for _ in range(len(self._sandbox_pool)):
                    candidate_id = self._sandbox_pool.popleft()
                    sandbox = self._sandboxes.get(candidate_id)

                    if sandbox and sandbox.status == SandboxStatus.IDLE:
                        sandbox_id = candidate_id
                        # Mark as busy
                        sandbox.status = SandboxStatus.BUSY
                        sandbox.updated_at = datetime.now()
                        logger.debug(f'Using sandbox {sandbox_id} from pool for tool {tool_name}')
                        break
                    elif sandbox:
                        # Put back to end of queue if it exists but is not idle
                        self._sandbox_pool.append(candidate_id)

                if sandbox_id:
                    break

                # Check timeout before waiting
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    raise TimeoutError(f'Timeout waiting for available sandbox from pool after {timeout}s')

                # Wait for notification that a sandbox is available
                try:
                    await asyncio.wait_for(self._pool_condition.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    raise TimeoutError(f'Timeout waiting for available sandbox from pool after {timeout}s')

        # Execute tool outside of condition lock
        try:
            sandbox = self._sandboxes[sandbox_id]
            result = await sandbox.execute_tool(tool_name, parameters)
            return result
        finally:
            # Return to pool and notify waiting tasks
            async with self._pool_condition:
                sandbox.status = SandboxStatus.IDLE
                sandbox.updated_at = datetime.now()
                self._sandbox_pool.append(sandbox_id)
                logger.debug(f'Returned sandbox {sandbox_id} to pool')
                # Notify one waiting task that a sandbox is available
                self._pool_condition.notify(1)
