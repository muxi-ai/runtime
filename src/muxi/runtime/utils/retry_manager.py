"""
Retry Manager

Utility for implementing retry logic for transient failures in Formation operations.
"""

import asyncio
import time
from typing import Any, Callable, Awaitable, TypeVar, Optional, Dict

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

                # Success - return result
                elapsed_time = time.time() - start_time
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_attempts=attempt_num,
                    total_elapsed_time=elapsed_time
                )

            except Exception as error:
                attempt_elapsed = time.time() - attempt_start

                # Check if this error should be retried
                if not is_retryable_error(error, retry_config):
                    # Non-retryable error - fail immediately
                    elapsed_time = time.time() - start_time

                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)

                    return RetryResult(
                        success=False,
                        error=error,
                        attempts=attempts,
                        total_attempts=attempt_num,
                        total_elapsed_time=elapsed_time
                    )

                # Calculate delay for next attempt
                delay = 0.0
                if attempt_num < retry_config.max_attempts:
                    delay = calculate_delay(attempt_num, retry_config)

                    # Respect retry_after hint from error if available
                    if isinstance(error, TransientError) and error.retry_after:
                        delay = max(delay, error.retry_after)

                # Record this attempt
                attempt = RetryAttempt(
                    attempt_number=attempt_num,
                    error=error,
                    delay_before_retry=delay,
                    timestamp=attempt_start,
                    elapsed_time=attempt_elapsed
                )
                attempts.append(attempt)

                # Call retry callback if configured
                if retry_config.on_retry_callback:
                    retry_config.on_retry_callback(attempt_num, error, delay)

                # If this was the last attempt, fail
                if attempt_num >= retry_config.max_attempts:
                    elapsed_time = time.time() - start_time

                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)

                    return RetryResult(
                        success=False,
                        error=error,
                        attempts=attempts,
                        total_attempts=attempt_num,
                        total_elapsed_time=elapsed_time
                    )

                # Wait before next attempt
                if delay > 0:
                    await asyncio.sleep(delay)

        # Should never reach here, but handle gracefully
        elapsed_time = time.time() - start_time
        return RetryResult(
            success=False,
            error=RuntimeError(f"Retry logic error for {operation_name}"),
            attempts=attempts,
            total_attempts=retry_config.max_attempts,
            total_elapsed_time=elapsed_time
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

                # Success - return result
                elapsed_time = time.time() - start_time
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_attempts=attempt_num,
                    total_elapsed_time=elapsed_time
                )

            except Exception as error:
                attempt_elapsed = time.time() - attempt_start

                # Check if this error should be retried
                if not is_retryable_error(error, retry_config):
                    # Non-retryable error - fail immediately
                    elapsed_time = time.time() - start_time

                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)

                    return RetryResult(
                        success=False,
                        error=error,
                        attempts=attempts,
                        total_attempts=attempt_num,
                        total_elapsed_time=elapsed_time
                    )

                # Calculate delay for next attempt
                delay = 0.0
                if attempt_num < retry_config.max_attempts:
                    delay = calculate_delay(attempt_num, retry_config)

                    # Respect retry_after hint from error if available
                    if isinstance(error, TransientError) and error.retry_after:
                        delay = max(delay, error.retry_after)

                # Record this attempt
                attempt = RetryAttempt(
                    attempt_number=attempt_num,
                    error=error,
                    delay_before_retry=delay,
                    timestamp=attempt_start,
                    elapsed_time=attempt_elapsed
                )
                attempts.append(attempt)

                # Call retry callback if configured
                if retry_config.on_retry_callback:
                    retry_config.on_retry_callback(attempt_num, error, delay)

                # If this was the last attempt, fail
                if attempt_num >= retry_config.max_attempts:
                    elapsed_time = time.time() - start_time

                    if retry_config.on_failure_callback:
                        retry_config.on_failure_callback(error, attempt_num)

                    return RetryResult(
                        success=False,
                        error=error,
                        attempts=attempts,
                        total_attempts=attempt_num,
                        total_elapsed_time=elapsed_time
                    )

                # Wait before next attempt
                if delay > 0:
                    time.sleep(delay)

        # Should never reach here, but handle gracefully
        elapsed_time = time.time() - start_time
        return RetryResult(
            success=False,
            error=RuntimeError(f"Retry logic error for {operation_name}"),
            attempts=attempts,
            total_attempts=retry_config.max_attempts,
            total_elapsed_time=elapsed_time
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
        on_retry_callback=lambda attempt, error, delay: print(
            f"🔄 {operation_name} attempt {attempt} failed: {error}. "
            f"Retrying in {delay:.1f}s..."
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
        on_retry_callback=lambda attempt, error, delay: print(
            f"🔄 {operation_name} attempt {attempt} failed: {error}. "
            f"Retrying in {delay:.1f}s..."
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
    error_str = str(error).lower()

    # Network timeouts
    if isinstance(error, TimeoutError) or 'timeout' in error_str or 'timed out' in error_str:
        return NetworkTransientError(
            f"Network timeout: {error}",
            details={"original_error": str(error)}
        )

    # Connection issues
    if isinstance(error, ConnectionError) or 'connection' in error_str:
        if 'refused' in error_str:
            return NetworkTransientError(
                f"Connection refused: {error}",
                details={"original_error": str(error)}
            )
        else:
            return NetworkTransientError(
                f"Connection error: {error}",
                details={"original_error": str(error)}
            )

    # Service unavailable
    if 'service unavailable' in error_str or 'temporarily unavailable' in error_str:
        return ServiceTransientError(
            f"Service unavailable: {error}",
            details={"original_error": str(error)}
        )

    # Rate limiting
    if 'rate limit' in error_str or 'too many requests' in error_str:
        return RateLimitTransientError(
            f"Rate limited: {error}",
            details={"original_error": str(error)}
        )

    # DNS issues
    if 'dns' in error_str or 'name resolution' in error_str:
        return NetworkTransientError(
            f"DNS resolution failed: {error}",
            details={"original_error": str(error)}
        )

    return None
