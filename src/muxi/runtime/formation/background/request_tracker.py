"""
Request tracking for async request-response patterns.

This module provides in-memory tracking of async requests with
thread-safe operations. Completed/failed requests are retained
for a configurable TTL (default 5 minutes) so clients can poll
for results after completion.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set


class RequestStatus(Enum):
    """Request status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_CLARIFICATION = "awaiting_clarification"


@dataclass
class RequestState:
    """Represents the state of an async request."""

    id: str
    status: RequestStatus
    start_time: float
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    end_time: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    webhook_url: Optional[str] = None
    estimated_completion: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    # Clarification fields
    clarification_question: Optional[str] = None
    clarification_request_id: Optional[str] = None
    original_message: Optional[str] = None
    # Lifecycle management fields
    progress: Optional[str] = None  # Optional progress string (e.g., "3/5 tasks")
    task_ref: Optional[asyncio.Task] = None  # Reference to asyncio task for cancellation

    @property
    def processing_time(self) -> Optional[float]:
        """Calculate processing time if request is completed."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None

    def get_created_timestamp(self) -> Optional[float]:
        """
        Get the creation timestamp for this request.

        Returns created_at if available, otherwise falls back to start_time.
        This provides a canonical accessor for timestamp resolution.

        Returns:
            Timestamp as float, or None if neither field exists
        """
        return getattr(self, "created_at", None) or getattr(self, "start_time", None)


_TERMINAL_STATUSES = frozenset(
    {RequestStatus.COMPLETED, RequestStatus.FAILED, RequestStatus.CANCELLED}
)

# Statuses a request can still be moved out of by the producer that owns it.
# Used by ``mark_completed_if_active`` so a request that already reached a
# terminal state keeps the status it has.
_ACTIVE_STATUSES = frozenset(
    {RequestStatus.PENDING, RequestStatus.PROCESSING, RequestStatus.RUNNING}
)

DEFAULT_COMPLETED_TTL_SECONDS = 300  # 5 minutes
DEFAULT_STALE_REQUEST_TIMEOUT = 600  # 10 minutes -- matches StreamingManager.SUBSCRIBE_TIMEOUT


class RequestTracker:
    """In-memory tracking of async requests with thread-safe operations.

    Completed/failed/cancelled requests are retained for ``completed_ttl``
    seconds so that clients can poll for results after the request finishes.
    A background cleanup task purges expired terminal requests automatically.
    """

    def __init__(
        self,
        completed_ttl: float = DEFAULT_COMPLETED_TTL_SECONDS,
        stale_timeout: float = DEFAULT_STALE_REQUEST_TIMEOUT,
    ):
        self._requests: Dict[str, RequestState] = {}
        self._cancelled: Set[str] = set()  # For cooperative cancellation
        self._lock = asyncio.Lock()
        self.completed_ttl = completed_ttl
        self.stale_timeout = stale_timeout
        self._cleanup_task: Optional[asyncio.Task] = None

    async def track_request(self, request_id: str, initial_state: RequestState) -> None:
        """
        Start tracking a request.

        Args:
            request_id: Unique identifier for the request
            initial_state: Initial request state to track
        """
        async with self._lock:
            self._requests[request_id] = initial_state

    async def update_request(
        self,
        request_id: str,
        status: RequestStatus,
        result: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update request status and result.

        Args:
            request_id: Unique identifier for the request
            status: New status to set
            result: Result data (if completed successfully)
            error: Error message (if failed)

        Returns:
            True if request was found and updated, False otherwise
        """
        async with self._lock:
            if request_id not in self._requests:
                return False

            request_state = self._requests[request_id]
            request_state.status = status

            if result is not None:
                request_state.result = result

            if error is not None:
                request_state.error = error

            if status in _TERMINAL_STATUSES and request_state.end_time is None:
                request_state.end_time = time.time()

            return True

    async def mark_completed_if_active(self, request_id: str, result: Any = None) -> bool:
        """
        Transition an in-flight request to COMPLETED.

        Compare-and-set against the active statuses, so a request that already
        reached a terminal state (cancelled on client disconnect, failed, or
        completed by the async background path) keeps the status it has. This
        is what lets a finished chat turn record itself without racing the
        disconnect handler.

        ``end_time`` is stamped like any other terminal transition, so the
        entry is purged by ``cleanup_expired`` once ``completed_ttl`` elapses.

        Args:
            request_id: Unique identifier for the request
            result: Result data to store alongside the COMPLETED status

        Returns:
            True if the request was found, still active, and transitioned
        """
        async with self._lock:
            request_state = self._requests.get(request_id)
            if request_state is None or request_state.status not in _ACTIVE_STATUSES:
                return False

            request_state.status = RequestStatus.COMPLETED

            if result is not None:
                request_state.result = result

            if request_state.end_time is None:
                request_state.end_time = time.time()

            return True

    async def get_request(self, request_id: str) -> Optional[RequestState]:
        """
        Get current request state.

        Args:
            request_id: Unique identifier for the request

        Returns:
            RequestState if found, None otherwise
        """
        async with self._lock:
            return self._requests.get(request_id)

    async def mark_cancelled(self, request_id: str) -> None:
        """
        Mark request as cancelled for cooperative cancellation.

        This adds the request_id to a set that processing checkpoints
        will check. When a checkpoint detects cancellation, it will
        raise RequestCancelledException.

        Args:
            request_id: Unique identifier for the request to cancel
        """
        async with self._lock:
            self._cancelled.add(request_id)

    def is_cancelled(self, request_id: str) -> bool:
        """
        Check if request is marked as cancelled.

        This is intentionally synchronous (no lock) for use in
        the cancellable decorator without blocking.

        Args:
            request_id: Unique identifier for the request

        Returns:
            True if request is marked as cancelled
        """
        return request_id in self._cancelled

    async def clear_cancelled(self, request_id: str) -> None:
        """
        Remove request from cancelled set.

        Called when cancellation has been processed (exception raised).

        Args:
            request_id: Unique identifier for the request
        """
        async with self._lock:
            self._cancelled.discard(request_id)

    async def remove_request(self, request_id: str) -> bool:
        """
        Remove a request from tracking.

        Args:
            request_id: Unique identifier for the request

        Returns:
            True if request was found and removed, False otherwise
        """
        async with self._lock:
            self._cancelled.discard(request_id)  # Cleanup cancelled set too
            if request_id in self._requests:
                del self._requests[request_id]
                return True
            return False

    async def get_all_requests(self) -> Dict[str, RequestState]:
        """
        Get all tracked requests (copy).

        Returns:
            Dictionary of all current request states
        """
        async with self._lock:
            return dict(self._requests)

    async def get_request_count(self) -> int:
        """
        Get total number of tracked requests.

        Returns:
            Number of currently tracked requests
        """
        async with self._lock:
            return len(self._requests)

    async def cleanup_expired(self) -> int:
        """
        Remove terminal requests whose TTL has expired and force-fail
        requests stuck in PROCESSING longer than ``stale_timeout``.

        Returns:
            Number of requests purged or reaped
        """
        now = time.time()
        purged = 0
        async with self._lock:
            # Purge terminal requests past their TTL
            expired_ids = [
                req_id
                for req_id, state in self._requests.items()
                if state.status in _TERMINAL_STATUSES
                and state.end_time is not None
                and (now - state.end_time) > self.completed_ttl
            ]
            for req_id in expired_ids:
                del self._requests[req_id]
                self._cancelled.discard(req_id)
                purged += 1

            # Reap stale processing requests (e.g. broken-pipe orphans)
            _active = frozenset({RequestStatus.PROCESSING, RequestStatus.RUNNING})
            stale_ids = [
                req_id
                for req_id, state in self._requests.items()
                if state.status in _active and (now - state.start_time) > self.stale_timeout
            ]
            for req_id in stale_ids:
                state = self._requests[req_id]
                state.status = RequestStatus.FAILED
                state.error = "Request timed out (stale request reaper)"
                state.end_time = now
                purged += 1
                logging.getLogger(__name__).warning(
                    "Reaped stale request %s (stuck in %s for %.0fs)",
                    req_id,
                    "PROCESSING",
                    now - state.start_time,
                )

        return purged

    def start_cleanup_loop(self, interval: float = 60.0) -> None:
        """Start a background task that periodically purges expired requests."""
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return

        async def _loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.cleanup_expired()
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "RequestTracker cleanup_expired raised: %s", exc, exc_info=True
                    )

        self._cleanup_task = asyncio.create_task(_loop())

    async def stop_cleanup_loop(self) -> None:
        """Cancel the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
