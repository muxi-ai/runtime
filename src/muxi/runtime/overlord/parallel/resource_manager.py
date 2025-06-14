"""
Resource management for parallel workflow optimization.

This module optimizes the allocation of agents to tasks for maximum efficiency,
handles load balancing, and manages resource constraints in parallel execution.
"""

import asyncio

import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .types import (
    TaskNode,
    ParallelGroup,
    ResourceAllocation,
    AgentCapability,
    BottleneckInfo,
    BottleneckType
)




@dataclass
class AgentAssignmentScore:
    """Score for assigning a specific agent to a task."""
    agent_id: str
    task_id: str
    capability_match: float = 0.0    # How well agent matches task capabilities (0-1)
    load_factor: float = 0.0         # Current agent load (0-1, lower is better)
    performance_score: float = 0.0   # Historical performance (0-1)
    availability_score: float = 0.0  # How soon agent is available (0-1)
    total_score: float = 0.0         # Combined weighted score


class ResourceManager:
    """Manages agent allocation and resource optimization for parallel workflows."""

    def __init__(self):
        self.agent_capabilities: Dict[str, AgentCapability] = {}
        self.current_allocations: Dict[str, ResourceAllocation] = {}
        self.allocation_history: List[ResourceAllocation] = []

        # Scoring weights for agent assignment
        self.capability_weight = 0.4   # 40% weight on capability match
        self.load_weight = 0.3         # 30% weight on current load
        self.performance_weight = 0.2  # 20% weight on historical performance
        self.availability_weight = 0.1 # 10% weight on availability timing

    async def register_agent(self, agent_capability: AgentCapability) -> None:
        """Register an agent's capabilities for resource allocation."""
        self.agent_capabilities[agent_capability.agent_id] = agent_capability
        #  Info - add observability event
                   f"{list(agent_capability.capabilities)}")

    async def update_agent_load(self, agent_id: str, current_load: int) -> None:
        """Update an agent's current task load."""
        if agent_id in self.agent_capabilities:
            self.agent_capabilities[agent_id].current_load = current_load

    async def optimize_allocation(
        self,
        parallel_groups: List[ParallelGroup],
        available_agents: List[str]
    ) -> ResourceAllocation:
        """
        Optimize agent allocation for a set of parallel groups.

        Args:
            parallel_groups: Groups of tasks to be executed in parallel
            available_agents: List of available agent IDs

        Returns:
            Optimized ResourceAllocation object
        """
        allocation_id = f"allocation_{uuid.uuid4().hex[:8]}"
        allocation = ResourceAllocation(allocation_id=allocation_id)

        # Filter available agents based on registered capabilities
        valid_agents = [
            agent_id for agent_id in available_agents
            if agent_id in self.agent_capabilities
        ]

        if not valid_agents:
            #  Warning - add observability event
            return allocation

        # Process each parallel group
        for group in parallel_groups:
            await self._allocate_group_tasks(group, valid_agents, allocation)

        # Calculate allocation metrics
        await self._calculate_allocation_metrics(allocation, parallel_groups)

        # Store allocation
        self.current_allocations[allocation_id] = allocation
        self.allocation_history.append(allocation)

        #  Info - add observability event
                   f"{allocation.parallel_efficiency:.2f}")

        return allocation

    async def _allocate_group_tasks(
        self,
        group: ParallelGroup,
        available_agents: List[str],
        allocation: ResourceAllocation
    ) -> None:
        """Allocate tasks within a parallel group to agents."""

        # Get task nodes for this group (mock implementation)
        group_tasks = []
        for task_id in group.task_ids:
            # Create a mock task node for allocation
            task_node = TaskNode(
                task_id=task_id,
                description=f"Task {task_id}",
                required_capabilities=["general"],  # Default capability
                estimated_duration=group.estimated_duration / len(group.task_ids)
            )
            group_tasks.append(task_node)

        # Score all agent-task combinations
        all_scores = []
        for task in group_tasks:
            task_scores = await self._score_agents_for_task(task, available_agents)
            all_scores.extend(task_scores)

        # Sort by score (highest first)
        all_scores.sort(key=lambda x: x.total_score, reverse=True)

        # Assign tasks using greedy approach with load balancing
        assigned_tasks = set()
        for score in all_scores:
            if score.task_id in assigned_tasks:
                continue

            # Check if agent is still available (not overloaded)
            if self._is_agent_available(score.agent_id, allocation):
                allocation.assign_task(
                    score.task_id,
                    score.agent_id,
                    self._get_task_duration(score.task_id, group_tasks)
                )
                assigned_tasks.add(score.task_id)

        # Handle unassigned tasks (fallback to least loaded agents)
        unassigned = set(group.task_ids) - assigned_tasks
        for task_id in unassigned:
            least_loaded = allocation.get_least_loaded_agent(available_agents)
            if least_loaded:
                task_duration = self._get_task_duration(task_id, group_tasks)
                allocation.assign_task(task_id, least_loaded, task_duration)
                #  Warning - add observability event

    async def _score_agents_for_task(
        self,
        task: TaskNode,
        available_agents: List[str]
    ) -> List[AgentAssignmentScore]:
        """Score all available agents for a specific task."""
        scores = []

        for agent_id in available_agents:
            if agent_id not in self.agent_capabilities:
                continue

            agent = self.agent_capabilities[agent_id]
            score = AgentAssignmentScore(agent_id=agent_id, task_id=task.task_id)

            # Calculate capability match score
            score.capability_match = await self._calculate_capability_match(task, agent)

            # Calculate load factor (inverted - lower load is better)
            score.load_factor = 1.0 - agent.get_load_factor()

            # Use historical performance
            score.performance_score = agent.success_rate

            # Simple availability score (available = 1.0, unavailable = 0.0)
            score.availability_score = 1.0 if agent.is_available() else 0.0

            # Calculate weighted total score
            score.total_score = (
                score.capability_match * self.capability_weight +
                score.load_factor * self.load_weight +
                score.performance_score * self.performance_weight +
                score.availability_score * self.availability_weight
            )

            scores.append(score)

        return scores

    async def _calculate_capability_match(
        self,
        task: TaskNode,
        agent: AgentCapability
    ) -> float:
        """Calculate how well an agent's capabilities match a task's requirements."""
        if not task.required_capabilities:
            return 1.0  # No specific requirements

        total_match = 0.0
        for capability in task.required_capabilities:
            if agent.can_handle_capability(capability):
                # Get agent's score for this capability
                capability_score = agent.get_capability_score(capability)
                total_match += capability_score
            else:
                # Agent cannot handle this capability
                return 0.0

        # Return average match score
        return total_match / len(task.required_capabilities)

    def _is_agent_available(self, agent_id: str, allocation: ResourceAllocation) -> bool:
        """Check if an agent is available for more tasks."""
        if agent_id not in self.agent_capabilities:
            return False

        agent = self.agent_capabilities[agent_id]
        current_load = allocation.get_agent_load(agent_id)

        return current_load < agent.max_concurrent_tasks

    def _get_task_duration(self, task_id: str, tasks: List[TaskNode]) -> float:
        """Get the estimated duration for a task."""
        for task in tasks:
            if task.task_id == task_id:
                return task.estimated_duration
        return 30.0  # Default duration

    async def _calculate_allocation_metrics(
        self,
        allocation: ResourceAllocation,
        parallel_groups: List[ParallelGroup]
    ) -> None:
        """Calculate metrics for the resource allocation."""

        if not allocation.task_assignments:
            return

        # Calculate total estimated time (sum of all group durations)
        allocation.total_estimated_time = sum(group.estimated_duration for group in parallel_groups)

        # Calculate parallel efficiency (how well we utilize parallelism)
        total_sequential_time = sum(
            sum(self._get_task_duration(task_id, []) for task_id in group.task_ids)
            for group in parallel_groups
        )

        if total_sequential_time > 0:
            allocation.parallel_efficiency = min(1.0, allocation.total_estimated_time / total_sequential_time)

        # Calculate load balance score
        if allocation.agent_workloads:
            workload_sizes = [len(tasks) for tasks in allocation.agent_workloads.values()]
            avg_workload = sum(workload_sizes) / len(workload_sizes)
            max_workload = max(workload_sizes)

            if max_workload > 0:
                allocation.load_balance_score = avg_workload / max_workload
            else:
                allocation.load_balance_score = 1.0

    async def detect_resource_bottlenecks(
        self,
        allocation: ResourceAllocation,
        parallel_groups: List[ParallelGroup]
    ) -> List[BottleneckInfo]:
        """Detect resource-related bottlenecks in the allocation."""
        bottlenecks = []

        # Check for overloaded agents
        for agent_id, tasks in allocation.agent_workloads.items():
            if agent_id in self.agent_capabilities:
                agent = self.agent_capabilities[agent_id]
                if len(tasks) > agent.max_concurrent_tasks:
                    bottleneck = BottleneckInfo(
                        bottleneck_id=f"agent_overload_{agent_id}",
                        bottleneck_type=BottleneckType.AGENT_OVERLOAD,
                        affected_tasks=tasks,
                        severity_score=min(1.0, len(tasks) / agent.max_concurrent_tasks - 1.0),
                        estimated_delay=len(tasks) * agent.average_task_duration * 0.1,
                        description=f"Agent {agent_id} overloaded with {len(tasks)} tasks "
                                   f"(max: {agent.max_concurrent_tasks})",
                        suggested_resolution=f"Redistribute tasks from agent {agent_id} or add more agents",
                        can_auto_resolve=True,
                        resolution_confidence=0.8
                    )
                    bottlenecks.append(bottleneck)

        # Check for capability shortages
        capability_demand = {}
        for group in parallel_groups:
            for capability, count in group.resource_requirements.items():
                capability_demand[capability] = capability_demand.get(capability, 0) + count

        capability_supply = {}
        for agent in self.agent_capabilities.values():
            for capability in agent.capabilities:
                capability_supply[capability] = capability_supply.get(capability, 0) + 1

        for capability, demand in capability_demand.items():
            supply = capability_supply.get(capability, 0)
            if supply < demand:
                bottleneck = BottleneckInfo(
                    bottleneck_id=f"capability_shortage_{capability}",
                    bottleneck_type=BottleneckType.CAPABILITY_SHORTAGE,
                    affected_tasks=[],  # Would need task mapping
                    severity_score=min(1.0, (demand - supply) / demand),
                    estimated_delay=(demand - supply) * 30.0,  # Estimate 30s per missing capability
                    description=f"Shortage of '{capability}' capability: need {demand}, have {supply}",
                    suggested_resolution=f"Add {demand - supply} agents with '{capability}' capability",
                    can_auto_resolve=False,
                    resolution_confidence=0.9,
                    resource_context={"capability": capability, "demand": demand, "supply": supply}
                )
                bottlenecks.append(bottleneck)

        return bottlenecks

    async def rebalance_allocation(
        self,
        allocation: ResourceAllocation,
        target_balance_threshold: float = 0.8
    ) -> ResourceAllocation:
        """
        Rebalance an allocation to improve load distribution.

        Args:
            allocation: Current allocation to rebalance
            target_balance_threshold: Target balance score (0-1)

        Returns:
            Rebalanced ResourceAllocation
        """
        if allocation.load_balance_score >= target_balance_threshold:
            return allocation  # Already well balanced

        # Find overloaded and underloaded agents
        workload_sizes = {
            agent_id: len(tasks) for agent_id, tasks in allocation.agent_workloads.items()
        }

        if not workload_sizes:
            return allocation

        avg_workload = sum(workload_sizes.values()) / len(workload_sizes)

        overloaded = [
            agent_id for agent_id, size in workload_sizes.items()
            if size > avg_workload * 1.5  # 50% above average
        ]

        underloaded = [
            agent_id for agent_id, size in workload_sizes.items()
            if size < avg_workload * 0.5  # 50% below average
        ]

        # Redistribute tasks from overloaded to underloaded agents
        for overloaded_agent in overloaded:
            if not underloaded:
                break

            # Move some tasks to underloaded agents
            tasks_to_move = allocation.agent_workloads[overloaded_agent][:1]  # Move 1 task

            for task_id in tasks_to_move:
                target_agent = underloaded[0]  # Simple round-robin

                # Remove from overloaded agent
                allocation.agent_workloads[overloaded_agent].remove(task_id)

                # Add to underloaded agent
                if target_agent not in allocation.agent_workloads:
                    allocation.agent_workloads[target_agent] = []
                allocation.agent_workloads[target_agent].append(task_id)

                # Update assignment
                allocation.task_assignments[task_id] = target_agent

                #  Info - add observability event

        # Recalculate load balance score
        new_workload_sizes = [len(tasks) for tasks in allocation.agent_workloads.values()]
        if new_workload_sizes:
            new_avg = sum(new_workload_sizes) / len(new_workload_sizes)
            new_max = max(new_workload_sizes)
            allocation.load_balance_score = new_avg / max(new_max, 1)

        return allocation

    def get_allocation_summary(self, allocation_id: str) -> Dict[str, Any]:
        """Get a summary of a resource allocation."""
        if allocation_id not in self.current_allocations:
            return {}

        allocation = self.current_allocations[allocation_id]

        return {
            "allocation_id": allocation_id,
            "total_tasks": len(allocation.task_assignments),
            "total_agents": len(allocation.agent_workloads),
            "parallel_efficiency": allocation.parallel_efficiency,
            "load_balance_score": allocation.load_balance_score,
            "estimated_total_time": allocation.total_estimated_time,
            "agent_utilization": {
                agent_id: len(tasks) / self.agent_capabilities[agent_id].max_concurrent_tasks
                for agent_id, tasks in allocation.agent_workloads.items()
                if agent_id in self.agent_capabilities
            }
        }

    async def cleanup_completed_allocation(self, allocation_id: str) -> None:
        """Clean up a completed allocation and update agent states."""
        if allocation_id in self.current_allocations:
            allocation = self.current_allocations[allocation_id]

            # Reset agent loads
            for agent_id in allocation.agent_workloads:
                if agent_id in self.agent_capabilities:
                    self.agent_capabilities[agent_id].current_load = 0

            # Remove from current allocations
            del self.current_allocations[allocation_id]

            #  Info - add observability event
