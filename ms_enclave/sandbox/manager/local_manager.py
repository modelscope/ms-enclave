"""Sandbox environment manager."""

import asyncio
import time
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from ms_enclave.utils import get_logger

from ..boxes import Sandbox, SandboxFactory
from ..model import SandboxConfig, SandboxInfo, SandboxStatus, SandboxType, ToolResult
from .base import SandboxManager

logger = get_logger()


class LocalSandboxManager(SandboxManager):
    """Manager for sandbox environments."""

    def __init__(self, cleanup_interval: int = 300):  # 5 minutes
        """Initialize sandbox manager.

        Args:
            cleanup_interval: Interval between cleanup runs in seconds
        """
        super().__init__()
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the sandbox manager."""
        if self._running:
            return

        self._running = True
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
