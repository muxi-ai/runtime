"""
Retry Manager

Utility for implementing retry logic for transient failures in Formation operations.
"""

import asyncio
import time
from typing import Any, Callable, Awaitable, TypeVar, Optional, Dict

from ..services import observability
from ..datatypes.retry import (
    RetryConfig,
    RetryResult,
    RetryAttempt,
    RetryStrategy,
    TransientError,
    NetworkTransientError,
    ServiceTransientError,
    RateLimitTransientError,
    calculate_delay,
    is_retryable_error,
)

T = TypeVar('T')


class RetryManager:
    """
    Manager for retry operations with comprehensive failure handling.

    Provides retry logic for transient failures with configurable strategies,
    backoff algorithms, and error classification.
    """

    def __init__(self, default_config: Optional[RetryConfig] = None):
        """
        Initialize retry manager.

        Args:
            default_config: Default retry configuration
        """
        self.default_config = default_config or RetryConfig()

    def _should_retry_error(self, error: Exception, retry_config: RetryConfig) -> bool:
        """Check if an error should be retried based on configuration."""
        return is_retryable_error(error, retry_config)

    def _calculate_retry_delay(self, attempt_num: int, retry_config: RetryConfig, error: Exception) -> float:
        """Calculate delay for next retry attempt."""
        if attempt_num >= retry_config.max_attempts:
            return 0.0

        delay = calculate_delay(attempt_num, retry_config)

        # Respect retry_after hint from error if available
        if isinstance(error, TransientError) and error.retry_after:
            delay = max(delay, error.retry_after)

        return delay

    def _create_retry_attempt(self, attempt_num: int, error: Exception, delay: float,
                              attempt_start: float, attempt_elapsed: float) -> RetryAttempt:
        """Create a RetryAttempt record."""
        return RetryAttempt(
            attempt_number=attempt_num,
            error=error,
            delay_before_retry=delay,
            timestamp=attempt_start,
            elapsed_time=attempt_elapsed
        )

    def _create_success_result(self, result: T, attempts: list, attempt_num: int, start_time: float) -> RetryResult:
        """Create a successful RetryResult."""
        elapsed_time = time.time() - start_time
        return RetryResult(
            success=True,
            result=result,
            attempts=attempts,
            total_attempts=attempt_num,
            total_elapsed_time=elapsed_time
        )

    def _create_failure_result(self, error: Exception, attempts: list, attempt_num: int,
                               start_time: float) -> RetryResult:
        """Create a failed RetryResult."""
        elapsed_time = time.time() - start_time
        return RetryResult(
            success=False,
            error=error,
            attempts=attempts,
            total_attempts=attempt_num,
            total_elapsed_time=elapsed_time
        )

    async def execute_with_retry(
        self,
        operation: Callable[[], Awaitable[T]],
        config: Optional[RetryConfig] = None,
        operation_name: str = "operation",
        context: Optional[Dict[str, Any]] = None
    ) -> RetryResult:
        """
        Execute an async operation with retry logic.

        Args:
            operation: Async function to execute
            config: Retry configuration (uses default if None)
            operation_name: Name for logging/debugging
            context: Additional context for callbacks

        Returns:
            RetryResult with success/failure information
        """
        retry_config = config or self.default_config
        start_time = time.time()
        attempts = []

        for attempt_num in range(1, retry_config.max_attempts + 1):
            attempt_start = time.time()

            try:
                result = await operation()
                return self._create_success_result(result, attempts, attempt_num, start_time)

            except Exception as error:
                attempt_elapsed = time.time() - attempt_start

                # Check if this error should be retried
                if not self._should_retry_error(error, retry_config):
                    # Non-retryable error - fail immediately
                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)
                    return self._create_failure_result(error, attempts, attempt_num, start_time)

                # Calculate delay for next attempt
                delay = self._calculate_retry_delay(attempt_num, retry_config, error)

                # Record this attempt
                attempt = self._create_retry_attempt(attempt_num, error, delay, attempt_start, attempt_elapsed)
                attempts.append(attempt)

                # Call retry callback if configured
                if retry_config.on_retry_callback:
                    retry_config.on_retry_callback(attempt_num, error, delay)

                # If this was the last attempt, fail
                if attempt_num >= retry_config.max_attempts:
                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)
                    return self._create_failure_result(error, attempts, attempt_num, start_time)

                # Wait before next attempt
                if delay > 0:
                    await asyncio.sleep(delay)

        # Should never reach here, but handle gracefully
        return self._create_failure_result(
            RuntimeError(f"Retry logic error for {operation_name}"),
            attempts,
            retry_config.max_attempts,
            start_time
        )

    def execute_sync_with_retry(
        self,
        operation: Callable[[], T],
        config: Optional[RetryConfig] = None,
        operation_name: str = "operation",
        context: Optional[Dict[str, Any]] = None
    ) -> RetryResult:
        """
        Execute a synchronous operation with retry logic.

        Args:
            operation: Sync function to execute
            config: Retry configuration (uses default if None)
            operation_name: Name for logging/debugging
            context: Additional context for callbacks

        Returns:
            RetryResult with success/failure information
        """
        retry_config = config or self.default_config
        start_time = time.time()
        attempts = []

        for attempt_num in range(1, retry_config.max_attempts + 1):
            attempt_start = time.time()

            try:
                result = operation()
                return self._create_success_result(result, attempts, attempt_num, start_time)

            except Exception as error:
                attempt_elapsed = time.time() - attempt_start

                # Check if this error should be retried
                if not self._should_retry_error(error, retry_config):
                    # Non-retryable error - fail immediately
                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)
                    return self._create_failure_result(error, attempts, attempt_num, start_time)

                # Calculate delay for next attempt
                delay = self._calculate_retry_delay(attempt_num, retry_config, error)

                # Record this attempt
                attempt = self._create_retry_attempt(attempt_num, error, delay, attempt_start, attempt_elapsed)
                attempts.append(attempt)

                # Call retry callback if configured
                if retry_config.on_retry_callback:
                    retry_config.on_retry_callback(attempt_num, error, delay)

                # If this was the last attempt, fail
                if attempt_num >= retry_config.max_attempts:
                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)
                    return self._create_failure_result(error, attempts, attempt_num, start_time)

                # Wait before next attempt
                if delay > 0:
                    time.sleep(delay)

        # Should never reach here, but handle gracefully
        return self._create_failure_result(
            RuntimeError(f"Retry logic error for {operation_name}"),
            attempts,
            retry_config.max_attempts,
            start_time
        )


# Global retry manager instance
_retry_manager: Optional[RetryManager] = None


def get_retry_manager() -> RetryManager:
    """Get the global retry manager instance."""
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = RetryManager()
    return _retry_manager


def set_default_retry_config(config: RetryConfig) -> None:
    """Set the default retry configuration for the global manager."""
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = RetryManager(config)
    else:
        _retry_manager.default_config = config


# Convenience functions for common retry scenarios
async def retry_network_operation(
    operation: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    operation_name: str = "network_operation"
) -> RetryResult:
    """
    Retry a network operation with network-specific error handling.

    Args:
        operation: Async network operation to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay between attempts
        operation_name: Name for logging

    Returns:
        RetryResult with operation outcome
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        base_delay=base_delay,
        max_delay=30.0,
        retryable_errors=[
            ConnectionError,
            TimeoutError,
            OSError,
            NetworkTransientError,
        ],
        retry_on_status_codes=[408, 429, 500, 502, 503, 504],
        on_retry_callback=lambda attempt, error, delay: observability.observe(
            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
            level=observability.EventLevel.WARNING,
            data={
                "operation_name": operation_name,
                "attempt_number": attempt,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "retry_delay": delay,
                "total_attempts": max_attempts
            },
            description=f"🔄 {operation_name} attempt {attempt} failed: {error}. Retrying in {delay:.1f}s..."
        )
    )

    manager = get_retry_manager()
    return await manager.execute_with_retry(operation, config, operation_name)


async def retry_api_call(
    operation: Callable[[], Awaitable[T]],
    max_attempts: int = 5,
    base_delay: float = 2.0,
    operation_name: str = "api_call"
) -> RetryResult:
    """
    Retry an API call with API-specific error handling.

    Args:
        operation: Async API operation to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay between attempts
        operation_name: Name for logging

    Returns:
        RetryResult with operation outcome
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        strategy=RetryStrategy.JITTERED_BACKOFF,
        base_delay=base_delay,
        max_delay=60.0,
        backoff_multiplier=1.5,
        jitter_range=0.2,
        retryable_errors=[
            ConnectionError,
            TimeoutError,
            OSError,
            ServiceTransientError,
            RateLimitTransientError,
        ],
        retry_on_status_codes=[408, 429, 500, 502, 503, 504],
        on_retry_callback=lambda attempt, error, delay: observability.observe(
            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
            level=observability.EventLevel.WARNING,
            data={
                "operation_name": operation_name,
                "attempt_number": attempt,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "retry_delay": delay,
                "total_attempts": max_attempts
            },
            description=f"🔄 {operation_name} attempt {attempt} failed: {error}. Retrying in {delay:.1f}s..."
        )
    )

    manager = get_retry_manager()
    return await manager.execute_with_retry(operation, config, operation_name)


def classify_error_as_transient(error: Exception) -> Optional[TransientError]:
    """
    Classify a standard exception as a transient error if applicable.

    Args:
        error: Exception to classify

    Returns:
        TransientError if the error is transient, None otherwise
    """
    # Network timeouts - use isinstance checks instead of string matching
    if isinstance(error, TimeoutError):
        return NetworkTransientError(
            f"Network timeout: {error}",
            details={"original_error": str(error)}
        )

    # Connection issues - use isinstance checks
    if isinstance(error, ConnectionError):
        if isinstance(error, ConnectionRefusedError):
            return NetworkTransientError(
                f"Connection refused: {error}",
                details={"original_error": str(error)}
            )
        else:
            return NetworkTransientError(
                f"Connection error: {error}",
                details={"original_error": str(error)}
            )

    # OS network errors
    if isinstance(error, OSError):
        # Common network-related OS errors
        if error.errno in (10054, 10060, 10061, 104, 110, 111):  # Common network error codes
            return NetworkTransientError(
                f"Network OS error: {error}",
                details={"original_error": str(error), "errno": error.errno}
            )

    # HTTP-specific errors (for when using requests or httpx)
    if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
        status_code = error.response.status_code
        if status_code in [408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524]:
            if status_code == 429:
                return RateLimitTransientError(
                    f"Rate limited (HTTP {status_code}): {error}",
                    details={"original_error": str(error), "status_code": status_code}
                )
            elif status_code in [500, 502, 503, 504]:
                return ServiceTransientError(
                    f"Service unavailable (HTTP {status_code}): {error}",
                    details={"original_error": str(error), "status_code": status_code}
                )
            else:
                return NetworkTransientError(
                    f"Network error (HTTP {status_code}): {error}",
                    details={"original_error": str(error), "status_code": status_code}
                )

    # Import errors for missing optional dependencies
    if isinstance(error, ImportError):
        return None  # Not transient - missing dependency

    # Fall back to string matching for some specific cases that lack proper exception types
    error_str = str(error).lower()

    # DNS resolution failures (when not caught by OSError)
    dns_error_terms = [
        'name or service not known',
        'nodename nor servname',
        'no address associated'
    ]
    if any(term in error_str for term in dns_error_terms):
        return NetworkTransientError(
            f"DNS resolution failed: {error}",
            details={"original_error": str(error)}
        )

    # Service unavailable messages (when not caught by HTTP status)
    if any(term in error_str for term in ['service unavailable', 'temporarily unavailable', 'try again later']):
        return ServiceTransientError(
            f"Service unavailable: {error}",
            details={"original_error": str(error)}
        )

    return None
