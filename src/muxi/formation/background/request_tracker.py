"""
Request tracking for async request-response patterns.

This module provides in-memory tracking of async requests with
thread-safe operations.
"""

import asyncio
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
        return getattr(self, 'created_at', None) or getattr(self, 'start_time', None)


class RequestTracker:
    """In-memory tracking of async requests with thread-safe operations."""

    def __init__(self):
        self._requests: Dict[str, RequestState] = {}
        self._cancelled: Set[str] = set()  # For cooperative cancellation
        self._lock = asyncio.Lock()

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

            if status in (RequestStatus.COMPLETED, RequestStatus.FAILED):
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
