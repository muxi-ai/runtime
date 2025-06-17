"""
Request tracking for async request-response patterns.

This module provides in-memory tracking of async requests with
thread-safe operations.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class RequestStatus(Enum):
    """Request status enumeration."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
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

    @property
    def processing_time(self) -> Optional[float]:
        """Calculate processing time if request is completed."""
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None


class RequestTracker:
    """In-memory tracking of async requests with thread-safe operations."""

    def __init__(self):
        self._requests: Dict[str, RequestState] = {}
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

    async def remove_request(self, request_id: str) -> bool:
        """
        Remove a request from tracking.

        Args:
            request_id: Unique identifier for the request

        Returns:
            True if request was found and removed, False otherwise
        """
        async with self._lock:
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

    async def cleanup_completed_requests(self, max_age_seconds: float = 3600) -> int:
        """
        Clean up completed requests older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age in seconds for completed requests

        Returns:
            Number of requests cleaned up
        """
        current_time = time.time()
        removed_count = 0

        async with self._lock:
            to_remove = []
            for request_id, request_state in self._requests.items():
                if (
                    request_state.status in (RequestStatus.COMPLETED, RequestStatus.FAILED)
                    and request_state.end_time
                    and (current_time - request_state.end_time) > max_age_seconds
                ):
                    to_remove.append(request_id)

            for request_id in to_remove:
                del self._requests[request_id]
                removed_count += 1

        return removed_count

    async def get_request_count(self) -> int:
        """
        Get total number of tracked requests.

        Returns:
            Number of currently tracked requests
        """
        async with self._lock:
            return len(self._requests)
