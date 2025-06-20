"""
Async Operations Data Types

Core data structures for managing async operations with timeout and cancellation support.
"""

import asyncio
from typing import Any, Dict, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone


class OperationStatus(Enum):
    """Status of an async operation."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass
class TimeoutConfig:
    """Configuration for operation timeouts."""

    # Default timeouts for different operation types
    config_load_timeout: float = 30.0
    secrets_operation_timeout: float = 10.0
    service_startup_timeout: float = 60.0
    overlord_startup_timeout: float = 120.0
    cleanup_timeout: float = 30.0

    # Global timeout settings
    enable_timeouts: bool = True
    default_timeout: float = 60.0
    cancellation_grace_period: float = 5.0  # Time to wait for graceful cancellation


@dataclass
class OperationContext:
    """Context information for an async operation."""

    operation_id: str
    operation_type: str
    description: str
    timeout: float
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: OperationStatus = OperationStatus.PENDING
    result: Optional[Any] = None
    error: Optional[Exception] = None
    cancellation_token: Optional['CancellationToken'] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since operation started."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    @property
    def is_expired(self) -> bool:
        """Check if operation has exceeded its timeout."""
        return self.elapsed_time > self.timeout

    @property
    def time_remaining(self) -> float:
        """Get remaining time before timeout."""
        return max(0, self.timeout - self.elapsed_time)


class CancellationToken:
    """
    Token for cancelling async operations gracefully.

    Provides a mechanism for coordinated cancellation of related operations,
    with support for graceful shutdown and cleanup.
    """

    def __init__(self, grace_period: float = 5.0):
        """
        Initialize cancellation token.

        Args:
            grace_period: Time to wait for graceful cancellation before forcing
        """
        self._cancelled = False
        self._tasks: Set[asyncio.Task] = set()
        self._callbacks: Set[Callable[[], None]] = set()
        self._grace_period = grace_period
        self._cancel_event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        """Check if this token has been cancelled."""
        return self._cancelled

    def cancel(self) -> None:
        """
        Cancel all operations associated with this token.

        Triggers graceful cancellation of all registered tasks and callbacks.
        """
        if self._cancelled:
            return

        self._cancelled = True
        self._cancel_event.set()

        # Execute cancellation callbacks
        for callback in self._callbacks:
            try:
                callback()
            except Exception:
                # Ignore callback errors during cancellation
                pass

        # Cancel all registered tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def register_task(self, task: asyncio.Task) -> None:
        """Register a task to be cancelled with this token."""
        if not self._cancelled:
            self._tasks.add(task)
            # Remove task when it completes
            task.add_done_callback(lambda t: self._tasks.discard(t))

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when cancellation occurs."""
        if not self._cancelled:
            self._callbacks.add(callback)

    def throw_if_cancelled(self) -> None:
        """Raise CancellationError if this token has been cancelled."""
        if self._cancelled:
            raise asyncio.CancelledError("Operation was cancelled")

    async def wait_for_cancellation(self) -> None:
        """Wait until this token is cancelled."""
        await self._cancel_event.wait()


class CancellationError(Exception):
    """Exception raised when an operation is cancelled."""

    def __init__(self, message: str = "Operation was cancelled", operation_id: Optional[str] = None):
        super().__init__(message)
        self.operation_id = operation_id


class OperationTimeoutError(Exception):
    """Exception raised when an operation times out."""

    def __init__(self, message: str, timeout: float, operation_id: Optional[str] = None):
        super().__init__(message)
        self.timeout = timeout
        self.operation_id = operation_id


@dataclass
class AsyncOperationResult:
    """Result of an async operation with timeout/cancellation handling."""

    operation_id: str
    status: OperationStatus
    result: Optional[Any] = None
    error: Optional[Exception] = None
    elapsed_time: float = 0.0
    was_cancelled: bool = False
    was_timeout: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """Check if operation completed successfully."""
        return self.status == OperationStatus.COMPLETED and self.error is None

    @property
    def is_failure(self) -> bool:
        """Check if operation failed."""
        return self.status in [OperationStatus.FAILED, OperationStatus.TIMEOUT, OperationStatus.CANCELLED]
