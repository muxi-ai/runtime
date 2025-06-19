from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
import uuid


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"
    REVIEW = "review"


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


@dataclass
class TaskInput:
    """Input specification for a task"""
    name: str
    description: str
    type: str  # "text", "file", "data", etc.
    required: bool = True
    source_task_id: Optional[str] = None  # ID of task that provides this input


@dataclass
class TaskOutput:
    """Output specification for a task"""
    name: str
    description: str
    type: str  # "text", "file", "data", etc.
    target_task_ids: List[str] = field(default_factory=list)  # Tasks that use this output


@dataclass
class SubTask:
    """Individual task within a workflow"""
    id: str
    description: str
    required_capabilities: List[str]
    dependencies: List[str] = field(default_factory=list)  # IDs of prerequisite tasks
    inputs: List[TaskInput] = field(default_factory=list)
    outputs: List[TaskOutput] = field(default_factory=list)
    estimated_complexity: float = 5.0  # 1-10 scale
    assigned_agent_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    progress_percent: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class RequestAnalysis:
    """Analysis results for a user request"""
    complexity_score: float  # 1-10 scale
    requires_decomposition: bool
    requires_approval: bool  # NEW: Plan preview needed
    implicit_subtasks: List[str]
    required_capabilities: List[str]
    acceptance_criteria: List[str]
    confidence_score: float = 0.0  # 0-1 scale


@dataclass
class TaskResult:
    """Result of task execution"""
    task_id: str
    status: TaskStatus
    outputs: Dict[str, Any] = field(default_factory=dict)
    agent_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    raw_response: Optional[str] = None


@dataclass
class Workflow:
    """Complete workflow definition"""
    id: str
    user_request: str
    tasks: Dict[str, SubTask]
    execution_graph: Optional[Dict[str, Set[str]]] = None  # DAG representation
    status: WorkflowStatus = WorkflowStatus.PENDING
    requires_approval: bool = False  # NEW: Plan preview required
    approval_status: ApprovalStatus = ApprovalStatus.PENDING  # NEW
    plan_preview: Optional[str] = None  # NEW: Human-readable plan
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress_percent: float = 0.0
    current_phase: int = 0
    total_phases: int = 0
    execution_phases: List[List[str]] = field(default_factory=list)  # Parallel execution groups


# Utility Functions

def generate_workflow_id() -> str:
    """Generate a unique workflow ID"""
    return f"workflow_{uuid.uuid4().hex[:8]}"


def generate_task_id() -> str:
    """Generate a unique task ID"""
    return f"task_{uuid.uuid4().hex[:8]}"


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
            task_id for task_id in remaining_tasks
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
        Progress percentage (0.0 - 1.0)
    """
    if not workflow.tasks:
        return 0.0

    total_tasks = len(workflow.tasks)
    completed_tasks = sum(
        1 for task in workflow.tasks.values()
        if task.status == TaskStatus.DONE
    )

    return completed_tasks / total_tasks


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
