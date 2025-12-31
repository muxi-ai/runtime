"""
Circuit Breaker Implementation for Resilience Framework.

This module provides circuit breaker functionality to prevent cascading
failures by monitoring failure rates and temporarily blocking requests
when failure thresholds are exceeded.
"""

import time
import asyncio
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic

from ...datatypes.resilience import (
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitBreakerException,
    WorkflowException,
    ErrorType,
    ErrorSeverity,
)
from ...datatypes import observability

T = TypeVar("T")


class CircuitBreaker(Generic[T]):
    """
    Circuit breaker implementation that monitors failure rates and prevents
    cascading failures by temporarily blocking requests when thresholds are exceeded.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is open, requests fail fast
    - HALF_OPEN: Testing if service has recovered
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize the circuit breaker.

        Args:
            name: Unique name for this circuit breaker
            config: Configuration for circuit breaker behavior
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState()
        self._lock = asyncio.Lock()

    async def execute(
        self, func: Callable[..., T], *args, fallback: Optional[Callable[..., T]] = None, **kwargs
    ) -> T:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Arguments for the function
            fallback: Optional fallback function if circuit is open
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function execution

        Raises:
            CircuitBreakerException: If circuit is open and no fallback provided
        """
        async with self._lock:
            # Check if we should allow the request
            if not await self._should_allow_request():
                if fallback:
                    observability.observe(
                        event_type=observability.SystemEvents.CIRCUIT_BREAKER_FALLBACK_TRIGGERED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "circuit_breaker": self.name,
                            "state": self.state.state.value,
                            "failure_count": self.state.failure_count,
                        },
                        description=(
                            f"Circuit breaker '{self.name}' triggered fallback "
                            f"(state: {self.state.state.value})"
                        ),
                    )
                    return await self._execute_fallback(fallback, *args, **kwargs)
                else:
                    estimated_recovery = self._get_estimated_recovery_time()
                    raise CircuitBreakerException(
                        f"Circuit breaker '{self.name}' is open",
                        estimated_recovery_time=estimated_recovery,
                    )

        # Execute the function
        start_time = time.time()
        try:
            result = await self._execute_function(func, *args, **kwargs)
            execution_time = time.time() - start_time

            # Record success
            await self._record_success(execution_time)
            return result

        except Exception as error:
            execution_time = time.time() - start_time

            # Record failure
            await self._record_failure(error, execution_time)
            raise

    async def _should_allow_request(self) -> bool:
        """Determine if a request should be allowed based on circuit state."""
        current_time = time.time()

        if self.state.state == CircuitState.CLOSED:
            return True

        elif self.state.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if self.state.next_attempt_time and current_time >= self.state.next_attempt_time:
                await self._transition_to_half_open()
                return True
            return False

        elif self.state.state == CircuitState.HALF_OPEN:
            # Allow limited requests in half-open state
            return True

        return False

    async def _execute_function(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute the function with timeout protection."""
        try:
            if asyncio.iscoroutinefunction(func):
                return await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout)
            else:
                # Run sync function in executor with timeout
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                    timeout=self.config.timeout,
                )
        except asyncio.TimeoutError:
            raise WorkflowException(
                f"Function execution timed out after {self.config.timeout}s",
                ErrorType.AGENT_TIMEOUT,
                ErrorSeverity.MEDIUM,
            )

    async def _execute_fallback(self, fallback: Callable[..., T], *args, **kwargs) -> T:
        """Execute the fallback function."""
        try:
            if asyncio.iscoroutinefunction(fallback):
                return await fallback(*args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: fallback(*args, **kwargs))
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.CIRCUIT_BREAKER_FALLBACK_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "circuit_breaker": self.name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Circuit breaker '{self.name}' fallback execution failed: {str(e)}",
            )
            raise WorkflowException(
                f"Both primary function and fallback failed for circuit breaker '{self.name}'",
                ErrorType.SYSTEM_OVERLOAD,
                ErrorSeverity.CRITICAL,
            )

    async def _record_success(self, execution_time: float) -> None:
        """Record a successful execution."""
        current_time = time.time()

        self.state.total_requests += 1
        self.state.total_successes += 1
        self.state.last_success_time = current_time

        if self.state.state == CircuitState.HALF_OPEN:
            self.state.success_count += 1

            # Check if we should close the circuit
            if self.state.success_count >= self.config.success_threshold:
                await self._transition_to_closed()

        elif self.state.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.state.failure_count = max(0, self.state.failure_count - 1)

        #     f"Circuit breaker '{self.name}' recorded success "
        #     f"(execution_time: {execution_time:.2f}s, state: {self.state.state.value})"
        # )

    async def _record_failure(self, error: Exception, execution_time: float) -> None:
        """Record a failed execution."""
        current_time = time.time()

        self.state.total_requests += 1
        self.state.total_failures += 1
        self.state.failure_count += 1
        self.state.last_failure_time = current_time

        # Check if we should open the circuit
        if (
            self.state.state in [CircuitState.CLOSED, CircuitState.HALF_OPEN]
            and self.state.failure_count >= self.config.failure_threshold
        ):
            await self._transition_to_open()

        observability.observe(
            event_type=observability.SystemEvents.CIRCUIT_BREAKER_FAILURE_RECORDED,
            level=observability.EventLevel.WARNING,
            data={
                "circuit_breaker": self.name,
                "error": str(error),
                "execution_time": execution_time,
                "failure_count": self.state.failure_count,
                "threshold": self.config.failure_threshold,
            },
            description=(
                f"Circuit breaker '{self.name}' recorded failure: {error} "
                f"(execution_time: {execution_time:.2f}s, "
                f"failures: {self.state.failure_count})"
            ),
        )
        # )

    async def _transition_to_open(self) -> None:
        """Transition circuit breaker to OPEN state."""
        self.state.state = CircuitState.OPEN
        self.state.next_attempt_time = time.time() + self.config.recovery_timeout
        self.state.success_count = 0

        observability.observe(
            event_type=observability.SystemEvents.CIRCUIT_BREAKER_OPENED,
            level=observability.EventLevel.WARNING,
            data={
                "circuit_breaker": self.name,
                "failure_count": self.state.failure_count,
                "next_attempt_time": self.state.next_attempt_time,
                "recovery_timeout": self.config.recovery_timeout,
            },
            description=(
                f"Circuit breaker '{self.name}' opened due to "
                f"{self.state.failure_count} failures. "
                f"Will attempt recovery at {time.ctime(self.state.next_attempt_time)}"
            ),
        )
        # )

    async def _transition_to_half_open(self) -> None:
        """Transition circuit breaker to HALF_OPEN state."""
        self.state.state = CircuitState.HALF_OPEN
        self.state.success_count = 0
        self.state.failure_count = 0

    async def _transition_to_closed(self) -> None:
        """Transition circuit breaker to CLOSED state."""
        self.state.state = CircuitState.CLOSED
        self.state.failure_count = 0
        self.state.success_count = 0
        self.state.next_attempt_time = None

    def _get_estimated_recovery_time(self) -> Optional[float]:
        """Get estimated time until circuit breaker recovery attempt."""
        if self.state.next_attempt_time:
            return max(0, self.state.next_attempt_time - time.time())
        return None

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self.state

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        total_requests = self.state.total_requests
        success_rate = (
            (self.state.total_successes / total_requests * 100) if total_requests > 0 else 0
        )
        failure_rate = (
            (self.state.total_failures / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            "name": self.name,
            "state": self.state.state.value,
            "total_requests": total_requests,
            "total_successes": self.state.total_successes,
            "total_failures": self.state.total_failures,
            "success_rate": round(success_rate, 2),
            "failure_rate": round(failure_rate, 2),
            "current_failure_count": self.state.failure_count,
            "current_success_count": self.state.success_count,
            "failure_threshold": self.config.failure_threshold,
            "success_threshold": self.config.success_threshold,
            "last_failure_time": self.state.last_failure_time,
            "last_success_time": self.state.last_success_time,
            "next_attempt_time": self.state.next_attempt_time,
            "estimated_recovery_time": self._get_estimated_recovery_time(),
        }

    async def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self.state = CircuitBreakerState()

    async def force_open(self) -> None:
        """Force circuit breaker to OPEN state."""
        async with self._lock:
            await self._transition_to_open()
            observability.observe(
                event_type=observability.SystemEvents.CIRCUIT_BREAKER_FORCED_OPEN,
                level=observability.EventLevel.WARNING,
                data={"circuit_breaker": self.name},
                description=f"Circuit breaker '{self.name}' was manually forced open",
            )

    async def force_close(self) -> None:
        """Force circuit breaker to CLOSED state."""
        async with self._lock:
            await self._transition_to_closed()


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        """Initialize the circuit breaker registry."""
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._default_config = CircuitBreakerConfig()

    def get_circuit_breaker(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker by name.

        Args:
            name: Circuit breaker name
            config: Optional configuration (uses default if not provided)

        Returns:
            CircuitBreaker instance
        """
        if name not in self._circuit_breakers:
            effective_config = config or self._default_config
            self._circuit_breakers[name] = CircuitBreaker(name, effective_config)

        return self._circuit_breakers[name]

    def remove_circuit_breaker(self, name: str) -> bool:
        """
        Remove a circuit breaker from the registry.

        Args:
            name: Circuit breaker name

        Returns:
            True if removed, False if not found
        """
        if name in self._circuit_breakers:
            del self._circuit_breakers[name]
            return True
        return False

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {name: cb.get_stats() for name, cb in self._circuit_breakers.items()}

    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._circuit_breakers.values():
            await cb.reset()

    def set_default_config(self, config: CircuitBreakerConfig) -> None:
        """Set default configuration for new circuit breakers."""
        self._default_config = config

    def list_circuit_breakers(self) -> List[str]:
        """List all circuit breaker names."""
        return list(self._circuit_breakers.keys())
