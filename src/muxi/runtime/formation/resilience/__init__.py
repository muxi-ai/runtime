"""
Resilience module for advanced error handling and recovery.

This module provides comprehensive error handling, recovery strategies,
circuit breaker patterns, and fallback management for production-ready
workflow execution.

Components:
- ErrorClassifier: Classify and categorize different types of errors
- RecoveryStrategist: Select optimal recovery strategies based on error types
- CircuitBreaker: Prevent cascading failures with circuit breaker patterns
- FallbackManager: Provide graceful degradation when recovery fails
- ResilientWorkflowManager: Main orchestrator for resilient workflow execution
"""

from ...datatypes.resilience import (
    ErrorType,
    ErrorSeverity,
    RecoveryStrategy,
    RecoveryResult,
    CircuitState,
    ResilienceConfig,
    ResilientWorkflowResult,
    WorkflowException,
    RecoveryException,
    CircuitBreakerException,
)

from .error_classifier import ErrorClassifier
from .recovery_strategist import RecoveryStrategist
from .circuit_breaker import CircuitBreaker
from .fallback_manager import FallbackManager
# COMMENTED OUT - Unused, architectural issues with workflow execution
# from .resilient_workflow_manager import ResilientWorkflowManager

__all__ = [
    # Types
    "ErrorType",
    "ErrorSeverity",
    "RecoveryStrategy",
    "RecoveryResult",
    "CircuitState",
    "ResilienceConfig",
    "ResilientWorkflowResult",
    "WorkflowException",
    "RecoveryException",
    "CircuitBreakerException",

    # Components
    "ErrorClassifier",
    "RecoveryStrategist",
    "CircuitBreaker",
    "FallbackManager",
    # "ResilientWorkflowManager",  # COMMENTED OUT - Unused
]
