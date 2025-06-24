"""
Async Operations Data Types

Core data structures for managing async operations with timeout and cancellation support.
"""

import asyncio
from typing import Any, Optional, Callable, Set
from enum import Enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, ConfigDict

from .type_definitions import OperationMetadata


class OperationStatus(Enum):
    """Status of an async operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    FAILED = "failed"


class TimeoutConfig(BaseModel):
    """Configuration for operation timeouts."""

    # Default timeouts for different operation types
    config_load_timeout: float = Field(
        default=30.0, ge=0.1, le=300.0, description="Timeout for loading configuration"
    )
    secrets_operation_timeout: float = Field(
        default=10.0, ge=0.1, le=60.0, description="Timeout for secrets operations"
    )
    service_startup_timeout: float = Field(
        default=60.0, ge=1.0, le=600.0, description="Timeout for service startup"
    )
    overlord_startup_timeout: float = Field(
        default=120.0, ge=1.0, le=1200.0, description="Timeout for overlord startup"
    )
    cleanup_timeout: float = Field(
        default=30.0, ge=0.1, le=300.0, description="Timeout for cleanup operations"
    )

    # Global timeout settings
    enable_timeouts: bool = Field(default=True, description="Enable timeout enforcement globally")
    default_timeout: float = Field(
        default=60.0, ge=0.1, le=600.0, description="Default timeout for unspecified operations"
    )
    cancellation_grace_period: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Time to wait for graceful cancellation before forcing",
    )

    @field_validator("default_timeout")
    @classmethod
    def validate_default_timeout(cls, v, info):
        """Ensure default timeout is reasonable."""
        if v > 600:
            raise ValueError("Default timeout should not exceed 10 minutes")
        return v

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class OperationContext(BaseModel):
    """Context information for an async operation."""

    operation_id: str = Field(..., min_length=1, description="Unique operation identifier")
    operation_type: str = Field(..., min_length=1, description="Type of operation")
    description: str = Field(..., description="Human-readable operation description")
    timeout: float = Field(..., ge=0.1, le=3600.0, description="Operation timeout in seconds")
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Operation start time",
    )
    status: OperationStatus = Field(
        default=OperationStatus.PENDING, description="Current operation status"
    )
    result: Optional[Any] = Field(default=None, description="Operation result when completed")
    error: Optional[str] = Field(default=None, description="Error message if operation failed")
    cancellation_token: Optional[Any] = Field(
        default=None, description="Token for operation cancellation", exclude=True
    )
    metadata: OperationMetadata = Field(
        default_factory=dict, description="Additional operation metadata"
    )

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

    @field_validator("operation_id", "operation_type")
    @classmethod
    def validate_non_empty(cls, v):
        """Ensure string fields are not empty."""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v):
        """Ensure timeout is within reasonable bounds."""
        if v <= 0:
            raise ValueError("Timeout must be positive")
        if v > 3600:
            raise ValueError("Timeout cannot exceed 1 hour")
        return v

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


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

    def __init__(
        self, message: str = "Operation was cancelled", operation_id: Optional[str] = None
    ):
        super().__init__(message)
        self.operation_id = operation_id


class OperationTimeoutError(Exception):
    """Exception raised when an operation times out."""

    def __init__(self, message: str, timeout: float, operation_id: Optional[str] = None):
        super().__init__(message)
        self.timeout = timeout
        self.operation_id = operation_id


class AsyncOperationResult(BaseModel):
    """Result of an async operation with timeout/cancellation handling."""

    operation_id: str = Field(..., min_length=1, description="Unique operation identifier")
    status: OperationStatus = Field(..., description="Final operation status")
    result: Optional[Any] = Field(default=None, description="Operation result if successful")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    elapsed_time: float = Field(default=0.0, ge=0.0, description="Total operation time in seconds")
    was_cancelled: bool = Field(default=False, description="Whether operation was cancelled")
    was_timeout: bool = Field(default=False, description="Whether operation timed out")
    metadata: OperationMetadata = Field(
        default_factory=dict, description="Additional result metadata"
    )

    @property
    def is_success(self) -> bool:
        """Check if operation completed successfully."""
        # Handle both enum and string values due to Pydantic serialization
        status_value = (
            self.status.value if isinstance(self.status, OperationStatus) else self.status
        )
        return status_value == "completed" and self.error is None

    @property
    def is_failure(self) -> bool:
        """Check if operation failed."""
        return self.status in [
            OperationStatus.FAILED,
            OperationStatus.TIMEOUT,
            OperationStatus.CANCELLED,
        ]

    @field_validator("elapsed_time")
    @classmethod
    def validate_elapsed_time(cls, v):
        """Ensure elapsed time is non-negative."""
        if v < 0:
            raise ValueError("Elapsed time cannot be negative")
        return v

    @field_validator("error")
    @classmethod
    def validate_error_consistency(cls, v, info):
        """Ensure error is present for failure statuses."""
        if info.data.get("status") in [
            OperationStatus.FAILED,
            OperationStatus.TIMEOUT,
            OperationStatus.CANCELLED,
        ]:
            if not v:
                raise ValueError("Error message required for failure status")
        return v

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )
