"""
Error Classification System for Resilience Framework.

This module provides intelligent error classification to determine
the appropriate recovery strategy based on error type and context.
"""

import re
import asyncio
from typing import Dict, List, Optional, Pattern

from ...datatypes.resilience import (
    ErrorType,
    ErrorSeverity,
    ErrorContext,
    WorkflowException,
)
from ...services import observability


class ErrorClassifier:
    """
    Intelligent error classifier that analyzes exceptions and determines
    the appropriate error type and severity for recovery strategy selection.

    The classifier uses pattern matching, exception type analysis, and
    contextual information to make accurate classifications.
    """

    def __init__(self):
        """Initialize the error classifier with predefined patterns and rules."""
        self._initialize_classification_patterns()
        self._initialize_severity_rules()

    def _initialize_classification_patterns(self) -> None:
        """Initialize regex patterns for error message classification."""
        self.error_patterns: Dict[ErrorType, List[Pattern]] = {
            # Network-related patterns
            ErrorType.NETWORK_TIMEOUT: [
                re.compile(r"timeout|timed out", re.IGNORECASE),
                re.compile(r"connection.*timeout", re.IGNORECASE),
                re.compile(r"read.*timeout", re.IGNORECASE),
            ],
            ErrorType.CONNECTION_FAILED: [
                re.compile(r"connection.*refused|refused.*connection", re.IGNORECASE),
                re.compile(r"connection.*failed|failed.*connection", re.IGNORECASE),
                re.compile(r"no route to host", re.IGNORECASE),
                re.compile(r"network.*unreachable", re.IGNORECASE),
            ],
            ErrorType.DNS_RESOLUTION: [
                re.compile(r"name.*resolution.*failed", re.IGNORECASE),
                re.compile(r"could not resolve", re.IGNORECASE),
                re.compile(r"dns.*error", re.IGNORECASE),
            ],
            ErrorType.SSL_ERROR: [
                re.compile(r"ssl.*error|certificate.*error", re.IGNORECASE),
                re.compile(r"handshake.*failed", re.IGNORECASE),
                re.compile(r"certificate.*verify.*failed", re.IGNORECASE),
            ],
            # Agent-related patterns
            ErrorType.AGENT_UNAVAILABLE: [
                re.compile(r"agent.*unavailable|unavailable.*agent", re.IGNORECASE),
                re.compile(r"agent.*not.*found", re.IGNORECASE),
                re.compile(r"no.*agent.*available", re.IGNORECASE),
            ],
            ErrorType.AGENT_OVERLOADED: [
                re.compile(r"agent.*overloaded|overloaded.*agent", re.IGNORECASE),
                re.compile(r"agent.*busy|busy.*agent", re.IGNORECASE),
                re.compile(r"too many.*requests", re.IGNORECASE),
            ],
            ErrorType.AGENT_TIMEOUT: [
                re.compile(r"agent.*timeout|timeout.*agent", re.IGNORECASE),
                re.compile(r"agent.*response.*timeout", re.IGNORECASE),
            ],
            # LLM-related patterns
            ErrorType.LLM_RATE_LIMITED: [
                re.compile(r"rate.*limit.*exceeded", re.IGNORECASE),
                re.compile(r"too many.*requests", re.IGNORECASE),
                re.compile(r"quota.*exceeded", re.IGNORECASE),
                re.compile(r"429|rate.limit", re.IGNORECASE),
            ],
            ErrorType.LLM_CONTEXT_OVERFLOW: [
                re.compile(r"context.*length.*exceeded", re.IGNORECASE),
                re.compile(r"maximum.*context.*length", re.IGNORECASE),
                re.compile(r"input.*too.*long", re.IGNORECASE),
            ],
            ErrorType.LLM_API_ERROR: [
                re.compile(r"api.*error|openai.*error", re.IGNORECASE),
                re.compile(r"invalid.*api.*key", re.IGNORECASE),
                re.compile(r"unauthorized.*api", re.IGNORECASE),
            ],
            # Memory-related patterns
            ErrorType.MEMORY_FULL: [
                re.compile(r"out of memory|memory.*full", re.IGNORECASE),
                re.compile(r"insufficient.*memory", re.IGNORECASE),
                re.compile(r"memory.*allocation.*failed", re.IGNORECASE),
            ],
            ErrorType.MEMORY_ACCESS_DENIED: [
                re.compile(r"memory.*access.*denied", re.IGNORECASE),
                re.compile(r"permission.*denied.*memory", re.IGNORECASE),
            ],
            # Auth-related patterns
            ErrorType.AUTH_FAILED: [
                re.compile(r"authentication.*failed|auth.*failed", re.IGNORECASE),
                re.compile(r"invalid.*credentials", re.IGNORECASE),
                re.compile(r"unauthorized", re.IGNORECASE),
            ],
            ErrorType.TOKEN_EXPIRED: [
                re.compile(r"token.*expired|expired.*token", re.IGNORECASE),
                re.compile(r"session.*expired", re.IGNORECASE),
            ],
            ErrorType.PERMISSION_DENIED: [
                re.compile(r"permission.*denied|access.*denied", re.IGNORECASE),
                re.compile(r"forbidden|403", re.IGNORECASE),
            ],
            # Data-related patterns
            ErrorType.DATA_VALIDATION: [
                re.compile(r"validation.*error|invalid.*data", re.IGNORECASE),
                re.compile(r"schema.*validation.*failed", re.IGNORECASE),
                re.compile(r"malformed.*data", re.IGNORECASE),
            ],
            ErrorType.SERIALIZATION_ERROR: [
                re.compile(r"serialization.*error|json.*error", re.IGNORECASE),
                re.compile(r"pickle.*error|encoding.*error", re.IGNORECASE),
            ],
            # System-related patterns
            ErrorType.SYSTEM_OVERLOAD: [
                re.compile(r"system.*overload|server.*overload", re.IGNORECASE),
                re.compile(r"service.*unavailable|503", re.IGNORECASE),
                re.compile(r"internal.*server.*error|500", re.IGNORECASE),
            ],
            ErrorType.DISK_FULL: [
                re.compile(r"no.*space.*left|disk.*full", re.IGNORECASE),
                re.compile(r"storage.*full", re.IGNORECASE),
            ],
            ErrorType.CONFIGURATION_ERROR: [
                re.compile(r"configuration.*error|config.*error", re.IGNORECASE),
                re.compile(r"missing.*configuration", re.IGNORECASE),
                re.compile(r"invalid.*configuration", re.IGNORECASE),
            ],
        }

    def _initialize_severity_rules(self) -> None:
        """Initialize rules for determining error severity."""
        self.severity_rules: Dict[ErrorType, ErrorSeverity] = {
            # Critical errors
            ErrorType.CRITICAL: ErrorSeverity.CRITICAL,
            ErrorType.SYSTEM_OVERLOAD: ErrorSeverity.CRITICAL,
            ErrorType.MEMORY_FULL: ErrorSeverity.CRITICAL,
            ErrorType.DISK_FULL: ErrorSeverity.CRITICAL,
            ErrorType.AGENT_CRASHED: ErrorSeverity.CRITICAL,
            # High severity errors
            ErrorType.AGENT_UNAVAILABLE: ErrorSeverity.HIGH,
            ErrorType.AUTH_FAILED: ErrorSeverity.HIGH,
            ErrorType.PERMISSION_DENIED: ErrorSeverity.HIGH,
            ErrorType.DATA_CORRUPTION: ErrorSeverity.HIGH,
            ErrorType.MEMORY_CORRUPTION: ErrorSeverity.HIGH,
            ErrorType.CONFIGURATION_ERROR: ErrorSeverity.HIGH,
            # Medium severity errors
            ErrorType.NETWORK_TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorType.CONNECTION_FAILED: ErrorSeverity.MEDIUM,
            ErrorType.AGENT_TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorType.AGENT_OVERLOADED: ErrorSeverity.MEDIUM,
            ErrorType.LLM_RATE_LIMITED: ErrorSeverity.MEDIUM,
            ErrorType.LLM_CONTEXT_OVERFLOW: ErrorSeverity.MEDIUM,
            ErrorType.TOKEN_EXPIRED: ErrorSeverity.MEDIUM,
            ErrorType.WORKFLOW_VALIDATION: ErrorSeverity.MEDIUM,
            ErrorType.DEPENDENCY_FAILED: ErrorSeverity.MEDIUM,
            # Low severity errors
            ErrorType.DNS_RESOLUTION: ErrorSeverity.LOW,
            ErrorType.DATA_VALIDATION: ErrorSeverity.LOW,
            ErrorType.SERIALIZATION_ERROR: ErrorSeverity.LOW,
            ErrorType.LLM_API_ERROR: ErrorSeverity.LOW,
        }

        # Exception type mappings
        self.exception_type_mappings: Dict[type, ErrorType] = {
            asyncio.TimeoutError: ErrorType.NETWORK_TIMEOUT,
            TimeoutError: ErrorType.AGENT_TIMEOUT,
            ConnectionError: ErrorType.CONNECTION_FAILED,
            ConnectionRefusedError: ErrorType.CONNECTION_FAILED,
            ConnectionAbortedError: ErrorType.CONNECTION_FAILED,
            ConnectionResetError: ErrorType.CONNECTION_FAILED,
            MemoryError: ErrorType.MEMORY_FULL,
            PermissionError: ErrorType.PERMISSION_DENIED,
            ValueError: ErrorType.DATA_VALIDATION,
            TypeError: ErrorType.DATA_VALIDATION,
            KeyError: ErrorType.DATA_VALIDATION,
            FileNotFoundError: ErrorType.CONFIGURATION_ERROR,
            OSError: ErrorType.SYSTEM_OVERLOAD,
        }

    async def classify(self, error: Exception, context: Optional[Dict] = None) -> ErrorContext:
        """
        Classify an error and return comprehensive error context.

        Args:
            error: The exception to classify
            context: Optional context information

        Returns:
            ErrorContext with classified error information
        """
        try:
            # Determine error type
            error_type = await self._determine_error_type(error)

            # Determine severity
            severity = await self._determine_severity(error, error_type, context)

            # Create error context
            error_context = ErrorContext(
                error=error, error_type=error_type, severity=severity, context_data=context or {}
            )

            # Add additional context from exception
            if hasattr(error, "error_type"):
                error_context.error_type = error.error_type
            if hasattr(error, "severity"):
                error_context.severity = error.severity
            if hasattr(error, "context"):
                error_context.context_data.update(error.context)

            observability.observe(
                event_type=observability.SystemEvents.CIRCUIT_BREAKER_FAILURE_RECORDED,
                level=observability.EventLevel.DEBUG,
                data={
                    "error_type": error_type.value,
                    "severity": severity.value,
                    "error_message": str(error)[:200],
                },
                description=f"Classified error: {error_type.value} (severity: {severity.value})",
            )

            return error_context

        except Exception as classification_error:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "component": "error_classifier",
                    "error_type": type(classification_error).__name__,
                    "error": str(classification_error),
                },
                description="Error classification failed, using fallback",
            )
            # Fallback classification
            return ErrorContext(
                error=error,
                error_type=ErrorType.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                context_data=context or {},
            )

    async def _determine_error_type(self, error: Exception) -> ErrorType:
        """Determine the error type based on exception and message analysis."""

        # Check if it's a WorkflowException with explicit type
        if isinstance(error, WorkflowException) and hasattr(error, "error_type"):
            return error.error_type

        # Check exception type mappings
        error_class = type(error)
        if error_class in self.exception_type_mappings:
            return self.exception_type_mappings[error_class]

        # Check parent classes
        for exception_type, error_type in self.exception_type_mappings.items():
            if isinstance(error, exception_type):
                return error_type

        # Pattern matching on error message
        error_message = str(error).lower()

        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern.search(error_message):
                    return error_type

        # Check for specific HTTP status codes
        if hasattr(error, "status_code"):
            status_code = error.status_code
            if status_code == 429:
                return ErrorType.LLM_RATE_LIMITED
            elif status_code in [401, 403]:
                return ErrorType.AUTH_FAILED
            elif status_code in [500, 502, 503, 504]:
                return ErrorType.SYSTEM_OVERLOAD
            elif status_code == 408:
                return ErrorType.NETWORK_TIMEOUT

        # Default to unknown
        return ErrorType.UNKNOWN

    async def _determine_severity(
        self, error: Exception, error_type: ErrorType, context: Optional[Dict] = None
    ) -> ErrorSeverity:
        """Determine error severity based on type and context."""

        # Check if it's a WorkflowException with explicit severity
        if isinstance(error, WorkflowException) and hasattr(error, "severity"):
            return error.severity

        # Get base severity from rules
        base_severity = self.severity_rules.get(error_type, ErrorSeverity.MEDIUM)

        # Adjust severity based on context
        if context:
            # Critical context indicators
            if context.get("user_facing", False) and base_severity == ErrorSeverity.HIGH:
                return ErrorSeverity.CRITICAL

            # Check for repeated failures
            attempt_count = context.get("attempt_count", 1)
            if attempt_count > 3 and base_severity == ErrorSeverity.MEDIUM:
                return ErrorSeverity.HIGH
            elif attempt_count > 5:
                return ErrorSeverity.CRITICAL

            # Check for workflow importance
            workflow_priority = context.get("workflow_priority", "normal")
            if workflow_priority == "critical" and base_severity == ErrorSeverity.MEDIUM:
                return ErrorSeverity.HIGH

        return base_severity

    def get_classification_stats(self) -> Dict[str, int]:
        """Get statistics about error classifications."""
        return {
            "total_error_types": len(ErrorType),
            "total_patterns": sum(len(patterns) for patterns in self.error_patterns.values()),
            "severity_levels": len(ErrorSeverity),
            "exception_mappings": len(self.exception_type_mappings),
        }

    def add_custom_pattern(self, error_type: ErrorType, pattern: str) -> None:
        """Add a custom pattern for error classification."""
        if error_type not in self.error_patterns:
            self.error_patterns[error_type] = []
        self.error_patterns[error_type].append(re.compile(pattern, re.IGNORECASE))

    def add_exception_mapping(self, exception_class: type, error_type: ErrorType) -> None:
        """Add a custom exception type mapping."""
        self.exception_type_mappings[exception_class] = error_type

    def update_severity_rule(self, error_type: ErrorType, severity: ErrorSeverity) -> None:
        """Update the severity rule for a specific error type."""
        self.severity_rules[error_type] = severity
