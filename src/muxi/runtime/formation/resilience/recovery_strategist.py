"""
Recovery Strategy Selection for Resilience Framework.

This module provides intelligent recovery strategy selection based on
error types, context, and historical success rates.
"""

from typing import Dict, List, Optional

from ...datatypes.resilience import (
    ErrorType,
    ErrorSeverity,
    RecoveryStrategy,
    ErrorContext,
    ResilienceConfig,
)
from ...services import observability


class RecoveryStrategist:
    """
    Intelligent recovery strategy selector that chooses optimal recovery
    approaches based on error types, context, and historical performance.
    """

    def __init__(self, config: Optional[ResilienceConfig] = None):
        """
        Initialize the recovery strategist.

        Args:
            config: Resilience configuration
        """
        self.config = config or ResilienceConfig()
        self._initialize_strategy_mappings()
        self._strategy_performance: Dict[str, Dict[str, float]] = {}

    def _initialize_strategy_mappings(self) -> None:
        """Initialize default strategy mappings for different error types."""
        self.default_strategies: Dict[ErrorType, List[RecoveryStrategy]] = {
            # Network errors - retry with backoff
            ErrorType.NETWORK_TIMEOUT: [
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.JITTERED_RETRY,
                RecoveryStrategy.CIRCUIT_BREAKER,
            ],
            ErrorType.CONNECTION_FAILED: [
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.CIRCUIT_BREAKER,
            ],
            ErrorType.DNS_RESOLUTION: [
                RecoveryStrategy.LINEAR_BACKOFF,
                RecoveryStrategy.CACHED_RESPONSE,
            ],
            # Agent errors - fallback and retry
            ErrorType.AGENT_UNAVAILABLE: [
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                RecoveryStrategy.CACHED_RESPONSE,
            ],
            ErrorType.AGENT_OVERLOADED: [
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.CIRCUIT_BREAKER,
            ],
            ErrorType.AGENT_TIMEOUT: [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
            ],
            ErrorType.AGENT_CRASHED: [
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            # LLM errors - retry and cached responses
            ErrorType.LLM_RATE_LIMITED: [
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.CACHED_RESPONSE,
            ],
            ErrorType.LLM_CONTEXT_OVERFLOW: [
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                RecoveryStrategy.PARTIAL_RESPONSE,
            ],
            ErrorType.LLM_API_ERROR: [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.CACHED_RESPONSE,
            ],
            ErrorType.LLM_QUOTA_EXCEEDED: [
                RecoveryStrategy.CACHED_RESPONSE,
                RecoveryStrategy.ESCALATE_TO_ADMIN,
            ],
            # Memory errors - cleanup and fallback
            ErrorType.MEMORY_FULL: [
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                RecoveryStrategy.PARTIAL_RESPONSE,
                RecoveryStrategy.ESCALATE_TO_ADMIN,
            ],
            ErrorType.MEMORY_ACCESS_DENIED: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            # Auth errors - re-auth and escalation
            ErrorType.AUTH_FAILED: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            ErrorType.TOKEN_EXPIRED: [
                RecoveryStrategy.IMMEDIATE_RETRY,  # Assuming auto-refresh
                RecoveryStrategy.ESCALATE_TO_ADMIN,
            ],
            ErrorType.PERMISSION_DENIED: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            # Data errors - validation and retry
            ErrorType.DATA_VALIDATION: [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                RecoveryStrategy.ERROR_MESSAGE,
            ],
            ErrorType.DATA_CORRUPTION: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            ErrorType.SERIALIZATION_ERROR: [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.FALLBACK_WORKFLOW,
            ],
            # System errors - circuit breaker and escalation
            ErrorType.SYSTEM_OVERLOAD: [
                RecoveryStrategy.CIRCUIT_BREAKER,
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
            ],
            ErrorType.DISK_FULL: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            ErrorType.CONFIGURATION_ERROR: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            # Workflow errors - retry and simplify
            ErrorType.WORKFLOW_VALIDATION: [
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                RecoveryStrategy.FALLBACK_WORKFLOW,
                RecoveryStrategy.ERROR_MESSAGE,
            ],
            ErrorType.DEPENDENCY_FAILED: [
                RecoveryStrategy.FALLBACK_WORKFLOW,
                RecoveryStrategy.PARTIAL_RESPONSE,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            ErrorType.TASK_EXECUTION: [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
            ],
            # Unknown/Critical errors - conservative approach
            ErrorType.UNKNOWN: [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
            ErrorType.CRITICAL: [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
            ],
        }

    async def select_strategy(
        self,
        error_context: ErrorContext,
        available_strategies: Optional[List[RecoveryStrategy]] = None,
    ) -> RecoveryStrategy:
        """
        Select the optimal recovery strategy for the given error context.

        Args:
            error_context: Context information about the error
            available_strategies: Optional list of available strategies

        Returns:
            Selected recovery strategy
        """
        try:
            # Check for custom strategy override
            if error_context.error_type in self.config.custom_strategies:
                strategy = self.config.custom_strategies[error_context.error_type]
                return strategy

            # Get candidate strategies
            candidates = available_strategies or self._get_candidate_strategies(error_context)

            if not candidates:
                return RecoveryStrategy.ABORT_WORKFLOW

            # Filter strategies based on configuration
            filtered_candidates = self._filter_strategies_by_config(candidates)

            if not filtered_candidates:
                return candidates[0]

            # Select best strategy based on performance and context
            selected_strategy = await self._select_best_strategy(filtered_candidates, error_context)

            #  f"Selected {selected_strategy.value} for error {error_context.error_type.value} "
            #  f"(severity: {error_context.severity.value}, attempt: {error_context.attempt_count})"
            # )

            return selected_strategy

        except Exception as selection_error:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "component": "recovery_strategist",
                    "error_type": type(selection_error).__name__,
                    "error": str(selection_error),
                },
                description="Recovery strategy selection failed, aborting workflow",
            )
            return RecoveryStrategy.ABORT_WORKFLOW

    def _get_candidate_strategies(self, error_context: ErrorContext) -> List[RecoveryStrategy]:
        """Get candidate strategies for the error type."""
        candidates = self.default_strategies.get(error_context.error_type, [])

        # Adjust candidates based on severity
        if error_context.severity == ErrorSeverity.CRITICAL:
            # For critical errors, prioritize escalation and abort
            critical_strategies = [
                RecoveryStrategy.ESCALATE_TO_ADMIN,
                RecoveryStrategy.ABORT_WORKFLOW,
                RecoveryStrategy.FAIL_FAST,
            ]
            candidates = [s for s in critical_strategies if s in candidates] + candidates

        elif error_context.severity == ErrorSeverity.LOW:
            # For low severity, prefer simple retries
            low_severity_strategies = [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.CACHED_RESPONSE,
                RecoveryStrategy.ERROR_MESSAGE,
            ]
            candidates = [s for s in low_severity_strategies if s in candidates] + candidates

        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for strategy in candidates:
            if strategy not in seen:
                seen.add(strategy)
                unique_candidates.append(strategy)

        return unique_candidates

    def _filter_strategies_by_config(
        self, candidates: List[RecoveryStrategy]
    ) -> List[RecoveryStrategy]:
        """Filter strategies based on configuration settings."""
        filtered = []

        for strategy in candidates:
            # Check if strategy type is enabled
            if strategy in [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.LINEAR_BACKOFF,
                RecoveryStrategy.JITTERED_RETRY,
            ]:
                if not self.config.enable_retries:
                    continue

            elif strategy in [
                RecoveryStrategy.FALLBACK_AGENT,
                RecoveryStrategy.FALLBACK_WORKFLOW,
                RecoveryStrategy.CACHED_RESPONSE,
            ]:
                if not self.config.enable_fallbacks:
                    continue

            elif strategy in [
                RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                RecoveryStrategy.PARTIAL_RESPONSE,
            ]:
                if not self.config.enable_graceful_degradation:
                    continue

            elif strategy == RecoveryStrategy.CIRCUIT_BREAKER:
                if not self.config.enable_circuit_breaker:
                    continue

            filtered.append(strategy)

        return filtered

    async def _select_best_strategy(
        self, candidates: List[RecoveryStrategy], error_context: ErrorContext
    ) -> RecoveryStrategy:
        """Select the best strategy from candidates based on performance and context."""

        if len(candidates) == 1:
            return candidates[0]

        # Score each strategy
        strategy_scores = {}

        for strategy in candidates:
            score = await self._calculate_strategy_score(strategy, error_context)
            strategy_scores[strategy] = score

        # Select strategy with highest score
        best_strategy = max(strategy_scores.keys(), key=lambda s: strategy_scores[s])

        return best_strategy

    async def _calculate_strategy_score(
        self, strategy: RecoveryStrategy, error_context: ErrorContext
    ) -> float:
        """Calculate a score for a strategy based on various factors."""
        score = 0.0

        # Base score from strategy priority
        strategy_priority = {
            RecoveryStrategy.CACHED_RESPONSE: 0.9,
            RecoveryStrategy.IMMEDIATE_RETRY: 0.8,
            RecoveryStrategy.FALLBACK_AGENT: 0.7,
            RecoveryStrategy.EXPONENTIAL_BACKOFF: 0.6,
            RecoveryStrategy.JITTERED_RETRY: 0.6,
            RecoveryStrategy.LINEAR_BACKOFF: 0.5,
            RecoveryStrategy.SIMPLIFIED_WORKFLOW: 0.5,
            RecoveryStrategy.FALLBACK_WORKFLOW: 0.4,
            RecoveryStrategy.PARTIAL_RESPONSE: 0.3,
            RecoveryStrategy.CIRCUIT_BREAKER: 0.3,
            RecoveryStrategy.ERROR_MESSAGE: 0.2,
            RecoveryStrategy.ESCALATE_TO_ADMIN: 0.1,
            RecoveryStrategy.ABORT_WORKFLOW: 0.05,
            RecoveryStrategy.FAIL_FAST: 0.01,
        }

        score += strategy_priority.get(strategy, 0.1)

        # Adjust based on historical performance
        performance_key = f"{error_context.error_type.value}:{strategy.value}"
        if performance_key in self._strategy_performance:
            historical_success = self._strategy_performance[performance_key]
            score *= 0.5 + historical_success  # 0.5 to 1.5 multiplier

        # Adjust based on attempt count
        if error_context.attempt_count > 1:
            # Penalize retry strategies for repeated attempts
            if strategy in [RecoveryStrategy.IMMEDIATE_RETRY, RecoveryStrategy.LINEAR_BACKOFF]:
                score *= 0.8 ** (error_context.attempt_count - 1)
            # Favor escalation for repeated failures
            elif strategy in [RecoveryStrategy.ESCALATE_TO_ADMIN, RecoveryStrategy.ABORT_WORKFLOW]:
                score *= 1.2 ** (error_context.attempt_count - 1)

        # Adjust based on severity
        if error_context.severity == ErrorSeverity.CRITICAL:
            if strategy in [RecoveryStrategy.ESCALATE_TO_ADMIN, RecoveryStrategy.ABORT_WORKFLOW]:
                score *= 1.5
            elif strategy in [RecoveryStrategy.IMMEDIATE_RETRY, RecoveryStrategy.CACHED_RESPONSE]:
                score *= 0.5

        elif error_context.severity == ErrorSeverity.LOW:
            if strategy in [RecoveryStrategy.IMMEDIATE_RETRY, RecoveryStrategy.CACHED_RESPONSE]:
                score *= 1.3
            elif strategy in [RecoveryStrategy.ESCALATE_TO_ADMIN, RecoveryStrategy.ABORT_WORKFLOW]:
                score *= 0.3

        return score

    async def record_strategy_result(
        self, error_type: ErrorType, strategy: RecoveryStrategy, success: bool
    ) -> None:
        """Record the result of a recovery strategy for future selection."""
        performance_key = f"{error_type.value}:{strategy.value}"

        if performance_key not in self._strategy_performance:
            self._strategy_performance[performance_key] = 0.5  # Start neutral

        # Update performance with exponential moving average
        current_performance = self._strategy_performance[performance_key]
        new_result = 1.0 if success else 0.0
        alpha = 0.1  # Learning rate

        self._strategy_performance[performance_key] = (
            1 - alpha
        ) * current_performance + alpha * new_result

        #     f"Updated strategy performance: {performance_key} = "
        #     f"{self._strategy_performance[performance_key]:.3f} (success: {success})"
        # )

    def get_strategy_performance(self) -> Dict[str, float]:
        """Get current strategy performance metrics."""
        return self._strategy_performance.copy()

    def reset_strategy_performance(self) -> None:
        """Reset all strategy performance metrics."""
        self._strategy_performance.clear()

    def add_custom_strategy_mapping(
        self, error_type: ErrorType, strategies: List[RecoveryStrategy]
    ) -> None:
        """Add or update custom strategy mapping for an error type."""
        self.default_strategies[error_type] = strategies

    def get_available_strategies(self, error_type: ErrorType) -> List[RecoveryStrategy]:
        """Get available strategies for a specific error type."""
        return self.default_strategies.get(error_type, [RecoveryStrategy.ABORT_WORKFLOW])
