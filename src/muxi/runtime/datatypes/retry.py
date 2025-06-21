"""
Retry Logic Data Types

Core data structures for implementing retry logic for transient failures.
"""

import random
from typing import Any, Dict, Optional, Callable, List, Type
from dataclasses import dataclass, field
from enum import Enum


class RetryStrategy(Enum):
    """Retry strategy types."""

    FIXED_DELAY = "fixed_delay"
    LINEAR_BACKOFF = "linear_backoff"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    JITTERED_BACKOFF = "jittered_backoff"


class TransientErrorType(Enum):
    """Types of transient errors that can be retried."""

    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_REFUSED = "connection_refused"
    SERVICE_UNAVAILABLE = "service_unavailable"
    RATE_LIMITED = "rate_limited"
    TEMPORARY_FAILURE = "temporary_failure"
    DNS_RESOLUTION = "dns_resolution"
    SSL_HANDSHAKE = "ssl_handshake"
    WEBHOOK_DELIVERY = "webhook_delivery"
    API_TIMEOUT = "api_timeout"
    DATABASE_CONNECTION = "database_connection"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    # Basic retry settings
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds

    # Backoff configuration
    backoff_multiplier: float = 2.0
    jitter_range: float = 0.1  # 10% jitter

    # Error type specific settings
    retryable_errors: List[Type[Exception]] = field(
        default_factory=lambda: [
            ConnectionError,
            TimeoutError,
            OSError,  # Network-related OS errors
        ]
    )

    # Retry conditions
    retry_on_status_codes: List[int] = field(
        default_factory=lambda: [
            408,  # Request Timeout
            429,  # Too Many Requests
            500,  # Internal Server Error
            502,  # Bad Gateway
            503,  # Service Unavailable
            504,  # Gateway Timeout
        ]
    )

    # Callbacks
    on_retry_callback: Optional[Callable[[int, Exception, float], None]] = None
    on_failure_callback: Optional[Callable[[Exception, int], None]] = None


@dataclass
class RetryAttempt:
    """Information about a single retry attempt."""

    attempt_number: int
    error: Exception
    delay_before_retry: float
    timestamp: float
    elapsed_time: float


@dataclass
class RetryResult:
    """Result of a retry operation."""

    success: bool
    result: Any = None
    error: Optional[Exception] = None
    attempts: List[RetryAttempt] = field(default_factory=list)
    total_attempts: int = 0
    total_elapsed_time: float = 0.0

    @property
    def final_attempt_number(self) -> int:
        """Get the final attempt number."""
        return self.total_attempts

    @property
    def was_retried(self) -> bool:
        """Check if the operation was retried."""
        return self.total_attempts > 1


class TransientError(Exception):
    """Base exception for transient errors that can be retried."""

    def __init__(
        self,
        message: str,
        error_type: TransientErrorType,
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.retry_after = retry_after  # Suggested retry delay
        self.details = details or {}


class NetworkTransientError(TransientError):
    """Network-related transient error."""

    def __init__(
        self,
        message: str,
        error_type: TransientErrorType = TransientErrorType.NETWORK_TIMEOUT,
        **kwargs,
    ):
        super().__init__(message, error_type, **kwargs)


class ServiceTransientError(TransientError):
    """Service-related transient error."""

    def __init__(
        self,
        message: str,
        error_type: TransientErrorType = TransientErrorType.SERVICE_UNAVAILABLE,
        **kwargs,
    ):
        super().__init__(message, error_type, **kwargs)


class RateLimitTransientError(TransientError):
    """Rate limiting transient error."""

    def __init__(self, message: str, retry_after: Optional[float] = None, **kwargs):
        super().__init__(
            message, TransientErrorType.RATE_LIMITED, retry_after=retry_after, **kwargs
        )


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay for retry attempt based on strategy.

    Args:
        attempt: Current attempt number (1-based)
        config: Retry configuration

    Returns:
        Delay in seconds before next retry
    """
    if config.strategy == RetryStrategy.FIXED_DELAY:
        delay = config.base_delay

    elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
        delay = config.base_delay * attempt

    elif config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
        delay = config.base_delay * (config.backoff_multiplier ** (attempt - 1))

    elif config.strategy == RetryStrategy.JITTERED_BACKOFF:
        base_delay = config.base_delay * (config.backoff_multiplier ** (attempt - 1))
        jitter = base_delay * config.jitter_range * (2 * random.random() - 1)  # ±jitter_range
        delay = base_delay + jitter

    else:
        delay = config.base_delay

    # Cap at max_delay
    return min(delay, config.max_delay)


def is_retryable_error(error: Exception, config: RetryConfig) -> bool:
    """
    Check if an error is retryable based on configuration.

    Args:
        error: Exception that occurred
        config: Retry configuration

    Returns:
        True if error should be retried
    """
    # Check if error type is in retryable list
    for retryable_type in config.retryable_errors:
        if isinstance(error, retryable_type):
            return True

    # Check for HTTP status codes if error has status attribute
    if hasattr(error, "status") or hasattr(error, "status_code"):
        status = getattr(error, "status", getattr(error, "status_code", None))
        if status and status in config.retry_on_status_codes:
            return True

    # Check for specific transient error types
    if isinstance(error, TransientError):
        return True

    # Check error message for common transient patterns
    error_str = str(error).lower()
    transient_patterns = [
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "service unavailable",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "network unreachable",
        "dns resolution failed",
    ]

    for pattern in transient_patterns:
        if pattern in error_str:
            return True

    return False
