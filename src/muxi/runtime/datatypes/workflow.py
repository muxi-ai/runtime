from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

from pydantic import BaseModel, Field, field_validator, computed_field, ConfigDict

from ..utils.id_generator import generate_nanoid
from .task_status import TaskStatus
from .type_definitions import TaskOutput as TaskOutputType


class WorkflowStatus(Enum):
    """Overall workflow status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


class ApprovalStatus(Enum):
    """Plan approval status"""

    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class TaskInput(BaseModel):
    """Input specification for a task"""

    name: str = Field(..., min_length=1, description="Input name")
    description: str = Field(..., description="Input description")
    type: str = Field(..., description="Input type (text, file, data, etc.)")
    required: bool = Field(default=True, description="Whether this input is required")
    source_task_id: Optional[str] = Field(
        default=None, description="ID of task that provides this input"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        """Validate input type."""
        valid_types = ["text", "file", "data", "json", "image", "audio", "video"]
        if v not in valid_types:
            raise ValueError(f"Invalid input type. Must be one of: {', '.join(valid_types)}")
        return v

    model_config = ConfigDict(extra="forbid")


class TaskOutput(BaseModel):
    """Output specification for a task"""

    name: str = Field(..., min_length=1, description="Output name")
    description: str = Field(..., description="Output description")
    type: str = Field(..., description="Output type (text, file, data, etc.)")
    target_task_ids: List[str] = Field(
        default_factory=list, description="Tasks that use this output"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        """Validate output type."""
        valid_types = ["text", "file", "data", "json", "image", "audio", "video"]
        if v not in valid_types:
            raise ValueError(f"Invalid output type. Must be one of: {', '.join(valid_types)}")
        return v

    model_config = ConfigDict(extra="forbid")


class SubTask(BaseModel):
    """Individual task within a workflow"""

    id: str = Field(..., min_length=1, description="Unique task identifier")
    description: str = Field(..., description="Task description")
    required_capabilities: List[str] = Field(..., description="Required agent capabilities")
    dependencies: List[str] = Field(default_factory=list, description="IDs of prerequisite tasks")
    inputs: List[TaskInput] = Field(default_factory=list, description="Task inputs")
    outputs: List[TaskOutput] = Field(default_factory=list, description="Task outputs")
    estimated_complexity: float = Field(
        default=5.0, ge=1.0, le=10.0, description="Complexity score (1-10 scale)"
    )
    assigned_agent_id: Optional[str] = Field(
        default=None, description="ID of agent assigned to this task"
    )
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task status")
    result: Optional[Any] = Field(default=None, description="Task execution result")
    start_time: Optional[datetime] = Field(default=None, description="Task start time")
    end_time: Optional[datetime] = Field(default=None, description="Task end time")
    progress_percent: Optional[float] = Field(
        default=None, ge=0.0, le=100.0, description="Task progress percentage"
    )
    error_message: Optional[str] = Field(default=None, description="Error message if task failed")

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v):
        """Validate task ID format."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("ID must be alphanumeric with hyphens/underscores")
        return v

    @field_validator("dependencies")
    @classmethod
    def validate_no_self_dependency(cls, v, info):
        """Ensure task doesn't depend on itself."""
        if "id" in info.data and info.data["id"] in v:
            raise ValueError("Task cannot depend on itself")
        return v

    @field_validator("required_capabilities")
    @classmethod
    def validate_capabilities_not_empty(cls, v):
        """Ensure at least one capability is required."""
        if not v:
            raise ValueError("At least one capability must be required")
        return v

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class RequestAnalysis(BaseModel):
    """Analysis results for a user request"""

    complexity_score: float = Field(
        ..., ge=1.0, le=10.0, description="Request complexity (1-10 scale)"
    )
    requires_decomposition: bool = Field(..., description="Whether request needs to be broken down")
    requires_approval: bool = Field(..., description="Whether plan preview is needed")
    implicit_subtasks: List[str] = Field(..., description="Identified implicit subtasks")
    required_capabilities: List[str] = Field(..., description="Required agent capabilities")
    acceptance_criteria: List[str] = Field(..., description="Success criteria for the request")
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Analysis confidence (0-1 scale)"
    )
    is_scheduling_request: bool = Field(default=False, description="Whether this is a scheduling request")
    is_explicit_approval_request: bool = Field(
        default=False,
        description="Whether user explicitly wants to see the plan/approach before execution"
    )
    explicit_sop_request: Optional[str] = Field(
        default=None,
        description="SOP ID if user explicitly requests a specific SOP/procedure/workflow by name"
    )
    topics: List[str] = Field(
        default_factory=list,
        description="Dynamic topic tags generated by LLM for request categorization"
    )
    is_security_threat: bool = Field(
        default=False,
        description="Whether the request appears to be a security threat (prompt injection, credential fishing, etc.)"
    )
    threat_type: Optional[str] = Field(
        default=None,
        description="Type of security threat if detected: 'prompt_injection', 'credential_fishing', 'information_extraction', 'jailbreak', or None"  # noqa: E501
    )

    @field_validator("threat_type")
    @classmethod
    def validate_threat_type(cls, v):
        """
        Validate and normalize threat_type to allowed values.

        Allowed values: None, 'prompt_injection', 'credential_fishing',
                       'information_extraction', 'jailbreak'
        """
        if v is None:
            return None

        # Normalize: strip whitespace and convert to lowercase
        if isinstance(v, str):
            normalized = v.strip().lower()

            # Check if normalized value is in allowed set
            allowed_threats = {
                'prompt_injection',
                'credential_fishing',
                'information_extraction',
                'jailbreak'
            }

            if normalized in allowed_threats:
                return normalized

            # Invalid value - raise with clear error message
            raise ValueError(
                f"Invalid threat_type: '{v}'. Must be None or one of: "
                f"{', '.join(sorted(allowed_threats))}"
            )

        # Non-string, non-None value
        raise ValueError(
            f"threat_type must be a string or None, got {type(v).__name__}"
        )

    @field_validator("implicit_subtasks", "required_capabilities", "acceptance_criteria")
    @classmethod
    def validate_non_empty_lists(cls, v, info):
        """Ensure lists have at least one item when required."""
        field_name = info.field_name
        if field_name in ["required_capabilities", "acceptance_criteria"] and not v:
            raise ValueError(f"{field_name} cannot be empty")
        return v

    model_config = ConfigDict(extra="forbid")


class TaskResult(BaseModel):
    """Result of task execution"""

    task_id: str = Field(..., min_length=1, description="ID of executed task")
    status: TaskStatus = Field(..., description="Task execution status")
    outputs: Dict[str, TaskOutputType] = Field(
        default_factory=dict, description="Task outputs by name"
    )
    agent_id: Optional[str] = Field(default=None, description="ID of agent that executed task")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time: Optional[float] = Field(
        default=None, ge=0.0, description="Execution time in seconds"
    )
    raw_response: Optional[str] = Field(default=None, description="Raw agent response")

    @field_validator("error_message")
    @classmethod
    def validate_error_consistency(cls, v, info):
        """Ensure error message exists for failure status."""
        if info.data.get("status") == TaskStatus.FAILED and not v:
            raise ValueError("Error message required for failed tasks")
        return v

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class Workflow(BaseModel):
    """Complete workflow definition"""

    id: str = Field(..., min_length=1, description="Unique workflow identifier")
    user_request: str = Field(..., min_length=1, description="Original user request")
    tasks: Dict[str, SubTask] = Field(..., description="Tasks indexed by ID")
    execution_graph: Optional[Dict[str, Set[str]]] = Field(
        default=None, description="DAG representation of task dependencies"
    )
    status: WorkflowStatus = Field(
        default=WorkflowStatus.PENDING, description="Current workflow status"
    )
    requires_approval: bool = Field(default=False, description="Whether plan preview is required")
    approval_status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING, description="Plan approval status"
    )
    plan_preview: Optional[str] = Field(default=None, description="Human-readable plan description")
    created_at: datetime = Field(default_factory=datetime.now, description="Workflow creation time")
    started_at: Optional[datetime] = Field(
        default=None, description="Workflow execution start time"
    )
    completed_at: Optional[datetime] = Field(default=None, description="Workflow completion time")
    progress_percent: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Overall progress percentage"
    )
    current_phase: int = Field(default=0, ge=0, description="Current execution phase")
    total_phases: int = Field(default=0, ge=0, description="Total number of phases")
    execution_phases: List[List[str]] = Field(
        default_factory=list, description="Parallel execution groups"
    )

    @field_validator("tasks")
    @classmethod
    def validate_tasks_not_empty(cls, v):
        """Ensure workflow has at least one task."""
        if not v:
            raise ValueError("Workflow must have at least one task")
        return v

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v):
        """Validate workflow ID format."""
        if not (v.startswith("workflow_") or v.startswith("wf_") or v.startswith("wrk_")):
            raise ValueError("Workflow ID must start with 'workflow_', 'wf_', or 'wrk_'")
        return v

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Check if workflow is complete."""
        return self.status in [
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        ]

    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if workflow is actively running."""
        return self.status == WorkflowStatus.IN_PROGRESS

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


# Utility Functions


def generate_workflow_id() -> str:
    """Generate a unique workflow ID"""
    return f"wrk_{generate_nanoid()}"


def generate_task_id() -> str:
    """Generate a unique task ID"""
    return f"tsk_{generate_nanoid()}"


def validate_workflow_dag(workflow: Workflow) -> bool:
    """
    Validate that workflow tasks form a valid DAG (no cycles)

    Args:
        workflow: Workflow to validate

    Returns:
        True if valid DAG, False if cycles detected
    """
    # Build proper graph representation
    graph = {}
    in_degree = {}
    reverse_graph = {}  # task_id -> list of tasks that depend on it

    for task_id, task in workflow.tasks.items():
        graph[task_id] = set(task.dependencies)
        in_degree[task_id] = len(task.dependencies)
        reverse_graph[task_id] = []

    # Build reverse graph for efficient dependency removal
    for task_id, task in workflow.tasks.items():
        for dep in task.dependencies:
            if dep in reverse_graph:
                reverse_graph[dep].append(task_id)

    # Kahn's algorithm for cycle detection
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    processed = 0

    while queue:
        current = queue.pop(0)
        processed += 1

        # Update in-degree for dependent tasks
        for dependent in reverse_graph[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # If we processed all tasks, no cycles exist
    return processed == len(workflow.tasks)


def build_execution_phases(workflow: Workflow) -> List[List[str]]:
    """
    Build execution phases for parallel task processing

    Args:
        workflow: Workflow to analyze

    Returns:
        List of task ID groups that can run in parallel
    """
    if not validate_workflow_dag(workflow):
        raise ValueError("Workflow contains circular dependencies")

    # Build dependency graph
    graph = {}
    remaining_tasks = set(workflow.tasks.keys())

    for task_id, task in workflow.tasks.items():
        graph[task_id] = set(task.dependencies)

    execution_phases = []

    while remaining_tasks:
        # Find tasks with no pending dependencies
        ready_tasks = [
            task_id
            for task_id in remaining_tasks
            if not graph[task_id].intersection(remaining_tasks)
        ]

        if not ready_tasks:
            raise ValueError("Circular dependency detected")

        execution_phases.append(ready_tasks)
        remaining_tasks -= set(ready_tasks)

    workflow.execution_phases = execution_phases
    workflow.total_phases = len(execution_phases)

    return execution_phases


def calculate_workflow_progress(workflow: Workflow) -> float:
    """
    Calculate overall workflow progress based on task completion

    Args:
        workflow: Workflow to analyze

    Returns:
        Progress percentage (0.0 - 100.0)
    """
    if not workflow.tasks:
        return 0.0

    total_tasks = len(workflow.tasks)
    completed_tasks = sum(1 for task in workflow.tasks.values() if task.status == TaskStatus.DONE)

    return (completed_tasks / total_tasks) * 100.0


def get_ready_tasks(workflow: Workflow) -> List[str]:
    """
    Get tasks that are ready to execute (all dependencies completed)

    Args:
        workflow: Workflow to analyze

    Returns:
        List of task IDs ready for execution
    """
    ready_tasks = []

    for task_id, task in workflow.tasks.items():
        if task.status != TaskStatus.PENDING:
            continue

        # Check if all dependencies are completed
        dependencies_met = all(
            workflow.tasks[dep_id].status == TaskStatus.DONE
            for dep_id in task.dependencies
            if dep_id in workflow.tasks
        )

        if dependencies_met:
            ready_tasks.append(task_id)

    return ready_tasks
