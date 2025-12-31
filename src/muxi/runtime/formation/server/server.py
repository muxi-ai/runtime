"""
Formation Server Implementation

This module provides the FastAPI-based HTTP server for MUXI formations.
It handles both admin operations (formation management) and client operations
(user interactions) with a dual-key authentication system.
"""

import asyncio
import re
import signal
import time
import threading
from contextlib import asynccontextmanager
from typing import Optional, TYPE_CHECKING, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ...services import observability
from ...utils.version import get_version
from ..initialization import enable_conversation_logging

if TYPE_CHECKING:
    from ..formation import Formation  # noqa: E402


# HTTP status code to error code mapping
STATUS_CODE_TO_ERROR_CODE = {
    400: "INVALID_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "INVALID_PARAMS",
    429: "RATE_LIMITED",
    501: "METHOD_NOT_FOUND",
    503: "SYSTEM_OVERLOAD",
}

# Field suffix patterns for type inference in validation errors
# Used to determine the expected field type based on field name patterns
FIELD_SUFFIX_PATTERNS = {
    "boolean": [".active"],
    "array": [".llm_models", ".mcp_servers", ".knowledge"],
    "object": [".a2a", ".settings"],
    "integer": [".max_tokens", ".timeout_seconds", ".max_retries"],
    "number": [".temperature"],
}


def create_http_exception_handler():
    """Create a reusable HTTP exception handler."""
    from .responses import create_error_response

    async def handler(request, exc):
        # Get request ID if available
        request_id = getattr(request.state, "request_id", None)

        # Get status code and detail from exception
        status_code = getattr(exc, "status_code", 500)
        detail = getattr(exc, "detail", str(exc))

        # Map status codes to error codes using dictionary lookup
        error_code = STATUS_CODE_TO_ERROR_CODE.get(status_code, "INTERNAL_ERROR")

        # Create structured error response
        error_response = create_error_response(
            error_code=error_code,
            message=str(detail),
            request_id=request_id,
        )

        return JSONResponse(
            status_code=status_code,
            content=error_response.model_dump(),
        )

    return handler


class FormationServer:
    """
    HTTP server for exposing formation capabilities via REST API.

    This server provides:
    - Admin endpoints for formation management (add/remove agents, update config)
    - Client endpoints for user interactions (chat, memories, async jobs)
    - MCP endpoint for tool-based access
    - Health and status monitoring
    """

    def __init__(self, formation: "Formation", host: str = "127.0.0.1", port: int = 8271, **kwargs):
        """
        Initialize the Formation server.

        Args:
            formation: The Formation instance to serve
            host: Host to bind to (default: 127.0.0.1 - localhost only)
            port: Port to bind to (default: 8271)
            **kwargs: Additional server configuration
        """
        self.formation = formation
        self.host = host
        self.port = port
        self.config = kwargs

        # Extract access_log setting
        self.access_log = kwargs.get("access_log", False)

        # Server state
        self._app: Optional[FastAPI] = None
        self._server: Optional[uvicorn.Server] = None
        self._server_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._active_connections: set = set()
        self._active_connections_lock = threading.Lock()
        self._shutdown_timeout = 30.0

        # Server metrics
        self._start_time = time.time()
        self._request_count = 0
        self._request_count_lock = threading.Lock()

        # Extract API keys from formation
        self.admin_key = formation._api_keys.get("admin", "")
        self.client_key = formation._api_keys.get("client", "")

        # Log server configuration
        observability.observe(
            event_type=observability.ServerEvents.SERVER_INITIALIZING,
            level=observability.EventLevel.INFO,
            data={
                "service": "formation_server",
                "host": self.host,
                "port": self.port,
                "has_admin_key": bool(self.admin_key),
                "has_client_key": bool(self.client_key),
                "formation_id": formation.formation_id,
                "access_log": self.access_log,
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
        # Startup events - these won't emit JSONL until server is confirmed ready
        # (enable_conversation_logging is called after "API Worker: listening")
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
            # Convert to InitEventFormatter
            print(observability.InitEventFormatter.format_warn(
                "API keys auto-generated (NOT for production)"
            ))

            # Still print to console for development visibility
            print("\n" + "=" * 60)
            print("⚠️  AUTO-GENERATED API KEYS - DEVELOPMENT ONLY")
            print("=" * 60)
            print("🔒 The following API keys were automatically generated")
            print("   because none were provided in your formation configuration.")
            print()
            print("⚠️  WARNING: This is NOT recommended for production use!")
            print("   Please configure proper API keys in your formation.afs:")
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
                event_type=observability.ServerEvents.API_KEYS_LOADED,
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
            if self.admin_key and self.client_key:
                print(observability.InitEventFormatter.format_info("API keys loaded from configuration"))

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

        # Add exception handlers to ensure proper envelope format
        from fastapi.exceptions import RequestValidationError
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from .responses import create_error_response

        # Create specialized handler for validation errors
        def _infer_field_type(error_type: str, loc_string: str) -> Tuple[str, str]:
            """
            Infer field type and error kind from error type and location string.

            Args:
                error_type: The error type from validation
                loc_string: The field location as a dot-separated string

            Returns:
                Tuple of (field_type, error_kind)
            """
            # Extract the core error type from FastAPI/Pydantic format
            # Handles multi-part error types:
            # - "value_error.missing" -> "missing"
            # - "type_error.str" -> "str"
            # - "string_too_short" -> "string_too_short" (kept as-is)
            # - "value_error.extra.forbidden" -> "extra.forbidden" (last two parts)

            # For error types with multiple dots, we may want the last two parts
            # to preserve context (e.g., "extra.forbidden" instead of just "forbidden")
            parts = error_type.split(".")
            if len(parts) > 2:
                # For multi-level errors, keep the last two parts for better context
                core_error_type = ".".join(parts[-2:])
            elif len(parts) == 2:
                # Standard format: take the last part
                core_error_type = parts[-1]
            else:
                # No dots: use as-is
                core_error_type = error_type

            # Error type to field type and error kind mapping
            # Updated to handle actual FastAPI/Pydantic error codes
            ERROR_TYPE_MAPPING = {
                # Value errors
                "missing": ("string", "missing"),  # value_error.missing
                "json_invalid": ("string", "invalid_json"),  # value_error.json_invalid
                "extra": ("string", "extra_field"),  # value_error.extra

                # Multi-part error types (for better context)
                "extra.forbidden": ("string", "extra_field"),  # value_error.extra.forbidden
                "missing.required": ("string", "missing"),  # value_error.missing.required

                # Type errors (from type_error.*)
                "str": ("string", "wrong_type"),  # type_error.str
                "string": ("string", "wrong_type"),  # alternative format
                "integer": ("integer", "wrong_type"),  # type_error.integer
                "int": ("integer", "wrong_type"),  # type_error.int
                "bool": ("boolean", "wrong_type"),  # type_error.bool
                "boolean": ("boolean", "wrong_type"),  # alternative format
                "list": ("array", "wrong_type"),  # type_error.list
                "array": ("array", "wrong_type"),  # alternative format
                "dict": ("object", "wrong_type"),  # type_error.dict
                "object": ("object", "wrong_type"),  # alternative format
                "float": ("number", "wrong_type"),  # type_error.float
                "number": ("number", "wrong_type"),  # alternative format

                # Validation errors
                "too_short": ("string", "too_short"),
                "too_long": ("string", "too_long"),
                "regex": ("string", "invalid_format"),
                "string_too_short": ("string", "too_short"),  # Alternative format
                "string_too_long": ("string", "too_long"),  # Alternative format
            }

            # Check if core error type is in the mapping
            if core_error_type in ERROR_TYPE_MAPPING:
                field_type, error_kind = ERROR_TYPE_MAPPING[core_error_type]
            else:
                # Fall back to pattern matching on full error type
                error_kind = "invalid"  # default
                if "json" in error_type:
                    error_kind = "invalid_json"
                elif "missing" in error_type:
                    error_kind = "missing"
                elif "type" in error_type:
                    error_kind = "wrong_type"
                elif "too_short" in error_type or "min_length" in error_type:
                    error_kind = "too_short"
                elif "too_long" in error_type or "max_length" in error_type:
                    error_kind = "too_long"
                elif "regex" in error_type or "pattern" in error_type:
                    error_kind = "invalid_format"
                elif "extra" in error_type:
                    error_kind = "extra_field"

                # Default field type
                field_type = "string"

            # Remove array indices from location string for accurate suffix matching
            # e.g., "agents[0].settings" -> "agents.settings"
            normalized_loc = re.sub(r'\[\d+\]', '', loc_string)

            # Override field type based on location string suffix
            # This is important for 'missing' errors where we need to know the expected type
            for expected_type, suffixes in FIELD_SUFFIX_PATTERNS.items():
                if any(normalized_loc.endswith(suffix) for suffix in suffixes):
                    field_type = expected_type
                    break

            return field_type, error_kind

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request, exc: RequestValidationError):
            """Handle FastAPI validation errors with detailed error information."""
            # Get request ID if available
            request_id = getattr(request.state, "request_id", None)

            # Extract detailed validation errors
            validation_errors = []
            for error in exc.errors():
                # Convert location array to dot notation
                loc_parts = list(error["loc"])
                # Remove "body" prefix if present (it's redundant for API users)
                if loc_parts and loc_parts[0] == "body":
                    loc_parts = loc_parts[1:]
                loc_string = ".".join(str(part) for part in loc_parts)

                # Use the new method to infer field type and error kind
                error_type = error["type"]
                field_type, error_kind = _infer_field_type(error_type, loc_string)

                validation_errors.append(
                    {
                        "field": loc_string,  # Dot notation location
                        "msg": error["msg"],  # Error message
                        "type": field_type,  # Expected data type
                        "error": error_kind,  # Specific error
                    }
                )

            # Create detailed error message
            error_message = f"Validation failed: {len(validation_errors)} error(s)"

            # Create structured error response with validation details
            error_response = create_error_response(
                error_code="INVALID_PARAMS",
                message=error_message,
                request_id=request_id,
                error_data={"validation_errors": validation_errors},
            )

            return JSONResponse(
                status_code=422,
                content=error_response.model_dump(),
            )

        # Register the same handler for both FastAPI and Starlette HTTP exceptions
        http_handler = create_http_exception_handler()
        app.add_exception_handler(HTTPException, http_handler)
        app.add_exception_handler(StarletteHTTPException, http_handler)

        # Register routers
        self._register_health_routes(app)
        self._register_admin_routes(app)
        self._register_client_routes(app)

        return app

    def _register_health_routes(self, app: FastAPI) -> None:
        """Register health and status endpoints."""
        from .routes.health import router, root_status

        # Register root status endpoint at / without prefix
        app.add_api_route("/", endpoint=root_status, methods=["GET"], include_in_schema=False)

        # Register /v1 status endpoint (same as root)
        app.add_api_route("/v1", endpoint=root_status, methods=["GET"], include_in_schema=False)

        # Health routes are mounted under /v1 to match OpenAPI spec
        app.include_router(router, prefix="/v1", tags=["health"])

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
            logs,
            memory,
            scheduler,
            a2a,
            audit,
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
            logs.router,
            memory.router,
            async_router,
            # scheduler.router moved to dual_auth_routers (GET /scheduler/jobs needs both keys)
            a2a.router,
            audit.router,
        ]

        for router in admin_routers:
            app.include_router(router, prefix="/v1", dependencies=[Depends(admin_auth)])

    def _register_client_routes(self, app: FastAPI) -> None:
        """Register client interaction endpoints."""
        from .auth import ClientKeyAuth, DualKeyAuth
        from fastapi import Depends

        # Import all client route modules
        from .routes.client import chat, credentials, events, requests, memory, triggers, users, sessions, sops
        # Import scheduler from admin routes (has dual-auth endpoint GET /scheduler/jobs)
        from .routes.admin import scheduler

        # Create auth dependencies
        client_auth = ClientKeyAuth(self.client_key)
        dual_auth = DualKeyAuth(self.admin_key, self.client_key)

        # Routers that accept only ClientKey
        client_only_routers = [
            chat.router,
            triggers.router,
            users.router,
            sessions.router,
            sops.router,
        ]

        # Routers that accept both ClientKey and AdminKey
        dual_auth_routers = [
            credentials.router,
            events.router,
            requests.router,
            memory.router,
            scheduler.router,  # GET /scheduler/jobs needs both keys
        ]

        for router in client_only_routers:
            app.include_router(router, prefix="/v1", dependencies=[Depends(client_auth)])

        for router in dual_auth_routers:
            app.include_router(router, prefix="/v1", dependencies=[Depends(dual_auth)])

    async def start(self, block: bool = True, install_signal_handlers: bool = True) -> None:
        """
        Start the Formation server.

        Args:
            block: Whether to block until server stops (default: True)
            install_signal_handlers: Whether to install signal handlers (default: True)
                                   Set to False if parent process handles signals
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
            log_level="warning",  # Suppress uvicorn startup logs, use MUXI's format
            access_log=self.access_log,
        )

        self._server = uvicorn.Server(config)

        # Only install signal handlers if requested
        if install_signal_handlers:
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
                        # If event loop is not running, set directly
                        self._shutdown_event.set()

                signal.signal(signal.SIGINT, sync_signal_handler)
                signal.signal(signal.SIGTERM, sync_signal_handler)

        # Start server with proper initialization
        # Always wait for server to be ready before returning (fail fast)
        self._server_task = asyncio.create_task(self._server.serve())

        # Wait for server to be ready (with timeout)
        await self._wait_for_server_ready(timeout=10.0)

        # If blocking mode, wait for server to complete
        if block:
            await self._server_task

    async def _wait_for_server_ready(self, timeout: float = 10.0) -> None:
        """
        Wait for the server to be ready to accept connections.

        Shows Linux-style init events during startup.
        Implements fail-fast philosophy - raises immediately on errors.

        Args:
            timeout: Maximum time to wait for server to be ready (seconds)

        Raises:
            RuntimeError: If server fails to start within timeout
            Exception: If server task encounters an error during startup
        """
        import socket
        from ...datatypes.observability import InitEventFormatter

        # Show server binding event
        print(InitEventFormatter.format_info(
            f"API Worker: binding to {self.host}:{self.port}",
            None
        ))

        start_time = asyncio.get_event_loop().time()
        last_error = None

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # Check if server task failed
            if self._server_task.done():
                try:
                    await self._server_task
                    # Task completed without error but server isn't ready?
                    raise RuntimeError("Server task completed unexpectedly")
                except Exception as e:
                    print(InitEventFormatter.format_fail(
                        "API Worker failed to start",
                        str(e)
                    ))
                    raise RuntimeError(f"Server startup failed: {e}") from e

            # Try to connect to the port
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.1)
                    # Try to connect
                    result = sock.connect_ex((self.host if self.host != "0.0.0.0" else "127.0.0.1", self.port))
                    if result == 0:
                        # Connection successful - server is ready!
                        print(InitEventFormatter.format_ok(
                            f"API Worker: listening on {self.host}:{self.port}",
                            f"http://{self.host if self.host != '0.0.0.0' else '127.0.0.1'}:{self.port}"
                        ))
                        # Enable observability logging now that server is confirmed ready
                        enable_conversation_logging(self.formation)
                        return
            except Exception as e:
                last_error = e

            # Wait a bit before retrying
            await asyncio.sleep(0.1)

        # Timeout reached
        error_msg = f"Server failed to start within {timeout}s"
        if last_error:
            error_msg += f": {last_error}"

        print(InitEventFormatter.format_fail(
            "API Worker startup timeout",
            error_msg
        ))

        # Try to cancel the server task
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass

        raise RuntimeError(error_msg)

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
