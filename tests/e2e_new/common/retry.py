"""
Error recovery and retry logic for E2E tests.
"""

from typing import Callable, Any
import asyncio
import time
from functools import wraps
class RetryConfig:
    """Configuration for retry behavior."""

    DEFAULT_ATTEMPTS = 3
    DEFAULT_DELAY = 1.0  # seconds
    DEFAULT_BACKOFF = 2.0  # exponential backoff multiplier

    TRANSIENT_ERRORS = [
        "connection reset",
        "timeout",
        "rate limit",
        "service unavailable",
        "connection refused",
        "network unreachable",
    ]
class TestRetry:
    """Retry logic for handling transient failures in tests."""

    @staticmethod
    def with_retry(
        attempts: int = RetryConfig.DEFAULT_ATTEMPTS,
        delay: float = RetryConfig.DEFAULT_DELAY,
        backoff: float = RetryConfig.DEFAULT_BACKOFF,
        exceptions: tuple = (Exception,),
    ):
        """Decorator for retrying test operations."""

        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay

                for attempt in range(attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if TestRetry._is_transient(e) and attempt < attempts - 1:
                            print(f"  Retry {attempt + 1}/{attempts} after {current_delay}s: {e}")
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            raise

                raise last_exception

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                current_delay = delay

                for attempt in range(attempts):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if TestRetry._is_transient(e) and attempt < attempts - 1:
                            print(f"  Retry {attempt + 1}/{attempts} after {current_delay}s: {e}")
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            raise

                raise last_exception

            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

        return decorator

    @staticmethod
    def _is_transient(exception: Exception) -> bool:
        """Check if exception is likely transient and worth retrying."""
        error_msg = str(exception).lower()
        return any(err.lower() in error_msg for err in RetryConfig.TRANSIENT_ERRORS)
class CircuitBreaker:
    """Prevent cascading failures by failing fast after threshold."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.is_open = False

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if self.is_open:
            if self.last_failure_time and time.time() - self.last_failure_time > self.timeout:
                self.is_open = False
                self.failures = 0
            else:
                raise RuntimeError(
                    f"Circuit breaker open - service failures exceeded {self.failure_threshold}"
                )

        try:
            result = func(*args, **kwargs)
            self.failures = 0
            return result
        except Exception:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.is_open = True
            raise
