"""
Type definitions for the resilience system.

This module defines all the data structures, enums, and exceptions
used throughout the resilience and error handling system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime


class ErrorType(Enum):
    """Classification of different error types for recovery strategy selection."""

    # Network-related errors
    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_FAILED = "connection_failed"
    DNS_RESOLUTION = "dns_resolution"
    SSL_ERROR = "ssl_error"

    # Agent-related errors
    AGENT_UNAVAILABLE = "agent_unavailable"
    AGENT_OVERLOADED = "agent_overloaded"
    AGENT_CRASHED = "agent_crashed"
    AGENT_TIMEOUT = "agent_timeout"

    # Workflow-related errors
    WORKFLOW_VALIDATION = "workflow_validation"
    DEPENDENCY_FAILED = "dependency_failed"
    TASK_EXECUTION = "task_execution"
    RESOURCE_EXHAUSTED = "resource_exhausted"

    # LLM-related errors
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_CONTEXT_OVERFLOW = "llm_context_overflow"
    LLM_API_ERROR = "llm_api_error"
    LLM_QUOTA_EXCEEDED = "llm_quota_exceeded"

    # Memory-related errors
    MEMORY_FULL = "memory_full"
    MEMORY_CORRUPTION = "memory_corruption"
    MEMORY_ACCESS_DENIED = "memory_access_denied"

    # Authentication/Authorization errors
    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    TOKEN_EXPIRED = "token_expired"

    # Data-related errors
    DATA_VALIDATION = "data_validation"
    DATA_CORRUPTION = "data_corruption"
    SERIALIZATION_ERROR = "serialization_error"

    # System-related errors
    SYSTEM_OVERLOAD = "system_overload"
    DISK_FULL = "disk_full"
    CONFIGURATION_ERROR = "configuration_error"

    # Unknown/Generic errors
    UNKNOWN = "unknown"
    CRITICAL = "critical"


class ErrorSeverity(Enum):
    """Severity levels for error classification."""

    LOW = "low"  # Minor issues, can be ignored or retried
    MEDIUM = "medium"  # Moderate issues, require intervention
    HIGH = "high"  # Serious issues, may impact user experience
    CRITICAL = "critical"  # Critical issues, system functionality compromised


class RecoveryStrategy(Enum):
    """Available recovery strategies for different error types."""

    # Retry strategies
    IMMEDIATE_RETRY = "immediate_retry"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    JITTERED_RETRY = "jittered_retry"

    # Fallback strategies
    FALLBACK_AGENT = "fallback_agent"
    FALLBACK_WORKFLOW = "fallback_workflow"
    CACHED_RESPONSE = "cached_response"

    # Circuit breaker strategies
    CIRCUIT_BREAKER = "circuit_breaker"
    BULKHEAD_ISOLATION = "bulkhead_isolation"

    # Graceful degradation
    SIMPLIFIED_WORKFLOW = "simplified_workflow"
    PARTIAL_RESPONSE = "partial_response"
    ERROR_MESSAGE = "error_message"

    # System intervention
    ESCALATE_TO_ADMIN = "escalate_to_admin"
    MANUAL_INTERVENTION = "manual_intervention"

    # No recovery
    FAIL_FAST = "fail_fast"
    ABORT_WORKFLOW = "abort_workflow"


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    success: bool
    strategy_used: RecoveryStrategy
    result: Optional[Any] = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    attempts: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: float = 60.0  # Seconds before trying half-open
    success_threshold: int = 3  # Successes needed to close from half-open
    timeout: float = 30.0  # Request timeout in seconds
    monitor_window: float = 300.0  # Time window for failure tracking (seconds)


@dataclass
class RetryConfig:
    """Configuration for retry strategies."""

    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1


@dataclass
class ResilienceConfig:
    """Comprehensive configuration for resilience behavior."""

    # Global settings
    enable_circuit_breaker: bool = True
    enable_retries: bool = True
    enable_fallbacks: bool = True
    enable_graceful_degradation: bool = True

    # Circuit breaker configuration
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # Retry configuration
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Timeout settings
    default_timeout: float = 30.0
    agent_timeout: float = 60.0
    workflow_timeout: float = 300.0

    # Fallback settings
    enable_cached_fallbacks: bool = True
    enable_simplified_workflows: bool = True
    fallback_models: List[str] = field(default_factory=list)

    # Error handling preferences
    auto_escalation_threshold: ErrorSeverity = ErrorSeverity.HIGH
    log_all_errors: bool = True
    detailed_error_reporting: bool = False

    # Custom recovery strategies (error_type -> strategy)
    custom_strategies: Dict[ErrorType, RecoveryStrategy] = field(default_factory=dict)


@dataclass
class ResilientWorkflowResult:
    """Result of resilient workflow execution."""

    result: Optional[Any] = None
    success: bool = False
    recovery_used: bool = False
    recovery_strategy: Optional[str] = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    attempts: int = 1
    fallback_used: bool = False
    circuit_breaker_triggered: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorContext:
    """Context information for error analysis."""

    error: Exception
    error_type: ErrorType
    severity: ErrorSeverity
    timestamp: datetime = field(default_factory=datetime.now)
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    user_id: Optional[int] = None
    attempt_count: int = 1
    previous_errors: List[Exception] = field(default_factory=list)
    context_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerState:
    """State information for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    next_attempt_time: Optional[float] = None
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0


# Custom Exceptions


class WorkflowException(Exception):
    """Base exception for workflow-related errors."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.severity = severity
        self.context = context or {}
        self.timestamp = datetime.now()


class RecoveryException(WorkflowException):
    """Exception raised during recovery attempts."""

    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
        recovery_strategy: Optional[RecoveryStrategy] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.original_error = original_error
        self.recovery_strategy = recovery_strategy


class CircuitBreakerException(WorkflowException):
    """Exception raised when circuit breaker is open."""

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        estimated_recovery_time: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(message, ErrorType.SYSTEM_OVERLOAD, ErrorSeverity.HIGH, **kwargs)
        self.estimated_recovery_time = estimated_recovery_time


class TimeoutException(WorkflowException):
    """Exception raised when operations timeout."""

    def __init__(self, message: str, timeout_duration: float, **kwargs):
        super().__init__(message, ErrorType.AGENT_TIMEOUT, ErrorSeverity.MEDIUM, **kwargs)
        self.timeout_duration = timeout_duration


class AgentUnavailableException(WorkflowException):
    """Exception raised when agent is unavailable."""

    def __init__(self, message: str, agent_id: Optional[str] = None, **kwargs):
        super().__init__(message, ErrorType.AGENT_UNAVAILABLE, ErrorSeverity.HIGH, **kwargs)
        self.agent_id = agent_id


# Type aliases for commonly used types
ErrorHandler = Callable[[ErrorContext], RecoveryResult]
FallbackFunction = Callable[..., Any]
WorkflowFunction = Callable[..., Any]
