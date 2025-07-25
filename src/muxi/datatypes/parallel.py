"""
Data types and structures for parallel workflow optimization.

This module defines the core data structures used for analyzing, optimizing,
and executing workflows in parallel across multiple agents.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from .task_status import TaskStatus


class BottleneckType(Enum):
    """Types of bottlenecks that can occur in workflow execution."""

    RESOURCE_CONTENTION = "resource_contention"  # Too many tasks competing for same agent
    DEPENDENCY_CHAIN = "dependency_chain"  # Long chain of dependent tasks
    AGENT_OVERLOAD = "agent_overload"  # Single agent with too many tasks
    CRITICAL_PATH = "critical_path"  # Tasks on the critical execution path
    CAPABILITY_SHORTAGE = "capability_shortage"  # Not enough agents with required capabilities


@dataclass
class TaskNode:
    """Represents a task in the dependency graph."""

    task_id: str
    description: str
    required_capabilities: List[str]
    estimated_duration: float = 30.0  # seconds
    priority: int = 1  # 1-10 scale
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING

    # Agent assignment
    assigned_agent_id: Optional[str] = None
    agent_score: float = 0.0

    # Execution tracking
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ParallelGroup:
    """Group of tasks that can be executed in parallel."""

    group_id: str
    task_ids: List[str]
    group_priority: int = 1
    estimated_duration: float = 0.0  # Max duration of tasks in group
    required_agents: int = 0  # Number of agents needed
    resource_requirements: Dict[str, int] = field(default_factory=dict)

    # Execution metadata
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    completion_rate: float = 0.0  # Percentage of tasks completed

    def add_task(self, task_id: str, estimated_duration: float) -> None:
        """Add a task to this parallel group."""
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)
            self.estimated_duration = max(self.estimated_duration, estimated_duration)
            self.required_agents = len(self.task_ids)


@dataclass
class ResourceAllocation:
    """Allocation of agents to tasks for optimal execution."""

    allocation_id: str
    task_assignments: Dict[str, str] = field(default_factory=dict)  # task_id -> agent_id
    agent_workloads: Dict[str, List[str]] = field(default_factory=dict)  # agent_id -> task_ids
    utilization_scores: Dict[str, float] = field(default_factory=dict)  # agent_id -> utilization

    # Optimization metrics
    total_estimated_time: float = 0.0
    parallel_efficiency: float = 0.0  # How well tasks are parallelized (0-1)
    load_balance_score: float = 0.0  # How evenly work is distributed (0-1)

    def assign_task(self, task_id: str, agent_id: str, estimated_duration: float) -> None:
        """Assign a task to an agent."""
        self.task_assignments[task_id] = agent_id

        if agent_id not in self.agent_workloads:
            self.agent_workloads[agent_id] = []
        self.agent_workloads[agent_id].append(task_id)

        # Update utilization (simplified calculation)
        current_load = len(self.agent_workloads[agent_id]) * estimated_duration
        self.utilization_scores[agent_id] = min(1.0, current_load / 300.0)  # 5 min max

    def get_agent_load(self, agent_id: str) -> int:
        """Get the number of tasks assigned to an agent."""
        return len(self.agent_workloads.get(agent_id, []))

    def get_least_loaded_agent(self, available_agents: List[str]) -> Optional[str]:
        """Find the agent with the least workload."""
        if not available_agents:
            return None

        return min(available_agents, key=lambda agent_id: self.get_agent_load(agent_id))


@dataclass
class BottleneckInfo:
    """Information about a detected bottleneck in workflow execution."""

    bottleneck_id: str
    bottleneck_type: BottleneckType
    affected_tasks: List[str]
    severity_score: float = 0.0  # 0-1 scale, higher = more severe
    estimated_delay: float = 0.0  # Additional time in seconds
    description: str = ""

    # Resolution suggestions
    suggested_resolution: str = ""
    can_auto_resolve: bool = False
    resolution_confidence: float = 0.0

    # Context information
    detected_at: datetime = field(default_factory=datetime.now)
    resource_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Detailed plan for parallel execution of a workflow."""

    plan_id: str
    parallel_groups: List[ParallelGroup]
    resource_allocation: ResourceAllocation
    execution_order: List[str]  # Group IDs in execution order

    # Timing estimates
    estimated_total_time: float = 0.0
    critical_path_time: float = 0.0
    parallelization_speedup: float = 1.0  # Expected speedup vs sequential execution

    # Resource requirements
    max_concurrent_agents: int = 0
    total_agent_time: float = 0.0  # Sum of all agent work time

    # Quality metrics
    plan_confidence: float = 0.0  # Confidence in time estimates (0-1)
    risk_factors: List[str] = field(default_factory=list)
    bottlenecks: List[BottleneckInfo] = field(default_factory=list)

    def get_total_groups(self) -> int:
        """Get the total number of parallel groups."""
        return len(self.parallel_groups)

    def get_max_group_size(self) -> int:
        """Get the size of the largest parallel group."""
        if not self.parallel_groups:
            return 0
        return max(len(group.task_ids) for group in self.parallel_groups)

    def calculate_efficiency_score(self) -> float:
        """Calculate overall execution efficiency score."""
        if self.parallelization_speedup <= 1.0:
            return 0.0

        # Combine speedup, resource utilization, and plan confidence
        speedup_score = min(1.0, (self.parallelization_speedup - 1.0) / 4.0)  # Normalize to 0-1
        resource_score = self.resource_allocation.parallel_efficiency
        confidence_score = self.plan_confidence

        return (speedup_score + resource_score + confidence_score) / 3.0


@dataclass
class OptimizedWorkflow:
    """Workflow optimized for parallel execution."""

    workflow_id: str
    original_workflow: Any  # Reference to original workflow
    execution_plan: ExecutionPlan
    optimization_metadata: Dict[str, Any] = field(default_factory=dict)

    # Optimization results
    original_estimated_time: float = 0.0
    optimized_estimated_time: float = 0.0
    expected_speedup: float = 1.0
    optimization_confidence: float = 0.0

    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    optimized_by: str = "ParallelWorkflowOptimizer"

    def get_speedup_ratio(self) -> float:
        """Get the ratio of speedup achieved."""
        if self.original_estimated_time <= 0:
            return 1.0
        return self.original_estimated_time / max(self.optimized_estimated_time, 1.0)

    def is_worth_optimizing(self, min_speedup: float = 1.2) -> bool:
        """Check if optimization provides meaningful benefit."""
        return self.get_speedup_ratio() >= min_speedup and self.optimization_confidence > 0.6


@dataclass
class ParallelExecutionResult:
    """Result of parallel workflow execution."""

    execution_id: str
    workflow_id: str
    execution_plan: ExecutionPlan

    # Execution tracking
    start_time: datetime
    end_time: Optional[datetime] = None
    actual_duration: float = 0.0

    # Task results
    task_results: Dict[str, Any] = field(default_factory=dict)  # task_id -> result
    task_errors: Dict[str, str] = field(default_factory=dict)  # task_id -> error
    completed_tasks: Set[str] = field(default_factory=set)
    failed_tasks: Set[str] = field(default_factory=set)

    # Performance metrics
    actual_speedup: float = 1.0
    efficiency_achieved: float = 0.0  # Actual vs planned efficiency
    agent_utilization: Dict[str, float] = field(default_factory=dict)

    # Bottlenecks encountered
    runtime_bottlenecks: List[BottleneckInfo] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of task execution."""
        total_tasks = len(self.completed_tasks) + len(self.failed_tasks)
        if total_tasks == 0:
            return 1.0
        return len(self.completed_tasks) / total_tasks

    @property
    def is_complete(self) -> bool:
        """Check if execution is complete."""
        return self.end_time is not None

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of execution performance."""
        return {
            "actual_duration": self.actual_duration,
            "planned_duration": self.execution_plan.estimated_total_time,
            "speedup_achieved": self.actual_speedup,
            "success_rate": self.success_rate,
            "efficiency": self.efficiency_achieved,
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "bottlenecks_encountered": len(self.runtime_bottlenecks),
        }


@dataclass
class AgentCapability:
    """Represents an agent's capability for task assignment."""

    agent_id: str
    capabilities: Set[str]
    performance_scores: Dict[str, float] = field(default_factory=dict)  # capability -> score
    current_load: int = 0
    max_concurrent_tasks: int = 3
    average_task_duration: float = 30.0  # seconds

    # Performance history
    success_rate: float = 1.0
    average_response_time: float = 30.0
    last_task_completed: Optional[datetime] = None

    def can_handle_capability(self, capability: str) -> bool:
        """Check if agent can handle a specific capability."""
        return capability in self.capabilities

    def get_capability_score(self, capability: str) -> float:
        """Get the agent's score for a specific capability."""
        return self.performance_scores.get(capability, 0.5)  # Default to medium score

    def is_available(self) -> bool:
        """Check if agent is available for new tasks."""
        return self.current_load < self.max_concurrent_tasks

    def get_load_factor(self) -> float:
        """Get current load as a factor (0-1)."""
        return self.current_load / self.max_concurrent_tasks
