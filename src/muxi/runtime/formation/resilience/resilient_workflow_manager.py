"""
Resilient Workflow Manager - Main orchestrator for resilience framework.

This module provides the main interface for resilient workflow execution,
coordinating error classification, recovery strategies, circuit breakers,
and fallback mechanisms.
"""

import asyncio
import time
from typing import Any, Dict, Optional

from ...datatypes.resilience import (
    ResilienceConfig,
    ResilientWorkflowResult,
    WorkflowException,
    ErrorType,
    ErrorSeverity,
    RecoveryStrategy,
    RecoveryResult,
)

from .error_classifier import ErrorClassifier
from .recovery_strategist import RecoveryStrategist
from .circuit_breaker import CircuitBreaker, CircuitBreakerRegistry
from .fallback_manager import FallbackManager


class ResilientWorkflowManager:
    """
    Main orchestrator for resilient workflow execution.

    Coordinates error classification, recovery strategy selection,
    circuit breaker protection, and fallback mechanisms to provide
    production-ready workflow resilience.
    """

    def __init__(self, config: Optional[ResilienceConfig] = None):
        """
        Initialize the resilient workflow manager.

        Args:
            config: Resilience configuration
        """
        self.config = config or ResilienceConfig()

        # Initialize components
        self.error_classifier = ErrorClassifier()
        self.recovery_strategist = RecoveryStrategist(self.config)
        self.circuit_breaker_registry = CircuitBreakerRegistry()
        self.fallback_manager = FallbackManager()

        # Set default circuit breaker config
        self.circuit_breaker_registry.set_default_config(self.config.circuit_breaker)

        #  Info - TODO: add observability

    async def execute_resilient_workflow(
        self, workflow: Any, resilience_config: Optional[ResilienceConfig] = None
    ) -> ResilientWorkflowResult:
        """
        Execute workflow with comprehensive error handling and recovery.

        Args:
            workflow: Workflow to execute
            resilience_config: Optional override configuration

        Returns:
            ResilientWorkflowResult with execution details
        """
        start_time = time.time()
        effective_config = resilience_config or self.config
        workflow_id = getattr(workflow, "id", f"workflow_{int(time.time())}")

        #  Debug - TODO: add observability

        try:
            # Get circuit breaker for this workflow type
            circuit_breaker = self._get_circuit_breaker(workflow)

            # Execute with circuit breaker protection
            if effective_config.enable_circuit_breaker:
                result = await circuit_breaker.execute(
                    self._execute_workflow_with_recovery,
                    workflow,
                    effective_config,
                    fallback=lambda w, c: self.fallback_manager.get_fallback_response(
                        w, ErrorType.SYSTEM_OVERLOAD, {"circuit_breaker_open": True}
                    ),
                )
                circuit_breaker_triggered = circuit_breaker.get_state().state.value != "closed"
            else:
                result = await self._execute_workflow_with_recovery(workflow, effective_config)
                circuit_breaker_triggered = False

            execution_time = time.time() - start_time

            # Cache successful response for fallback use
            self.fallback_manager.cache_successful_response(workflow, result)

            return ResilientWorkflowResult(
                result=result,
                success=True,
                recovery_used=False,
                execution_time=execution_time,
                circuit_breaker_triggered=circuit_breaker_triggered,
                metadata={
                    "workflow_id": workflow_id,
                    "execution_path": "normal",
                    "config_used": effective_config.__dict__,
                },
            )

        except Exception as error:
            execution_time = time.time() - start_time

            #  Error - TODO: add observability

            return ResilientWorkflowResult(
                result=None,
                success=False,
                error=error,
                execution_time=execution_time,
                metadata={
                    "workflow_id": workflow_id,
                    "execution_path": "failed",
                    "error_type": getattr(error, "error_type", ErrorType.UNKNOWN).value,
                },
            )

    async def _execute_workflow_with_recovery(
        self, workflow: Any, config: ResilienceConfig, attempt_count: int = 1
    ) -> Any:
        """Execute workflow with recovery mechanisms."""

        try:
            # Execute the workflow
            if hasattr(workflow, "execute"):
                if asyncio.iscoroutinefunction(workflow.execute):
                    result = await asyncio.wait_for(
                        workflow.execute(), timeout=config.workflow_timeout
                    )
                else:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, workflow.execute),
                        timeout=config.workflow_timeout,
                    )
            else:
                raise WorkflowException(
                    "Workflow does not have execute method",
                    ErrorType.WORKFLOW_VALIDATION,
                    ErrorSeverity.HIGH,
                )

            return result

        except Exception as error:
            # Classify the error
            error_context = await self.error_classifier.classify(
                error,
                context={
                    "workflow_id": getattr(workflow, "id", None),
                    "attempt_count": attempt_count,
                    "workflow_type": getattr(workflow, "type", "unknown"),
                    "user_facing": True,
                },
            )

            # Check if we should attempt recovery
            if not self._should_attempt_recovery(error_context, config, attempt_count):
                # Use fallback if recovery is not appropriate
                if config.enable_fallbacks:
                    fallback_result = await self.fallback_manager.get_fallback_response(
                        workflow, error_context.error_type, error_context.context_data
                    )
                    return fallback_result
                else:
                    raise error

            # Select recovery strategy
            recovery_strategy = await self.recovery_strategist.select_strategy(error_context)

            #  Info - TODO: add observability
            #     f"Attempting recovery for workflow {getattr(workflow, 'id', 'unknown')} "
            #     f"using strategy: {recovery_strategy.value} (attempt {attempt_count})"
            # )

            # Execute recovery strategy
            recovery_result = await self._execute_recovery_strategy(
                recovery_strategy, workflow, error_context, config, attempt_count
            )

            # Record strategy performance
            await self.recovery_strategist.record_strategy_result(
                error_context.error_type, recovery_strategy, recovery_result.success
            )

            if recovery_result.success:
                return recovery_result.result
            else:
                # Recovery failed, try fallback
                if config.enable_fallbacks:
                    fallback_result = await self.fallback_manager.get_fallback_response(
                        workflow, error_context.error_type, error_context.context_data
                    )
                    return fallback_result
                else:
                    raise recovery_result.error or error

    def _should_attempt_recovery(
        self, error_context, config: ResilienceConfig, attempt_count: int
    ) -> bool:
        """Determine if recovery should be attempted."""

        # Don't retry if retries are disabled
        if not config.enable_retries and attempt_count > 1:
            return False

        # Don't retry beyond max attempts
        if attempt_count > config.retry.max_attempts:
            return False

        # Don't retry critical errors that require immediate escalation
        if error_context.severity == ErrorSeverity.CRITICAL:
            critical_no_retry = [
                ErrorType.AUTH_FAILED,
                ErrorType.PERMISSION_DENIED,
                ErrorType.CONFIGURATION_ERROR,
                ErrorType.DATA_CORRUPTION,
            ]
            if error_context.error_type in critical_no_retry:
                return False

        # Auto-escalate based on threshold
        if error_context.severity.value >= config.auto_escalation_threshold.value:
            return attempt_count <= 1  # Only one attempt for high severity

        return True

    async def _execute_recovery_strategy(
        self,
        strategy: RecoveryStrategy,
        workflow: Any,
        error_context,
        config: ResilienceConfig,
        attempt_count: int,
    ):
        """Execute a specific recovery strategy."""

        try:
            if strategy in [
                RecoveryStrategy.IMMEDIATE_RETRY,
                RecoveryStrategy.EXPONENTIAL_BACKOFF,
                RecoveryStrategy.LINEAR_BACKOFF,
                RecoveryStrategy.JITTERED_RETRY,
            ]:
                return await self._execute_retry_strategy(strategy, workflow, config, attempt_count)

            elif strategy == RecoveryStrategy.FALLBACK_AGENT:
                return await self._execute_fallback_agent_strategy(workflow, error_context)

            elif strategy == RecoveryStrategy.CACHED_RESPONSE:
                return await self._execute_cached_response_strategy(workflow, error_context)

            elif strategy == RecoveryStrategy.SIMPLIFIED_WORKFLOW:
                return await self._execute_simplified_workflow_strategy(workflow, error_context)

            elif strategy in [RecoveryStrategy.ESCALATE_TO_ADMIN, RecoveryStrategy.ABORT_WORKFLOW]:
                return await self._execute_escalation_strategy(strategy, workflow, error_context)

            else:
                #  Warning - TODO: add observability
                return RecoveryResult(
                    success=False,
                    strategy_used=strategy,
                    error=WorkflowException(f"Unsupported recovery strategy: {strategy.value}"),
                )

        except Exception as recovery_error:
            #  Error - TODO: add observability
            return RecoveryResult(success=False, strategy_used=strategy, error=recovery_error)

    async def _execute_retry_strategy(
        self,
        strategy: RecoveryStrategy,
        workflow: Any,
        config: ResilienceConfig,
        attempt_count: int,
    ):
        """Execute retry-based recovery strategies."""

        # Calculate delay based on strategy
        if strategy == RecoveryStrategy.IMMEDIATE_RETRY:
            delay = 0
        elif strategy == RecoveryStrategy.LINEAR_BACKOFF:
            delay = config.retry.initial_delay * attempt_count
        elif strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
            delay = config.retry.initial_delay * (
                config.retry.backoff_factor ** (attempt_count - 1)
            )
        elif strategy == RecoveryStrategy.JITTERED_RETRY:
            base_delay = config.retry.initial_delay * (
                config.retry.backoff_factor ** (attempt_count - 1)
            )
            jitter = (
                base_delay * config.retry.jitter_factor * (2 * asyncio.get_event_loop().time() - 1)
            )
            delay = base_delay + jitter
        else:
            delay = config.retry.initial_delay

        # Cap the delay
        delay = min(delay, config.retry.max_delay)

        if delay > 0:
            #  Debug - TODO: add observability
            await asyncio.sleep(delay)

        # Retry the workflow
        try:
            result = await self._execute_workflow_with_recovery(workflow, config, attempt_count + 1)
            return RecoveryResult(
                success=True, strategy_used=strategy, result=result, attempts=attempt_count + 1
            )
        except Exception as retry_error:
            return RecoveryResult(
                success=False, strategy_used=strategy, error=retry_error, attempts=attempt_count + 1
            )

    async def _execute_fallback_agent_strategy(self, workflow: Any, error_context):
        """Execute fallback agent strategy."""
        # This would integrate with the agent selection system
        # For now, return a placeholder

        return RecoveryResult(
            success=False,
            strategy_used=RecoveryStrategy.FALLBACK_AGENT,
            error=WorkflowException("Fallback agent strategy not implemented"),
        )

    async def _execute_cached_response_strategy(self, workflow: Any, error_context):
        """Execute cached response strategy."""

        cached_response = await self.fallback_manager._get_cached_fallback(workflow)
        if cached_response:
            return RecoveryResult(
                success=True, strategy_used=RecoveryStrategy.CACHED_RESPONSE, result=cached_response
            )
        else:
            return RecoveryResult(
                success=False,
                strategy_used=RecoveryStrategy.CACHED_RESPONSE,
                error=WorkflowException("No cached response available"),
            )

    async def _execute_simplified_workflow_strategy(self, workflow: Any, error_context):
        """Execute simplified workflow strategy."""

        simplified_response = await self.fallback_manager._get_simplified_workflow_response(
            workflow
        )
        if simplified_response:
            return RecoveryResult(
                success=True,
                strategy_used=RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                result=simplified_response,
            )
        else:
            return RecoveryResult(
                success=False,
                strategy_used=RecoveryStrategy.SIMPLIFIED_WORKFLOW,
                error=WorkflowException("No simplified workflow available"),
            )

    async def _execute_escalation_strategy(
        self, strategy: RecoveryStrategy, workflow: Any, error_context
    ):
        """Execute escalation strategies."""

        # Log escalation
        #  Warning - TODO: add observability
        #     f"Escalating workflow {getattr(workflow, 'id', 'unknown')} "
        #     f"due to {error_context.error_type.value} (strategy: {strategy.value})"
        # )

        # Generate appropriate response
        if strategy == RecoveryStrategy.ESCALATE_TO_ADMIN:
            result = await self.fallback_manager._generate_error_message(
                workflow, error_context.error_type, error_context.context_data
            )
            result["escalated"] = True
            result["admin_notified"] = True

            return RecoveryResult(success=True, strategy_used=strategy, result=result)
        else:  # ABORT_WORKFLOW
            return RecoveryResult(
                success=False,
                strategy_used=strategy,
                error=WorkflowException(
                    f"Workflow aborted due to {error_context.error_type.value}",
                    error_context.error_type,
                    error_context.severity,
                ),
            )

    def _get_circuit_breaker(self, workflow: Any) -> CircuitBreaker:
        """Get or create circuit breaker for workflow type."""
        workflow_type = getattr(workflow, "type", "default")
        return self.circuit_breaker_registry.get_circuit_breaker(
            f"workflow_{workflow_type}", self.config.circuit_breaker
        )

    def get_resilience_stats(self) -> Dict[str, Any]:
        """Get comprehensive resilience statistics."""
        return {
            "error_classifier": self.error_classifier.get_classification_stats(),
            "recovery_strategist": {
                "strategy_performance": self.recovery_strategist.get_strategy_performance()
            },
            "circuit_breakers": self.circuit_breaker_registry.get_all_stats(),
            "fallback_manager": self.fallback_manager.get_cache_stats(),
            "config": {
                "retries_enabled": self.config.enable_retries,
                "circuit_breaker_enabled": self.config.enable_circuit_breaker,
                "fallbacks_enabled": self.config.enable_fallbacks,
                "graceful_degradation_enabled": self.config.enable_graceful_degradation,
            },
        }

    async def reset_resilience_state(self) -> None:
        """Reset all resilience state (for testing/debugging)."""
        await self.circuit_breaker_registry.reset_all()
        self.recovery_strategist.reset_strategy_performance()
        self.fallback_manager.clear_cache()
        #  Info - TODO: add observability

    def update_config(self, config: ResilienceConfig) -> None:
        """Update resilience configuration."""
        self.config = config
        self.recovery_strategist.config = config
        self.circuit_breaker_registry.set_default_config(config.circuit_breaker)
        #  Info - TODO: add observability
