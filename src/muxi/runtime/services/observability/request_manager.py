"""
MUXI Observability Request Manager

This module contains the RequestContextManager class for tracking
request lifecycles and automatic cleanup.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict, Optional

from ...utils.id_generator import generate_nanoid as generate_id
from .context import _current_request_context
from .types import RequestContext


class RequestContextManager:
    """In-memory request tracking with automatic cleanup."""

    def __init__(self, cleanup_interval: int = 300):  # 5 minutes
        self._contexts: Dict[str, RequestContext] = {}
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start_cleanup(self) -> None:
        """Start the automatic cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        """Stop the automatic cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of old request contexts."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_old_contexts()
            except asyncio.CancelledError:
                break
            except Exception:
                # Silent cleanup failures to avoid disrupting main flow
                pass

    async def _cleanup_old_contexts(self) -> None:
        """Remove contexts older than 1 hour."""
        cutoff_time = time.time() * 1000 - (60 * 60 * 1000)  # 1 hour ago

        async with self._lock:
            to_remove = [
                req_id for req_id, ctx in self._contexts.items() if ctx.started < cutoff_time
            ]
            for req_id in to_remove:
                del self._contexts[req_id]

    @asynccontextmanager
    async def track_request(
        self,
        request_id: Optional[str] = None,
        formation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Context manager for request tracking with automatic context propagation."""
        if request_id is None:
            request_id = generate_id()

        context = RequestContext(
            id=request_id, formation_id=formation_id, user_id=user_id, session_id=session_id
        )

        # Set the context variable when entering the context
        token = _current_request_context.set(context)

        async with self._lock:
            self._contexts[request_id] = context

        try:
            yield context
            context.complete()
        except Exception:
            context.fail()
            raise
        finally:
            # Reset the context variable when exiting
            _current_request_context.reset(token)
            # Don't remove immediately - let cleanup handle it

    async def get_context(self, request_id: str) -> Optional[RequestContext]:
        """Get request context by ID."""
        async with self._lock:
            return self._contexts.get(request_id)

    async def update_context(self, request_id: str, **updates) -> None:
        """Update request context with new information."""
        async with self._lock:
            if context := self._contexts.get(request_id):
                for key, value in updates.items():
                    if hasattr(context, key):
                        setattr(context, key, value)
