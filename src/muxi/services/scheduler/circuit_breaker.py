"""
Circuit breaker pattern for LLM calls in the scheduler.

This module provides a circuit breaker to prevent cascading failures
when LLM services are experiencing issues.
"""

import time
import asyncio
from typing import Callable, Optional, TypeVar
from enum import Enum

from ...services import observability


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


T = TypeVar("T")


class LLMCircuitBreaker:
    """
    Circuit breaker for LLM calls to prevent cascade failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation, calls go through
    - OPEN: Too many failures, calls are rejected
    - HALF_OPEN: Testing if the service has recovered

    This helps prevent overwhelming a failing LLM service and provides
    graceful degradation for the scheduler.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        half_open_timeout: float = 30.0,
    ):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes in half-open before closing
            timeout: Seconds before attempting to close from open state
            half_open_timeout: Timeout for calls in half-open state
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.half_open_timeout = half_open_timeout

        # State tracking
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()

        # Statistics
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "rejected_calls": 0,
            "state_changes": 0,
        }

    def _change_state(self, new_state: CircuitState) -> None:
        """
        Change circuit breaker state.

        Args:
            new_state: New state to transition to
        """
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.last_state_change = time.time()
            self._stats["state_changes"] += 1

            # Reset counters on state change
            if new_state == CircuitState.CLOSED:
                self.failure_count = 0
                self.success_count = 0

            observability.observe(
                event_type=observability.SystemEvents.SCHEDULER_CIRCUIT_BREAKER_STATE_CHANGE,
                level=observability.EventLevel.INFO,
                data={
                    "old_state": old_state.value,
                    "new_state": new_state.value,
                    "failure_count": self.failure_count,
                    "success_count": self.success_count,
                },
                description=f"Circuit breaker state changed from {old_state.value} to {new_state.value}",
            )

    def _should_attempt_reset(self) -> bool:
        """
        Check if we should attempt to reset from open state.

        Returns:
            True if enough time has passed to try half-open
        """
        return (
            self.state == CircuitState.OPEN
            and self.last_failure_time is not None
            and time.time() - self.last_failure_time >= self.timeout
        )

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Call function with circuit breaker protection.

        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Any exception from func
        """
        self._stats["total_calls"] += 1

        # Check if we should transition from OPEN to HALF_OPEN
        if self._should_attempt_reset():
            self._change_state(CircuitState.HALF_OPEN)

        # Reject calls if circuit is open
        if self.state == CircuitState.OPEN:
            self._stats["rejected_calls"] += 1
            retry_time = max(0, self.timeout - (time.time() - self.last_failure_time))
            raise CircuitBreakerError(
                f"Circuit breaker is OPEN. Service marked as unavailable. "
                f"Will retry in {retry_time:.1f} seconds."
            )

        # Apply timeout in half-open state
        timeout_duration = self.half_open_timeout if self.state == CircuitState.HALF_OPEN else None

        try:
            # Execute the function with optional timeout
            if timeout_duration:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_duration)
            else:
                result = await func(*args, **kwargs)

            # Record success
            self._record_success()
            return result

        except Exception:
            # Record failure
            self._record_failure()
            raise

    def _record_success(self) -> None:
        """Record a successful call."""
        self._stats["successful_calls"] += 1

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1

            # Check if we should close the circuit
            if self.success_count >= self.success_threshold:
                self._change_state(CircuitState.CLOSED)

        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success in closed state
            self.failure_count = 0

    def _record_failure(self) -> None:
        """Record a failed call."""
        self._stats["failed_calls"] += 1
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.CLOSED:
            # Check if we should open the circuit
            if self.failure_count >= self.failure_threshold:
                self._change_state(CircuitState.OPEN)

        elif self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens the circuit
            self._change_state(CircuitState.OPEN)

    def get_state(self) -> str:
        """Get current circuit breaker state."""
        return self.state.value

    def get_stats(self) -> dict:
        """
        Get circuit breaker statistics.

        Returns:
            Dictionary with statistics
        """
        success_rate = 0.0
        if self._stats["total_calls"] > 0:
            success_rate = self._stats["successful_calls"] / self._stats["total_calls"]

        return {
            "state": self.state.value,
            "total_calls": self._stats["total_calls"],
            "successful_calls": self._stats["successful_calls"],
            "failed_calls": self._stats["failed_calls"],
            "rejected_calls": self._stats["rejected_calls"],
            "success_rate": success_rate,
            "state_changes": self._stats["state_changes"],
            "current_failure_count": self.failure_count,
            "time_until_retry": (
                max(0, self.timeout - (time.time() - self.last_failure_time))
                if self.state == CircuitState.OPEN and self.last_failure_time
                else 0
            ),
        }

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._change_state(CircuitState.CLOSED)
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    def is_available(self) -> bool:
        """
        Check if the circuit breaker is allowing calls.

        Returns:
            True if calls are allowed, False if circuit is open
        """
        if self._should_attempt_reset():
            self._change_state(CircuitState.HALF_OPEN)

        return self.state != CircuitState.OPEN
