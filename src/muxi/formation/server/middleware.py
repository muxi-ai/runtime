"""
Middleware for the Formation API server.

This module provides middleware for request/response processing,
including error handling, logging, and request tracking.
"""

import asyncio
import time
import traceback
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ...services import observability
from ...utils.id_generator import generate_request_id
from .responses import create_error_response
from .utils import get_header_case_insensitive, has_header_case_insensitive


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to catch exceptions and convert them to structured error responses.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and handle any exceptions.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint

        Returns:
            Response with structured error format if exception occurs
        """
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Get request ID if available
            request_id = getattr(request.state, "request_id", None)

            # Determine error code based on exception type
            error_code = "INTERNAL_ERROR"
            status_code = 500

            # Handle FastAPI HTTPException
            if hasattr(e, "status_code") and hasattr(e, "detail"):
                status_code = e.status_code
                if status_code == 400:
                    error_code = "INVALID_REQUEST"
                elif status_code == 401:
                    error_code = "UNAUTHORIZED"
                elif status_code == 403:
                    error_code = "FORBIDDEN"
                elif status_code == 404:
                    error_code = "RESOURCE_NOT_FOUND"
                elif status_code == 422:
                    error_code = "INVALID_PARAMS"
                elif status_code == 429:
                    error_code = "RATE_LIMITED"
                elif status_code == 501:
                    error_code = "METHOD_NOT_FOUND"
                elif status_code == 503:
                    error_code = "SYSTEM_OVERLOAD"

                message = str(e.detail) if hasattr(e, "detail") else str(e)
            else:
                # For other exceptions, try to infer from the exception type
                message = str(e)

            # Handle traceback safely to avoid scoping issues
            trace_info = None
            if getattr(request.app, "debug", False):
                trace_info = traceback.format_exc()

            # Create structured error response
            error_response = create_error_response(
                error_code=error_code,
                message=message,
                trace=trace_info,
                request_id=request_id,
            )

            # Log the error
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation_api_server",
                    "error_code": error_code,
                    "status_code": status_code,
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "exception_type": type(e).__name__,
                },
                description=f"API request failed: {message}",
            )

            return JSONResponse(
                status_code=status_code,
                content=error_response.model_dump(),
            )


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track requests with IDs and logging.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add request tracking and logging.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint

        Returns:
            Response with request ID header
        """
        start_time = time.time()

        # Generate request ID for non-chat endpoints
        # Chat endpoints will use the request_id from the body
        if request.url.path != "/v1/chat" and request.url.path != "/chat":
            request_id = generate_request_id()
        else:
            # For chat, we'll get it from the body later
            request_id = None

        # Store request ID in state for access by endpoints
        request.state.request_id = request_id

        # Log request
        if request_id:
            observability.observe(
                event_type=observability.ServerEvents.REQUEST_RECEIVED,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_host": request.client.host if request.client else None,
                },
                description=f"API request received: {request.method} {request.url.path}",
            )

        # Process request
        response = await call_next(request)

        # Calculate processing time
        processing_time = time.time() - start_time

        # Increment request counter (thread-safe)
        if hasattr(request.app.state, 'formation'):
            server = getattr(request.app.state.formation, '_server', None)
            if server and hasattr(server, '_request_count_lock'):
                with server._request_count_lock:
                    server._request_count += 1

        # Log response
        if request_id:
            observability.observe(
                event_type=observability.ServerEvents.REQUEST_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "processing_time": processing_time,
                },
                description=f"API request completed: {response.status_code}",
            )

        return response


class APILoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware specifically for API request/response logging.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log API-specific events.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint

        Returns:
            Response
        """
        # Extract API key info (without exposing the actual key)
        has_admin_key = has_header_case_insensitive(request.headers, "X-Muxi-Admin-Key")
        has_client_key = has_header_case_insensitive(request.headers, "X-Muxi-Client-Key")

        # Log API-specific info
        observability.observe(
            event_type=observability.APIEvents.API_REQUEST,
            level=observability.EventLevel.DEBUG,
            data={
                "service": "formation_api_server",
                "method": request.method,
                "path": request.url.path,
                "has_admin_key": has_admin_key,
                "has_client_key": has_client_key,
                "content_type": get_header_case_insensitive(request.headers, "content-type"),
                "accept": get_header_case_insensitive(request.headers, "accept"),
                "user_agent": get_header_case_insensitive(request.headers, "user-agent"),
            },
            description="Formation API request details",
        )

        response = await call_next(request)

        return response


class ConnectionTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track active connections for graceful shutdown.
    """

    def __init__(self, app, server_instance):
        super().__init__(app)
        self.server_instance = server_instance

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Track connection lifecycle for graceful shutdown.

        Args:
            request: The incoming request
            call_next: The next middleware or endpoint

        Returns:
            Response
        """
        # Create connection tracking object
        # connection_id = id(request)
        connection_task = asyncio.current_task()

        # Add to active connections (thread-safe)
        if hasattr(self.server_instance, '_active_connections_lock'):
            with self.server_instance._active_connections_lock:
                self.server_instance._active_connections.add(connection_task)
        else:
            self.server_instance._active_connections.add(connection_task)

        try:
            response = await call_next(request)
            return response
        finally:
            # Remove from active connections when request completes (thread-safe)
            if hasattr(self.server_instance, '_active_connections_lock'):
                with self.server_instance._active_connections_lock:
                    self.server_instance._active_connections.discard(connection_task)
            else:
                self.server_instance._active_connections.discard(connection_task)
