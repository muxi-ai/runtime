"""
Formation Server Implementation

This module provides the FastAPI-based HTTP server for MUXI formations.
It handles both admin operations (formation management) and client operations
(user interactions) with a dual-key authentication system.
"""

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import Optional, TYPE_CHECKING

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ...services import observability
from ...utils.version import get_version

if TYPE_CHECKING:
    from ..formation import Formation


class FormationServer:
    """
    HTTP server for exposing formation capabilities via REST API.

    This server provides:
    - Admin endpoints for formation management (add/remove agents, update config)
    - Client endpoints for user interactions (chat, memories, async jobs)
    - MCP endpoint for tool-based access
    - Health and status monitoring
    """

    def __init__(self, formation: "Formation", host: str = "0.0.0.0", port: int = 8271, **kwargs):
        """
        Initialize the Formation server.

        Args:
            formation: The Formation instance to serve
            host: Host to bind to (default: 0.0.0.0)
            port: Port to bind to (default: 8271)
            **kwargs: Additional server configuration
        """
        self.formation = formation
        self.host = host
        self.port = port
        self.config = kwargs

        # Server state
        self._app: Optional[FastAPI] = None
        self._server: Optional[uvicorn.Server] = None
        self._server_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._active_connections: set = set()
        self._shutdown_timeout = 30.0

        # Extract API keys from formation
        self.admin_key = formation._api_keys.get("admin", "")
        self.client_key = formation._api_keys.get("client", "")

        # Log server configuration
        observability.observe(
            event_type=observability.SystemEvents.INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_server",
                "host": self.host,
                "port": self.port,
                "has_admin_key": bool(self.admin_key),
                "has_client_key": bool(self.client_key),
                "formation_id": formation.formation_id,
            },
            description=f"Initializing Formation server on {self.host}:{self.port}",
        )

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Manage server lifecycle events.

        This context manager handles startup and shutdown tasks,
        ensuring graceful initialization and cleanup.
        """
        # Startup
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_server",
                "formation_id": self.formation.formation_id,
                "endpoints_count": len(app.routes),
            },
            description="Formation server started successfully",
        )

        # Log server startup
        observability.observe(
            event_type=observability.ServerEvents.SERVER_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_api_server",
                "host": self.host,
                "port": self.port,
                "formation_id": self.formation.formation_id,
                "server_url": f"http://{self.host}:{self.port}",
                "endpoints_count": len(app.routes),
            },
            description=f"Formation API server started on http://{self.host}:{self.port}",
        )

        # Handle API key display and warnings
        generated_keys = getattr(self.formation, "_generated_api_keys", {})

        if generated_keys:
            # Log warning about auto-generated keys
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "formation_api_server",
                    "generated_keys": list(generated_keys.keys()),
                    "admin_key_generated": "admin" in generated_keys,
                    "client_key_generated": "client" in generated_keys,
                    "warning": "Auto-generated API keys are for development only",
                    "admin_key": "••••••••" if "admin" in generated_keys else None,
                    "client_key": "••••••••" if "client" in generated_keys else None,
                },
                description="Auto-generated API keys created - NOT recommended for production use",
            )

            # Still print to console for development visibility
            print(f"\n✅ Formation server started on http://{self.host}:{self.port}")
            print("\n" + "=" * 60)
            print("⚠️  AUTO-GENERATED API KEYS - DEVELOPMENT ONLY")
            print("=" * 60)
            print("🔒 The following API keys were automatically generated")
            print("   because none were provided in your formation configuration.")
            print()
            print("⚠️  WARNING: This is NOT recommended for production use!")
            print("   Please configure proper API keys in your formation.yaml:")
            print()
            print("   server:")
            print("     api_keys:")
            print('       admin_key: "${{ secrets.FORMATION_ADMIN_API_KEY }}"')
            print('       client_key: "${{ secrets.FORMATION_CLIENT_API_KEY }}"')
            print()
            print("📋 Generated API Keys:")

            if "admin" in generated_keys:
                print(f"   Admin API Key:  {generated_keys['admin']}")
            if "client" in generated_keys:
                print(f"   Client API Key: {generated_keys['client']}")
            print("=" * 60)
            print()
        else:
            # Log that keys were loaded from configuration
            observability.observe(
                event_type=observability.SystemEvents.INITIALIZING,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "api_keys_source": "configuration",
                    "has_admin_key": bool(self.admin_key),
                    "has_client_key": bool(self.client_key),
                },
                description="API keys loaded from formation configuration",
            )

            # Minimal console output for configured keys
            print(f"\n✅ Formation server started on http://{self.host}:{self.port}")
            if self.admin_key and self.client_key:
                print("🔒 API keys loaded from configuration")
            print()

        yield

        # Shutdown - drain connections gracefully
        observability.observe(
            event_type=observability.SystemEvents.CLEANUP,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_server",
                "formation_id": self.formation.formation_id,
                "active_connections": len(self._active_connections),
                "shutdown_timeout": self._shutdown_timeout,
            },
            description="Formation server shutting down - draining connections",
        )

        # Wait for active connections to complete
        if self._active_connections:
            observability.observe(
                event_type=observability.SystemEvents.CLEANUP,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_server",
                    "active_connections": len(self._active_connections),
                    "action": "draining_connections",
                },
                description=f"Waiting for {len(self._active_connections)} active connections to complete",
            )

            # Wait for connections to finish with timeout
            start_time = asyncio.get_event_loop().time()
            while (
                self._active_connections
                and (asyncio.get_event_loop().time() - start_time) < self._shutdown_timeout
            ):
                await asyncio.sleep(0.1)

            remaining_connections = len(self._active_connections)
            if remaining_connections > 0:
                observability.observe(
                    event_type=observability.SystemEvents.CLEANUP,
                    level=observability.EventLevel.WARNING,
                    data={
                        "service": "formation_server",
                        "remaining_connections": remaining_connections,
                        "timeout_seconds": self._shutdown_timeout,
                        "action": "force_close",
                    },
                    description=f"Shutdown timeout reached - {remaining_connections} connections still active",
                )
            else:
                observability.observe(
                    event_type=observability.SystemEvents.CLEANUP,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "formation_server",
                        "action": "connections_drained",
                        "drain_time_seconds": asyncio.get_event_loop().time() - start_time,
                    },
                    description="All connections drained successfully",
                )

    def _create_app(self) -> FastAPI:
        """
        Create and configure the FastAPI application.

        Returns:
            Configured FastAPI instance
        """
        app = FastAPI(
            title="MUXI Formation API",
            description="HTTP API for MUXI formation management and interactions",
            version=get_version(),
            lifespan=self.lifespan,
        )

        # Store formation reference in app state
        app.state.formation = self.formation

        # Add middleware in order (last added = first executed)
        # 1. CORS (needs to be first to handle preflight)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allow all origins for server-to-server
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Import and add custom middleware
        from .middleware import (
            ErrorHandlingMiddleware,
            RequestTrackingMiddleware,
            APILoggingMiddleware,
            ConnectionTrackingMiddleware,
        )

        # 2. Connection tracking (for graceful shutdown)
        app.add_middleware(ConnectionTrackingMiddleware, server_instance=self)

        # 3. Error handling (catch all exceptions)
        app.add_middleware(ErrorHandlingMiddleware)

        # 4. Request tracking (generate request IDs)
        app.add_middleware(RequestTrackingMiddleware)

        # 5. API logging (log requests)
        app.add_middleware(APILoggingMiddleware)

        # Register routers
        self._register_health_routes(app)
        self._register_admin_routes(app)
        self._register_client_routes(app)

        return app

    def _register_health_routes(self, app: FastAPI) -> None:
        """Register health and status endpoints."""
        from .routes.health import router

        # Health routes are not versioned for easier monitoring
        app.include_router(router, tags=["health"])

    def _register_admin_routes(self, app: FastAPI) -> None:
        """Register admin management endpoints."""
        from .auth import AdminKeyAuth
        from fastapi import Depends

        # Import all admin route modules
        from .routes.admin import (
            agents,
            secrets,
            config,
            overlord,
            mcp,
            llm,
            logging,
            memory,
            scheduler,
            a2a,
        )
        from .routes.admin.async_routes import router as async_router

        # Create auth dependency
        admin_auth = AdminKeyAuth(self.admin_key)

        # Register all admin routers with auth dependency
        admin_routers = [
            agents.router,
            secrets.router,
            config.router,
            overlord.router,
            mcp.router,
            llm.router,
            logging.router,
            memory.router,
            async_router,
            scheduler.router,
            a2a.router,
        ]

        for router in admin_routers:
            app.include_router(router, prefix="/v1", dependencies=[Depends(admin_auth)])

    def _register_client_routes(self, app: FastAPI) -> None:
        """Register client interaction endpoints."""
        from .auth import ClientKeyAuth
        from fastapi import Depends

        # Import all client route modules
        from .routes.client import chat, events, jobs, memory

        # Create auth dependency
        client_auth = ClientKeyAuth(self.client_key)

        # Register all client routers with auth dependency
        client_routers = [chat.router, events.router, jobs.router, memory.router]

        for router in client_routers:
            app.include_router(router, prefix="/v1", dependencies=[Depends(client_auth)])

    async def start(self, block: bool = True) -> None:
        """
        Start the Formation server.

        Args:
            block: Whether to block until server stops (default: True)
        """
        if self._server_task and not self._server_task.done():
            raise RuntimeError("Server is already running")

        # Create FastAPI app
        self._app = self._create_app()

        # Configure uvicorn
        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=True,
        )

        self._server = uvicorn.Server(config)

        # Setup asyncio-safe signal handlers for graceful shutdown
        def signal_handler(sig_num):
            observability.observe(
                event_type=observability.SystemEvents.CLEANUP,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "signal": str(sig_num),
                    "formation_id": self.formation.formation_id,
                },
                description=f"Received signal {sig_num}, initiating graceful shutdown",
            )
            self._shutdown_event.set()

        # Use asyncio event loop signal handlers for async safety
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, signal_handler, signal.SIGINT)
            loop.add_signal_handler(signal.SIGTERM, signal_handler, signal.SIGTERM)
        except (NotImplementedError, RuntimeError):
            # Fallback for platforms that don't support asyncio signal handlers
            # Use traditional signal handlers with proper async event handling
            def sync_signal_handler(sig_num, frame):
                observability.observe(
                    event_type=observability.SystemEvents.CLEANUP,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "formation_api_server",
                        "signal": str(sig_num),
                        "formation_id": self.formation.formation_id,
                    },
                    description=f"Received signal {sig_num}, initiating shutdown",
                )
                # Schedule the event setting on the event loop
                try:
                    loop.call_soon_threadsafe(self._shutdown_event.set)
                except RuntimeError:
                    # If event loop is not running, fall back to direct call
                    asyncio.create_task(self._set_shutdown_event())

            signal.signal(signal.SIGINT, sync_signal_handler)
            signal.signal(signal.SIGTERM, sync_signal_handler)

        # Start server
        if block:
            # Run server in blocking mode
            await self._server.serve()
        else:
            # Run server in non-blocking mode
            self._server_task = asyncio.create_task(self._server.serve())

            # Wait a moment to ensure server starts
            await asyncio.sleep(0.5)

            # Check if server started successfully
            if self._server_task.done():
                # Server task completed immediately, likely due to error
                try:
                    await self._server_task
                except Exception as e:
                    raise RuntimeError(f"Failed to start server: {e}")

    async def _set_shutdown_event(self) -> None:
        """Helper method to set shutdown event asynchronously."""
        self._shutdown_event.set()

    async def stop(self) -> None:
        """Stop the Formation server gracefully."""
        if not self._server:
            return

        observability.observe(
            event_type=observability.SystemEvents.CLEANUP,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_api_server",
                "formation_id": self.formation.formation_id,
                "server_url": f"http://{self.host}:{self.port}",
            },
            description="Stopping Formation API server",
        )

        self._shutdown_event.set()

        # Signal uvicorn to shutdown
        self._server.should_exit = True

        # Wait for server task to complete if running
        if self._server_task and not self._server_task.done():
            try:
                await asyncio.wait_for(self._server_task, timeout=30.0)
            except asyncio.TimeoutError:
                observability.observe(
                    event_type=observability.SystemEvents.CLEANUP,
                    level=observability.EventLevel.WARNING,
                    data={
                        "service": "formation_api_server",
                        "formation_id": self.formation.formation_id,
                        "timeout_seconds": 30,
                        "action": "force_cancel",
                    },
                    description="Server shutdown timed out after 30 seconds, forcing cancellation",
                )
                self._server_task.cancel()

        self._server = None
        self._server_task = None

        observability.observe(
            event_type=observability.SystemEvents.CLEANUP,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_api_server",
                "formation_id": self.formation.formation_id,
                "status": "stopped",
            },
            description="Formation API server stopped successfully",
        )

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._server_task is not None and not self._server_task.done()

    @property
    def url(self) -> str:
        """Get the server URL."""
        return f"http://{self.host}:{self.port}"
