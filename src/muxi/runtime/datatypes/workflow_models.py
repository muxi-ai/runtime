"""
Workflow Models with Clear Separation of Concerns

This module provides clean separation between:
- TaskSpecification: Immutable definition of what needs to be done
- TaskExecutionState: Mutable runtime state tracking
- TaskExecutionResult: Immutable record of what happened

This separation improves code clarity and maintainability while maintaining
compatibility with existing SubTask-based interfaces through adapters.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator

from .task_status import TaskStatus
from ..utils.datetime_utils import utc_now


class TaskSpecification(BaseModel):
    """
    Immutable specification of a task - defines WHAT needs to be done.

    This model contains only the static definition of a task, without any
    runtime state or execution results. It represents the "blueprint" for
    a task that can be executed multiple times.
    """

    id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., description="Human-readable task description")
    required_capabilities: List[str] = Field(
        ..., min_items=1, description="Capabilities an agent must have to execute this task"
    )
    expected_outputs: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Expected output specifications with name, type, and description",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="IDs of tasks that must complete before this task can start",
    )
    estimated_complexity: float = Field(
        default=5.0, ge=1.0, le=10.0, description="Estimated task complexity (1-10 scale)"
    )

    # Additional metadata for better task understanding
    task_type: Optional[str] = Field(
        default=None, description="Type of task (analysis, generation, transformation, etc.)"
    )
    input_requirements: Optional[Dict[str, Any]] = Field(
        default=None, description="Required inputs and their specifications"
    )
    constraints: Optional[Dict[str, Any]] = Field(
        default=None, description="Any constraints or limitations for task execution"
    )
    priority: Optional[int] = Field(
        default=None, ge=1, le=10, description="Task priority (1-10, higher is more important)"
    )

    model_config = ConfigDict(frozen=True, extra="forbid")


class TaskExecutionState(BaseModel):
    """
    Mutable runtime state of a task - tracks HOW execution is progressing.

    This model contains all the mutable state that changes during task execution,
    including status, assignment, timing, and progress information.
    """

    spec: TaskSpecification = Field(..., description="The immutable task specification")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current execution status")
    assigned_agent_id: Optional[str] = Field(
        default=None, description="ID of the agent assigned to execute this task"
    )
    start_time: Optional[datetime] = Field(default=None, description="When task execution started")
    progress_percent: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description="Execution progress percentage"
    )

    # Runtime tracking
    attempt_count: int = Field(default=0, ge=0, description="Number of execution attempts")
    last_attempt_time: Optional[datetime] = Field(
        default=None, description="Time of the last execution attempt"
    )
    estimated_completion_time: Optional[datetime] = Field(
        default=None, description="Estimated time when task will complete"
    )

    # Additional runtime state
    is_critical_path: Optional[bool] = Field(
        default=None, description="Whether this task is on the critical execution path"
    )
    blocked_by: List[str] = Field(
        default_factory=list,
        description="IDs of incomplete dependencies currently blocking this task",
    )
    retry_after: Optional[datetime] = Field(
        default=None, description="Earliest time to retry if in retry state"
    )

    model_config = ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=True)

    def can_start(self) -> bool:
        """Check if task can start execution based on current state."""
        return (
            self.status in [TaskStatus.PENDING, TaskStatus.READY]
            and len(self.blocked_by) == 0
            and (self.retry_after is None or utc_now() >= self.retry_after)
        )

    def mark_started(self, agent_id: str) -> None:
        """Mark task as started by an agent."""
        self.status = TaskStatus.IN_PROGRESS
        self.assigned_agent_id = agent_id
        self.start_time = utc_now()
        self.attempt_count += 1
        self.last_attempt_time = self.start_time
        self.progress_percent = 0.0


class TaskExecutionResult(BaseModel):
    """
    Immutable record of task execution - describes WHAT HAPPENED.

    This model contains the complete, immutable record of a task execution,
    including success/failure status, outputs, timing, and any errors.
    """

    task_id: str = Field(..., description="ID of the executed task")
    success: bool = Field(..., description="Whether execution succeeded")
    outputs: Dict[str, Any] = Field(
        default_factory=dict, description="Task outputs keyed by output name"
    )
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    execution_time: float = Field(..., ge=0.0, description="Total execution time in seconds")
    agent_id: str = Field(..., description="ID of agent that executed the task")

    # Execution metadata
    start_time: datetime = Field(..., description="When execution started")
    end_time: datetime = Field(..., description="When execution completed")
    attempt_number: int = Field(default=1, ge=1, description="Which attempt this result represents")

    # Additional result information
    raw_response: Optional[str] = Field(
        default=None, description="Raw response from the executing agent"
    )
    artifacts: Optional[Dict[str, Any]] = Field(
        default=None, description="Any artifacts produced during execution"
    )
    metrics: Optional[Dict[str, float]] = Field(
        default=None, description="Performance metrics from execution"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Non-fatal warnings from execution"
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_timezone_consistency(self):
        """
        Validate that start_time and end_time have consistent timezone information.

        Both timestamps must either:
        - Both be timezone-aware (with the same timezone)
        - Both be timezone-naive

        This ensures accurate execution_time calculation.
        """
        if self.start_time.tzinfo is None and self.end_time.tzinfo is None:
            # Both are naive - this is valid
            return self
        elif self.start_time.tzinfo is not None and self.end_time.tzinfo is not None:
            # Both are aware - check if they have the same timezone
            # Note: We don't require the exact same tzinfo object, just that they
            # represent the same timezone (e.g., UTC)
            if self.start_time.tzinfo.utcoffset(None) != self.end_time.tzinfo.utcoffset(None):
                raise ValueError(
                    f"start_time and end_time have different timezones: "
                    f"start_time timezone offset={self.start_time.tzinfo.utcoffset(None)}, "
                    f"end_time timezone offset={self.end_time.tzinfo.utcoffset(None)}"
                )
            return self
        else:
            # One is aware and one is naive - this is invalid
            raise ValueError(
                f"Timezone mismatch: start_time is {'aware' if self.start_time.tzinfo else 'naive'}, "
                f"but end_time is {'aware' if self.end_time.tzinfo else 'naive'}. "
                "Both timestamps must be either timezone-aware or timezone-naive."
            )

    @property
    def status(self) -> TaskStatus:
        """Derive task status from result."""
        return TaskStatus.COMPLETED if self.success else TaskStatus.FAILED


# Utility functions for working with the new models


def create_task_specification(
    task_id: str, description: str, capabilities: List[str], **kwargs
) -> TaskSpecification:
    """
    Factory function to create a TaskSpecification with sensible defaults.

    Args:
        task_id: Unique identifier for the task
        description: Human-readable task description
        capabilities: Required agent capabilities
        **kwargs: Additional specification fields

    Returns:
        TaskSpecification instance
    """
    return TaskSpecification(
        id=task_id, description=description, required_capabilities=capabilities, **kwargs
    )


def create_execution_state(spec: TaskSpecification) -> TaskExecutionState:
    """
    Create initial execution state for a task specification.

    Args:
        spec: Task specification to create state for

    Returns:
        TaskExecutionState instance in pending state
    """
    return TaskExecutionState(spec=spec)


def create_execution_result(
    task_id: str,
    agent_id: str,
    start_time: datetime,
    end_time: datetime,
    success: bool,
    outputs: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    **kwargs,
) -> TaskExecutionResult:
    """
    Factory function to create a TaskExecutionResult.

    Args:
        task_id: ID of the executed task
        agent_id: ID of the executing agent
        start_time: Execution start time
        end_time: Execution end time
        success: Whether execution succeeded
        outputs: Task outputs (if any)
        error: Error message (if failed)
        **kwargs: Additional result fields

    Returns:
        TaskExecutionResult instance

    Raises:
        ValueError: If start_time and end_time have inconsistent timezone information
    """
    # Validate timezone consistency before calculating execution time
    if (start_time.tzinfo is None) != (end_time.tzinfo is None):
        raise ValueError(
            f"Timezone mismatch: start_time is {'aware' if start_time.tzinfo else 'naive'}, "
            f"but end_time is {'aware' if end_time.tzinfo else 'naive'}. "
            "Both timestamps must be either timezone-aware or timezone-naive."
        )

    if start_time.tzinfo and end_time.tzinfo:
        # Both are aware - check if they have the same timezone offset
        if start_time.tzinfo.utcoffset(None) != end_time.tzinfo.utcoffset(None):
            raise ValueError(
                f"start_time and end_time have different timezones: "
                f"start_time timezone offset={start_time.tzinfo.utcoffset(None)}, "
                f"end_time timezone offset={end_time.tzinfo.utcoffset(None)}"
            )

    execution_time = (end_time - start_time).total_seconds()

    return TaskExecutionResult(
        task_id=task_id,
        agent_id=agent_id,
        start_time=start_time,
        end_time=end_time,
        execution_time=execution_time,
        success=success,
        outputs=outputs or {},
        error=error,
        **kwargs,
    )
