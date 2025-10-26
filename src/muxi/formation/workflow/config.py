"""
Enhanced workflow configuration and error handling for MUXI Runtime.

This module provides advanced configuration options for the workflow system including:
- Custom complexity calculation methods
- Task routing strategies
- Retry and timeout configuration
- Error recovery strategies
- Workflow-specific configuration overrides
"""

from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from datetime import datetime, timezone
import asyncio


class WorkflowTimeoutConfigError(ValueError):
    """Exception raised when workflow_timeout exceeds max_timeout_seconds."""

    def __init__(self, workflow_timeout: float, max_timeout_seconds: float):
        self.workflow_timeout = workflow_timeout
        self.max_timeout_seconds = max_timeout_seconds
        message = (
            f"workflow_timeout ({workflow_timeout}s) cannot exceed "
            f"max_timeout_seconds ({max_timeout_seconds}s). "
            f"Please reduce workflow_timeout or increase max_timeout_seconds."
        )
        super().__init__(message)


class TaskRoutingStrategy(Enum):
    """Available task routing strategies"""

    CAPABILITY_BASED = "capability_based"  # Route based on agent capabilities
    LOAD_BALANCED = "load_balanced"  # Distribute tasks evenly
    PRIORITY_BASED = "priority_based"  # Route based on task priority
    CUSTOM = "custom"  # Custom routing function
    ROUND_ROBIN = "round_robin"  # Simple round-robin assignment
    SPECIALIZED = "specialized"  # Route to most specialized agent


class ErrorRecoveryStrategy(Enum):
    """Error recovery strategies for failed tasks"""

    FAIL_FAST = "fail_fast"  # Stop workflow on first failure
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Exponential backoff retry
    RETRY_WITH_ALTERNATE = "retry_with_alternate"  # Try different agent
    SKIP_AND_CONTINUE = "skip_and_continue"  # Skip failed task if non-critical
    COMPENSATE = "compensate"  # Run compensation logic
    MANUAL_INTERVENTION = "manual_intervention"  # Request user intervention


class RetryConfig(BaseModel):
    """Configuration for task retry logic"""

    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    initial_delay: float = Field(default=1.0, ge=0.1, description="Initial retry delay in seconds")
    max_delay: float = Field(default=60.0, ge=1.0, description="Maximum retry delay in seconds")
    backoff_factor: float = Field(default=2.0, ge=1.0, description="Exponential backoff factor")
    retry_on_errors: List[str] = Field(
        default_factory=lambda: ["timeout", "rate_limit", "temporary_failure"],
        description="Error types to retry on",
    )

    model_config = ConfigDict(extra="forbid")


class TimeoutConfig(BaseModel):
    """Configuration for task and workflow timeouts"""

    task_timeout: Optional[float] = Field(
        default=300.0, ge=1.0, description="Default timeout per task in seconds"
    )
    workflow_timeout: Optional[float] = Field(
        default=3600.0, ge=1.0, description="Overall workflow timeout in seconds"
    )
    phase_timeout: Optional[float] = Field(
        default=600.0, ge=1.0, description="Timeout per execution phase in seconds"
    )
    max_timeout_seconds: Optional[float] = Field(
        default=7200.0, ge=1.0, description="Hard maximum timeout for entire workflow (2 hours)"
    )
    enable_adaptive_timeout: bool = Field(
        default=True, description="Adjust timeouts based on task complexity"
    )
    timeout_multiplier: float = Field(
        default=1.5, ge=1.0, description="Multiplier for complexity-based timeout adjustment"
    )

    @model_validator(mode="after")
    def validate_workflow_timeout(self):
        """Ensure workflow_timeout doesn't exceed max_timeout_seconds"""
        if (
            self.workflow_timeout is not None
            and self.max_timeout_seconds is not None
            and self.workflow_timeout > self.max_timeout_seconds
        ):
            raise WorkflowTimeoutConfigError(self.workflow_timeout, self.max_timeout_seconds)
        return self

    model_config = ConfigDict(extra="forbid")


class ComplexityConfig(BaseModel):
    """Configuration for complexity calculation"""

    method: str = Field(default="llm", description="Method for calculating request complexity")
    threshold: float = Field(
        default=7.0, ge=1.0, le=10.0, description="Threshold for triggering workflow decomposition"
    )
    weights: Dict[str, float] = Field(
        default_factory=lambda: {"heuristic": 0.4, "llm": 0.4, "custom": 0.2},
        description="Weights for hybrid complexity calculation",
    )

    @field_validator("method")
    @classmethod
    def validate_complexity_method(cls, v):
        """Validate complexity method"""
        valid_methods = ["heuristic", "llm", "custom", "hybrid"]
        if v not in valid_methods:
            raise ValueError(
                f"Invalid complexity method. Must be one of: {', '.join(valid_methods)}"
            )
        return v

    model_config = ConfigDict(extra="forbid")


class RoutingConfig(BaseModel):
    """Configuration for task routing"""

    strategy: TaskRoutingStrategy = Field(
        default=TaskRoutingStrategy.CAPABILITY_BASED,
        description="Strategy for routing tasks to agents",
    )
    enable_agent_affinity: bool = Field(
        default=True, description="Prefer agents that successfully completed similar tasks"
    )

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ResourceConfig(BaseModel):
    """Configuration for resource management"""

    enable_limits: bool = Field(default=False, description="Enable resource usage limits")
    max_memory_per_task_mb: Optional[int] = Field(
        default=None, ge=64, description="Maximum memory per task in MB"
    )
    max_cpu_per_task: Optional[float] = Field(
        default=None, ge=0.1, le=1.0, description="Maximum CPU allocation per task (0-1)"
    )

    model_config = ConfigDict(extra="forbid")


class ObservabilityConfig(BaseModel):
    """Configuration for monitoring and observability"""

    enable_detailed_logging: bool = Field(
        default=True, description="Enable detailed workflow execution logging"
    )
    log_task_inputs_outputs: bool = Field(
        default=False, description="Log task inputs and outputs (may contain sensitive data)"
    )
    enable_metrics_collection: bool = Field(
        default=True, description="Collect detailed execution metrics"
    )

    model_config = ConfigDict(extra="forbid")


class WorkflowBehaviorConfig(BaseModel):
    """Configuration for workflow execution behavior"""

    enable_parallel_execution: bool = Field(
        default=True, description="Execute independent tasks in parallel"
    )
    max_parallel_tasks: int = Field(
        default=5, ge=1, le=20, description="Maximum number of tasks to execute in parallel"
    )
    enable_partial_results: bool = Field(
        default=True, description="Return partial results if some tasks fail"
    )

    model_config = ConfigDict(extra="forbid")


class WorkflowConfig(BaseModel):
    """Enhanced configuration for workflow execution"""

    # Nested configuration models
    complexity: ComplexityConfig = Field(
        default_factory=ComplexityConfig, description="Configuration for complexity calculation"
    )
    routing: RoutingConfig = Field(
        default_factory=RoutingConfig, description="Configuration for task routing"
    )
    resources: ResourceConfig = Field(
        default_factory=ResourceConfig, description="Configuration for resource management"
    )
    observability: ObservabilityConfig = Field(
        default_factory=ObservabilityConfig,
        description="Configuration for monitoring and observability",
    )
    behavior: WorkflowBehaviorConfig = Field(
        default_factory=WorkflowBehaviorConfig,
        description="Configuration for workflow execution behavior",
    )
    timeout: TimeoutConfig = Field(
        default_factory=TimeoutConfig, description="Configuration for timeouts"
    )

    # Error handling (kept at top level as it's fundamental)
    error_recovery_strategy: ErrorRecoveryStrategy = Field(
        default=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
        description="Strategy for handling task failures",
    )
    retry_config: RetryConfig = Field(
        default_factory=RetryConfig, description="Configuration for retry logic"
    )

    @property
    def complexity_method(self) -> str:
        """Backward compatibility for complexity_method"""
        return self.complexity.method

    @property
    def complexity_threshold(self) -> float:
        """Backward compatibility for complexity_threshold"""
        return self.complexity.threshold

    @property
    def complexity_weights(self) -> Dict[str, float]:
        """Backward compatibility for complexity_weights"""
        return self.complexity.weights

    @property
    def routing_strategy(self) -> TaskRoutingStrategy:
        """Backward compatibility for routing_strategy"""
        return self.routing.strategy

    @property
    def enable_agent_affinity(self) -> bool:
        """Backward compatibility for enable_agent_affinity"""
        return self.routing.enable_agent_affinity

    @property
    def timeout_config(self) -> TimeoutConfig:
        """Backward compatibility for timeout_config"""
        return self.timeout

    @property
    def enable_parallel_execution(self) -> bool:
        """Backward compatibility for enable_parallel_execution"""
        return self.behavior.enable_parallel_execution

    @property
    def max_parallel_tasks(self) -> int:
        """Backward compatibility for max_parallel_tasks"""
        return self.behavior.max_parallel_tasks

    @property
    def enable_partial_results(self) -> bool:
        """Backward compatibility for enable_partial_results"""
        return self.behavior.enable_partial_results

    @property
    def enable_resource_limits(self) -> bool:
        """Backward compatibility for enable_resource_limits"""
        return self.resources.enable_limits

    @property
    def max_memory_per_task_mb(self) -> Optional[int]:
        """Backward compatibility for max_memory_per_task_mb"""
        return self.resources.max_memory_per_task_mb

    @property
    def max_cpu_per_task(self) -> Optional[float]:
        """Backward compatibility for max_cpu_per_task"""
        return self.resources.max_cpu_per_task

    @property
    def enable_detailed_logging(self) -> bool:
        """Backward compatibility for enable_detailed_logging"""
        return self.observability.enable_detailed_logging

    @property
    def log_task_inputs_outputs(self) -> bool:
        """Backward compatibility for log_task_inputs_outputs"""
        return self.observability.log_task_inputs_outputs

    @property
    def enable_metrics_collection(self) -> bool:
        """Backward compatibility for enable_metrics_collection"""
        return self.observability.enable_metrics_collection

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class WorkflowOverride(BaseModel):
    """Workflow-specific configuration overrides"""

    workflow_pattern: str = Field(..., description="Pattern to match workflow ID or user request")
    config_overrides: Dict[str, Any] = Field(..., description="Configuration values to override")
    priority: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Priority for applying overrides (higher = applied first)",
    )

    model_config = ConfigDict(extra="forbid")


class AgentRoutingRule(BaseModel):
    """Custom routing rule for task assignment"""

    task_pattern: str = Field(..., description="Pattern to match task description or capabilities")
    preferred_agents: List[str] = Field(..., description="Ordered list of preferred agent IDs")
    required_capabilities: List[str] = Field(
        default_factory=list, description="Required capabilities for the agent"
    )
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Weight for this routing rule")

    model_config = ConfigDict(extra="forbid")


class WorkflowErrorHandler:
    """Enhanced error handling for workflow execution.

    This handler classifies errors using a multi-tier approach:
    1. Built-in exception type checking (TimeoutError, ConnectionError, etc.)
    2. Known library exception types by class name
    3. HTTP status codes from response objects
    4. Error attributes and properties
    5. String matching as a last resort fallback

    This approach is more reliable than pure string matching and handles
    errors from various sources consistently.
    """

    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.retry_attempts: Dict[str, int] = {}
        self.error_history: Dict[str, List[Dict[str, Any]]] = {}

    async def handle_task_error(
        self, task_id: str, error: Exception, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle task execution error with configured strategy.

        Args:
            task_id: ID of the failed task
            error: The exception that occurred
            context: Execution context

        Returns:
            Dictionary with recovery action and metadata
        """
        error_type = self._classify_error(error)
        attempts = self.retry_attempts.get(task_id, 0)

        # Record error in history
        if task_id not in self.error_history:
            self.error_history[task_id] = []

        self.error_history[task_id].append(
            {
                "error_type": error_type,
                "error_message": str(error),
                "attempt": attempts + 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Apply recovery strategy
        strategy = self.config.error_recovery_strategy

        if strategy == ErrorRecoveryStrategy.FAIL_FAST:
            return {"action": "fail", "reason": "fail_fast_strategy"}

        elif strategy == ErrorRecoveryStrategy.RETRY_WITH_BACKOFF:
            if (
                attempts < self.config.retry_config.max_attempts
                and error_type in self.config.retry_config.retry_on_errors
            ):
                delay = self._calculate_backoff_delay(attempts)
                self.retry_attempts[task_id] = attempts + 1
                return {
                    "action": "retry",
                    "delay": delay,
                    "attempt": attempts + 1,
                    "max_attempts": self.config.retry_config.max_attempts,
                }
            else:
                return {"action": "fail", "reason": "max_retries_exceeded"}

        elif strategy == ErrorRecoveryStrategy.RETRY_WITH_ALTERNATE:
            if attempts < self.config.retry_config.max_attempts:
                self.retry_attempts[task_id] = attempts + 1
                return {
                    "action": "retry_alternate",
                    "attempt": attempts + 1,
                    "use_different_agent": True,
                }
            else:
                return {"action": "fail", "reason": "no_alternate_agents"}

        elif strategy == ErrorRecoveryStrategy.SKIP_AND_CONTINUE:
            if context.get("task_critical", True):
                return {"action": "fail", "reason": "critical_task_failed"}
            else:
                return {"action": "skip", "reason": "non_critical_task_skipped"}

        elif strategy == ErrorRecoveryStrategy.COMPENSATE:
            return {"action": "compensate", "compensation_task": f"compensate_{task_id}"}

        elif strategy == ErrorRecoveryStrategy.MANUAL_INTERVENTION:
            return {
                "action": "manual_intervention",
                "error_details": str(error),
                "request_user_action": True,
            }

        # Default fallback
        return {"action": "fail", "reason": "unknown_strategy"}

    def _classify_error(self, error: Exception) -> str:
        """Classify error type for retry decisions using exception types."""
        # Check for timeout errors
        if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
            return "timeout"

        # Check for common timeout exceptions from libraries
        if type(error).__name__ in [
            "OneLLMTimeoutError",
            "MCPTimeoutError",
            "OperationTimeoutError",
        ]:
            return "timeout"

        # Check for connection/network errors
        if isinstance(error, (ConnectionError, OSError)):
            return "network_error"

        # Check for common connection exceptions from libraries
        if type(error).__name__ in ["OneLLMConnectionError", "MCPConnectionError"]:
            return "network_error"

        # Check for permission/authentication errors
        if isinstance(error, PermissionError):
            return "permission_error"

        # Check for common auth exceptions from libraries
        if type(error).__name__ in ["OneLLMAuthenticationError", "SecretPermissionError"]:
            return "permission_error"

        # Check for rate limit errors
        if type(error).__name__ in ["OneLLMRateLimitError"]:
            return "rate_limit"

        # Check for HTTP errors with status codes
        if hasattr(error, "response") and hasattr(error.response, "status_code"):
            status_code = error.response.status_code
            if status_code == 429:
                return "rate_limit"
            elif status_code in [401, 403]:
                return "permission_error"
            elif status_code in [500, 502, 503, 504]:
                return "temporary_failure"
            elif status_code >= 400:
                return "client_error"

        # Check error attributes for additional classification
        if hasattr(error, "error_type"):
            error_type = str(error.error_type).lower()
            if "timeout" in error_type:
                return "timeout"
            elif "rate" in error_type and "limit" in error_type:
                return "rate_limit"
            elif "network" in error_type or "connection" in error_type:
                return "network_error"
            elif "auth" in error_type or "permission" in error_type:
                return "permission_error"

        # Fallback to string matching as last resort for unknown exception types
        error_str = str(error).lower()
        if "timeout" in error_str:
            return "timeout"
        elif "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        elif "connection" in error_str or "network" in error_str:
            return "network_error"
        elif (
            "permission" in error_str
            or "unauthorized" in error_str
            or "401" in error_str
            or "403" in error_str
        ):
            return "permission_error"
        elif "temporary" in error_str or "retry" in error_str or "503" in error_str:
            return "temporary_failure"

        return "unknown_error"

    def _calculate_backoff_delay(self, attempts: int) -> float:
        """Calculate exponential backoff delay"""
        config = self.config.retry_config
        delay = min(config.initial_delay * (config.backoff_factor**attempts), config.max_delay)
        return delay

    def get_error_summary(self, task_id: str) -> Dict[str, Any]:
        """Get error summary for a task"""
        if task_id not in self.error_history:
            return {"has_errors": False}

        errors = self.error_history[task_id]
        return {
            "has_errors": True,
            "total_errors": len(errors),
            "error_types": list(set(e["error_type"] for e in errors)),
            "last_error": errors[-1] if errors else None,
            "all_errors": errors,
        }

    def reset_task_retries(self, task_id: str):
        """Reset retry counter for a task"""
        if task_id in self.retry_attempts:
            del self.retry_attempts[task_id]
        if task_id in self.error_history:
            del self.error_history[task_id]


class WorkflowConfigManager:
    """Manage workflow configurations with custom functions"""

    def __init__(self, base_config: WorkflowConfig):
        self.base_config = base_config
        self.custom_complexity_fn: Optional[Callable] = None
        self.custom_routing_fn: Optional[Callable] = None

    def set_custom_complexity_function(self, fn: Callable[[str, Optional[Dict[str, Any]]], float]):
        """Set custom complexity calculation function"""
        self.custom_complexity_fn = fn

    def set_custom_routing_function(self, fn: Callable[[Any, List[Any]], str]):
        """Set custom task routing function"""
        self.custom_routing_fn = fn

    def get_config_for_workflow(self, workflow_id: str, user_request: str) -> WorkflowConfig:
        """Get configuration for a specific workflow (currently just returns base config)"""
        return self.base_config
