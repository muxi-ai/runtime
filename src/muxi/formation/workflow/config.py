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
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime


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
        description="Error types to retry on"
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
    enable_adaptive_timeout: bool = Field(
        default=True, description="Adjust timeouts based on task complexity"
    )
    timeout_multiplier: float = Field(
        default=1.5, ge=1.0, description="Multiplier for complexity-based timeout adjustment"
    )

    model_config = ConfigDict(extra="forbid")


class WorkflowConfig(BaseModel):
    """Enhanced configuration for workflow execution"""

    # Complexity calculation
    complexity_method: str = Field(
        default="heuristic",
        description="Method for calculating request complexity"
    )
    complexity_threshold: float = Field(
        default=7.0, ge=1.0, le=10.0,
        description="Threshold for triggering workflow decomposition"
    )
    complexity_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "heuristic": 0.4,
            "llm": 0.4,
            "custom": 0.2
        },
        description="Weights for hybrid complexity calculation"
    )

    # Task routing
    routing_strategy: TaskRoutingStrategy = Field(
        default=TaskRoutingStrategy.CAPABILITY_BASED,
        description="Strategy for routing tasks to agents"
    )
    enable_agent_affinity: bool = Field(
        default=True,
        description="Prefer agents that successfully completed similar tasks"
    )

    # Error handling
    error_recovery_strategy: ErrorRecoveryStrategy = Field(
        default=ErrorRecoveryStrategy.RETRY_WITH_BACKOFF,
        description="Strategy for handling task failures"
    )
    retry_config: RetryConfig = Field(
        default_factory=RetryConfig,
        description="Configuration for retry logic"
    )

    # Timeouts
    timeout_config: TimeoutConfig = Field(
        default_factory=TimeoutConfig,
        description="Configuration for timeouts"
    )

    # Workflow behavior
    enable_parallel_execution: bool = Field(
        default=True,
        description="Execute independent tasks in parallel"
    )
    max_parallel_tasks: int = Field(
        default=5, ge=1, le=20,
        description="Maximum number of tasks to execute in parallel"
    )
    enable_partial_results: bool = Field(
        default=True,
        description="Return partial results if some tasks fail"
    )

    # Resource management
    enable_resource_limits: bool = Field(
        default=False,
        description="Enable resource usage limits"
    )
    max_memory_per_task_mb: Optional[int] = Field(
        default=None, ge=64,
        description="Maximum memory per task in MB"
    )
    max_cpu_per_task: Optional[float] = Field(
        default=None, ge=0.1, le=1.0,
        description="Maximum CPU allocation per task (0-1)"
    )

    # Monitoring and observability
    enable_detailed_logging: bool = Field(
        default=True,
        description="Enable detailed workflow execution logging"
    )
    log_task_inputs_outputs: bool = Field(
        default=False,
        description="Log task inputs and outputs (may contain sensitive data)"
    )
    enable_metrics_collection: bool = Field(
        default=True,
        description="Collect detailed execution metrics"
    )

    @field_validator("complexity_method")
    @classmethod
    def validate_complexity_method(cls, v):
        """Validate complexity method"""
        valid_methods = ["heuristic", "llm", "custom", "hybrid"]
        if v not in valid_methods:
            raise ValueError(f"Invalid complexity method. Must be one of: {', '.join(valid_methods)}")
        return v

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True
    )


class WorkflowOverride(BaseModel):
    """Workflow-specific configuration overrides"""
    workflow_pattern: str = Field(
        ..., description="Pattern to match workflow ID or user request"
    )
    config_overrides: Dict[str, Any] = Field(
        ..., description="Configuration values to override"
    )
    priority: int = Field(
        default=0, ge=0, le=100,
        description="Priority for applying overrides (higher = applied first)"
    )

    model_config = ConfigDict(extra="forbid")


class AgentRoutingRule(BaseModel):
    """Custom routing rule for task assignment"""
    task_pattern: str = Field(
        ..., description="Pattern to match task description or capabilities"
    )
    preferred_agents: List[str] = Field(
        ..., description="Ordered list of preferred agent IDs"
    )
    required_capabilities: List[str] = Field(
        default_factory=list,
        description="Required capabilities for the agent"
    )
    weight: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Weight for this routing rule"
    )

    model_config = ConfigDict(extra="forbid")


class WorkflowErrorHandler:
    """Enhanced error handling for workflow execution"""

    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.retry_attempts: Dict[str, int] = {}
        self.error_history: Dict[str, List[Dict[str, Any]]] = {}

    async def handle_task_error(
        self,
        task_id: str,
        error: Exception,
        context: Dict[str, Any]
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

        self.error_history[task_id].append({
            "error_type": error_type,
            "error_message": str(error),
            "attempt": attempts + 1,
            "timestamp": datetime.now().isoformat()
        })

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
                    "max_attempts": self.config.retry_config.max_attempts
                }
            else:
                return {"action": "fail", "reason": "max_retries_exceeded"}

        elif strategy == ErrorRecoveryStrategy.RETRY_WITH_ALTERNATE:
            if attempts < self.config.retry_config.max_attempts:
                self.retry_attempts[task_id] = attempts + 1
                return {
                    "action": "retry_alternate",
                    "attempt": attempts + 1,
                    "use_different_agent": True
                }
            else:
                return {"action": "fail", "reason": "no_alternate_agents"}

        elif strategy == ErrorRecoveryStrategy.SKIP_AND_CONTINUE:
            if context.get("task_critical", True):
                return {"action": "fail", "reason": "critical_task_failed"}
            else:
                return {"action": "skip", "reason": "non_critical_task_skipped"}

        elif strategy == ErrorRecoveryStrategy.COMPENSATE:
            return {
                "action": "compensate",
                "compensation_task": f"compensate_{task_id}"
            }

        elif strategy == ErrorRecoveryStrategy.MANUAL_INTERVENTION:
            return {
                "action": "manual_intervention",
                "error_details": str(error),
                "request_user_action": True
            }

        # Default fallback
        return {"action": "fail", "reason": "unknown_strategy"}

    def _classify_error(self, error: Exception) -> str:
        """Classify error type for retry decisions"""
        error_str = str(error).lower()

        if "timeout" in error_str:
            return "timeout"
        elif "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        elif "temporary" in error_str or "retry" in error_str:
            return "temporary_failure"
        elif "connection" in error_str or "network" in error_str:
            return "network_error"
        elif "permission" in error_str or "unauthorized" in error_str:
            return "permission_error"
        else:
            return "unknown_error"

    def _calculate_backoff_delay(self, attempts: int) -> float:
        """Calculate exponential backoff delay"""
        config = self.config.retry_config
        delay = min(
            config.initial_delay * (config.backoff_factor ** attempts),
            config.max_delay
        )
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
            "all_errors": errors
        }

    def reset_task_retries(self, task_id: str):
        """Reset retry counter for a task"""
        if task_id in self.retry_attempts:
            del self.retry_attempts[task_id]
        if task_id in self.error_history:
            del self.error_history[task_id]


class WorkflowConfigManager:
    """Manage workflow configurations with overrides and validation"""

    def __init__(self, base_config: WorkflowConfig):
        self.base_config = base_config
        self.overrides: List[WorkflowOverride] = []
        self.routing_rules: List[AgentRoutingRule] = []
        self.custom_complexity_fn: Optional[Callable] = None
        self.custom_routing_fn: Optional[Callable] = None

    def add_override(self, override: WorkflowOverride):
        """Add a workflow-specific configuration override"""
        self.overrides.append(override)
        # Sort by priority (descending)
        self.overrides.sort(key=lambda x: x.priority, reverse=True)

    def add_routing_rule(self, rule: AgentRoutingRule):
        """Add a custom agent routing rule"""
        self.routing_rules.append(rule)

    def set_custom_complexity_function(self, fn: Callable[[str, Optional[Dict[str, Any]]], float]):
        """Set custom complexity calculation function"""
        self.custom_complexity_fn = fn

    def set_custom_routing_function(self, fn: Callable[[Any, List[Any]], str]):
        """Set custom task routing function"""
        self.custom_routing_fn = fn

    def get_config_for_workflow(self, workflow_id: str, user_request: str) -> WorkflowConfig:
        """Get configuration with applied overrides for a specific workflow"""
        # Start with base config
        config_dict = self.base_config.model_dump()

        # Apply matching overrides in priority order
        for override in self.overrides:
            if self._matches_pattern(workflow_id, user_request, override.workflow_pattern):
                # Merge overrides
                self._merge_config(config_dict, override.config_overrides)

        # Create new config instance with merged values
        return WorkflowConfig(**config_dict)

    def get_routing_rules_for_task(self, task_description: str, capabilities: List[str]) -> List[AgentRoutingRule]:
        """Get applicable routing rules for a task"""
        matching_rules = []

        for rule in self.routing_rules:
            if self._matches_task_pattern(task_description, capabilities, rule):
                matching_rules.append(rule)

        # Sort by weight (descending)
        matching_rules.sort(key=lambda x: x.weight, reverse=True)
        return matching_rules

    def _matches_pattern(self, workflow_id: str, user_request: str, pattern: str) -> bool:
        """Check if workflow matches override pattern"""
        # Simple pattern matching - can be enhanced with regex
        pattern_lower = pattern.lower()

        # Check workflow ID
        if pattern_lower in workflow_id.lower():
            return True

        # Check user request
        if pattern_lower in user_request.lower():
            return True

        # Check for wildcard
        if pattern == "*":
            return True

        return False

    def _matches_task_pattern(self, description: str, capabilities: List[str], rule: AgentRoutingRule) -> bool:
        """Check if task matches routing rule pattern"""
        pattern_lower = rule.task_pattern.lower()
        description_lower = description.lower()

        # Check description
        if pattern_lower in description_lower:
            return True

        # Check required capabilities
        if rule.required_capabilities:
            if all(cap in capabilities for cap in rule.required_capabilities):
                return True

        return False

    def _merge_config(self, base: Dict[str, Any], overrides: Dict[str, Any]):
        """Recursively merge configuration overrides"""
        for key, value in overrides.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
