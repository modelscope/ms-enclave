"""FastAPI server for sandbox system with optional API key authentication."""

import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..manager import LocalSandboxManager
from ..model import (
    DockerSandboxConfig,
    HealthCheckResult,
    SandboxConfig,
    SandboxInfo,
    SandboxStatus,
    SandboxType,
    ToolExecutionRequest,
    ToolResult,
)


class SandboxServer:
    """FastAPI-based sandbox server.
    """

    def __init__(self, cleanup_interval: int = 300, api_key: Optional[str] = None):
        """Initialize sandbox server.

        Args:
            cleanup_interval: Cleanup interval in seconds
            api_key: Optional API key to protect endpoints. If None, auth is disabled.
        """
        self.manager = LocalSandboxManager(cleanup_interval)
        self.api_key: Optional[str] = api_key
        self.app = FastAPI(
            title='Sandbox API',
            description='Agent sandbox execution environment',
            version='1.0.0',
            lifespan=self.lifespan
        )
        self._setup_middleware()
        self._setup_auth_middleware()
        self._setup_routes()
        self.start_time = time.time()

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """Application lifespan management."""
        # Startup
        await self.manager.start()
        yield
        # Shutdown
        await self.manager.stop()

    def _setup_middleware(self):
        """Setup middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'],
        )

    def _setup_auth_middleware(self) -> None:
        """Setup optional API key authentication middleware.

        When ``self.api_key`` is None, this middleware is a no-op.
        Otherwise, it enforces that every request includes the correct API key
        either via ``X-API-Key`` header or ``api_key`` query parameter.
        """

        @self.app.middleware('http')
        async def auth_middleware(request: Request, call_next):  # type: ignore[unused-ignore]
            # Fast path when auth is disabled
            if not self.api_key:
                return await call_next(request)

            provided = request.headers.get('x-api-key') or request.query_params.get('api_key')
            if provided == self.api_key:
                return await call_next(request)

            return JSONResponse(status_code=401, content={'detail': 'Unauthorized'})

    def _setup_routes(self):
        """Setup API routes."""

        # Health check
        @self.app.get('/health', response_model=HealthCheckResult)
        async def health_check():
            """Health check endpoint."""
            stats = await self.manager.get_stats()
            return HealthCheckResult(
                healthy=True,
                version='1.0.0',
                uptime=time.time() - self.start_time,
                active_sandboxes=stats['total_sandboxes'],
                system_info=stats
            )

        # Sandbox management
        @self.app.post('/sandbox/create')
        async def create_sandbox(sandbox_type: SandboxType, config: Optional[Dict] = None):
            """Create a new sandbox."""
            try:
                sandbox_id = await self.manager.create_sandbox(sandbox_type, config)

                return {'sandbox_id': sandbox_id}

            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get('/sandboxes')
        async def list_sandboxes(status: Optional[SandboxStatus] = None):
            """List all sandboxes."""
            sandboxes = await self.manager.list_sandboxes(status)
            return sandboxes

        @self.app.get('/sandbox/{sandbox_id}', response_model=SandboxInfo)
        async def get_sandbox_info(sandbox_id: str):
            """Get sandbox information."""
            info = await self.manager.get_sandbox_info(sandbox_id)
            if not info:
                raise HTTPException(status_code=404, detail='Sandbox not found')
            return info

        @self.app.post('/sandbox/{sandbox_id}/stop')
        async def stop_sandbox(sandbox_id: str):
            """Stop a sandbox."""
            success = await self.manager.stop_sandbox(sandbox_id)
            if not success:
                raise HTTPException(status_code=404, detail='Sandbox not found')
            return {'message': 'Sandbox stopped successfully'}

        @self.app.delete('/sandbox/{sandbox_id}')
        async def delete_sandbox(sandbox_id: str):
            """Delete a sandbox."""
            success = await self.manager.delete_sandbox(sandbox_id)
            if not success:
                raise HTTPException(status_code=404, detail='Sandbox not found')
            return {'message': 'Sandbox deleted successfully'}

        # Tool execution
        @self.app.post('/sandbox/tool/execute', response_model=ToolResult)
        async def execute_tool(request: ToolExecutionRequest):
            """Execute tool in sandbox."""
            try:
                result = await self.manager.execute_tool(request.sandbox_id, request.tool_name, request.parameters)
                return result
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get('/sandbox/{sandbox_id}/tools')
        async def get_sandbox_tools(sandbox_id: str):
            """Get available tools for a sandbox."""
            try:
                tools = await self.manager.get_sandbox_tools(sandbox_id)
                return tools
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))

        # System info
        @self.app.get('/stats')
        async def get_stats():
            """Get system statistics."""
            return await self.manager.get_stats()

    def run(self, host: str = '0.0.0.0', port: int = 8000, **kwargs):
        """Run the server.

        Args:
            host: Host to bind to
            port: Port to bind to
            **kwargs: Additional uvicorn arguments
        """
        import uvicorn
        uvicorn.run(self.app, host=host, port=port, **kwargs)


# Create a default server instance
def create_server(cleanup_interval: int = 300, api_key: Optional[str] = None) -> SandboxServer:
    """Create a sandbox server instance.

    Args:
        cleanup_interval: Cleanup interval in seconds
        api_key: Optional API key to protect endpoints. If None, auth is disabled.

    Returns:
        Sandbox server instance
    """
    return SandboxServer(cleanup_interval, api_key)
