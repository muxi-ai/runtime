"""
Dependency analysis for parallel workflow optimization.

This module analyzes task dependencies to identify groups of tasks that can
be executed in parallel, detects circular dependencies, and optimizes
execution order for maximum parallelization.
"""

import asyncio

from typing import Dict, List, Tuple, Any
from collections import defaultdict, deque

from ...datatypes.parallel import TaskNode, ParallelGroup, BottleneckInfo, BottleneckType


class DependencyAnalyzer:
    """Analyzes task dependencies to find optimal parallel execution strategies."""

    def __init__(self):
        self.dependency_graph: Dict[str, TaskNode] = {}
        self.parallel_groups: List[ParallelGroup] = []
        self.execution_levels: List[List[str]] = []

    async def build_dependency_graph(self, tasks: Dict[str, Any]) -> Dict[str, TaskNode]:
        """
        Build a dependency graph from workflow tasks.

        Args:
            tasks: Dictionary of task definitions from workflow

        Returns:
            Dictionary mapping task IDs to TaskNode objects
        """
        self.dependency_graph = {}

        # First pass: Create task nodes
        for task_id, task_data in tasks.items():
            task_node = TaskNode(
                task_id=task_id,
                description=task_data.get("description", ""),
                required_capabilities=task_data.get("required_capabilities", []),
                estimated_duration=task_data.get("estimated_duration", 30.0),
                priority=task_data.get("priority", 1),
                dependencies=set(task_data.get("dependencies", [])),
            )
            self.dependency_graph[task_id] = task_node

        # Second pass: Build bidirectional relationships
        for task_id, task_node in self.dependency_graph.items():
            for dependency_id in task_node.dependencies:
                if dependency_id in self.dependency_graph:
                    self.dependency_graph[dependency_id].dependents.add(task_id)
                else:
                    #  Warning - TODO: add observability
                    _ = dependency_id  # remove this after implementing observability

        return self.dependency_graph

    async def validate_dependencies(self) -> List[str]:
        """
        Validate the dependency graph for issues.

        Returns:
            List of validation error messages
        """
        errors = []

        # Check for circular dependencies
        circular_deps = await self._detect_circular_dependencies()
        if circular_deps:
            errors.append(f"Circular dependencies detected: {circular_deps}")

        # Check for missing dependencies
        for task_id, task_node in self.dependency_graph.items():
            for dep_id in task_node.dependencies:
                if dep_id not in self.dependency_graph:
                    errors.append(f"Task {task_id} depends on missing task {dep_id}")

        # Check for orphaned tasks (tasks with no path to completion)
        orphaned = await self._find_orphaned_tasks()
        if orphaned:
            errors.append(f"Orphaned tasks found: {orphaned}")

        return errors

    async def find_parallel_groups(self) -> List[ParallelGroup]:
        """
        Identify groups of tasks that can be executed in parallel.

        Returns:
            List of ParallelGroup objects representing parallelizable task groups
        """
        # Perform topological sort to get execution levels
        execution_levels = await self._topological_sort_levels()

        self.parallel_groups = []
        group_counter = 0

        for level_index, task_ids in enumerate(execution_levels):
            if not task_ids:
                continue

            # Create parallel group for this level
            group_id = f"group_{group_counter}"
            group_counter += 1

            parallel_group = ParallelGroup(
                group_id=group_id,
                task_ids=task_ids.copy(),
                group_priority=level_index + 1,  # Earlier levels have higher priority
            )

            # Calculate group metrics
            max_duration = 0.0
            total_capabilities = set()

            for task_id in task_ids:
                if task_id in self.dependency_graph:
                    task = self.dependency_graph[task_id]
                    max_duration = max(max_duration, task.estimated_duration)
                    total_capabilities.update(task.required_capabilities)

            parallel_group.estimated_duration = max_duration
            parallel_group.required_agents = len(task_ids)
            parallel_group.resource_requirements = {
                cap: sum(
                    1
                    for task_id in task_ids
                    if cap in self.dependency_graph[task_id].required_capabilities
                )
                for cap in total_capabilities
            }

            self.parallel_groups.append(parallel_group)

        return self.parallel_groups

    async def calculate_critical_path(self) -> Tuple[List[str], float]:
        """
        Calculate the critical path through the dependency graph.

        Returns:
            Tuple of (critical_path_task_ids, total_duration)
        """
        if not self.dependency_graph:
            return [], 0.0

        # Calculate longest path to each node
        distances = {}
        predecessors = {}

        # Initialize distances
        for task_id in self.dependency_graph:
            distances[task_id] = 0.0
            predecessors[task_id] = None

        # Find tasks with no dependencies (starting points)
        start_tasks = [
            task_id for task_id, task in self.dependency_graph.items() if not task.dependencies
        ]

        # Use a modified Bellman-Ford algorithm for longest path
        for _ in range(len(self.dependency_graph)):
            updated = False
            for task_id, task in self.dependency_graph.items():
                for dep_id in task.dependencies:
                    if dep_id in self.dependency_graph:
                        new_distance = distances[dep_id] + task.estimated_duration
                        if new_distance > distances[task_id]:
                            distances[task_id] = new_distance
                            predecessors[task_id] = dep_id
                            updated = True

            if not updated:
                break

        # Find the task with maximum distance (end of critical path)
        if not distances:
            return [], 0.0

        end_task = max(distances.keys(), key=lambda x: distances[x])
        critical_path_duration = distances[end_task]

        # Reconstruct critical path
        critical_path = []
        current = end_task
        while current is not None:
            critical_path.append(current)
            current = predecessors[current]

        critical_path.reverse()
        return critical_path, critical_path_duration

    async def analyze_bottlenecks(self) -> List[BottleneckInfo]:
        """
        Analyze the dependency graph to identify potential bottlenecks.

        Returns:
            List of BottleneckInfo objects describing potential bottlenecks
        """
        bottlenecks = []

        # Analyze dependency chains
        await self._analyze_dependency_chains(bottlenecks)

        # Analyze resource contention
        await self._analyze_resource_contention(bottlenecks)

        # Analyze critical path bottlenecks
        await self._analyze_critical_path_bottlenecks(bottlenecks)

        return bottlenecks

    async def _detect_circular_dependencies(self) -> List[List[str]]:
        """Detect circular dependencies using DFS."""
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(task_id: str, path: List[str]) -> None:
            if task_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(task_id)
                cycle = path[cycle_start:] + [task_id]
                cycles.append(cycle)
                return

            if task_id in visited:
                return

            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task_id)

            # Visit dependencies
            if task_id in self.dependency_graph:
                for dep_id in self.dependency_graph[task_id].dependencies:
                    if dep_id in self.dependency_graph:
                        dfs(dep_id, path.copy())

            rec_stack.remove(task_id)

        for task_id in self.dependency_graph:
            if task_id not in visited:
                dfs(task_id, [])

        return cycles

    async def _find_orphaned_tasks(self) -> List[str]:
        """Find tasks that cannot be reached from any starting point."""
        # Find all reachable tasks from tasks with no dependencies
        start_tasks = [
            task_id for task_id, task in self.dependency_graph.items() if not task.dependencies
        ]

        if not start_tasks:
            # If no start tasks, all tasks are potentially orphaned
            return list(self.dependency_graph.keys())

        reachable = set()
        queue = deque(start_tasks)

        while queue:
            current = queue.popleft()
            if current in reachable:
                continue

            reachable.add(current)

            # Add all dependents to queue
            if current in self.dependency_graph:
                for dependent in self.dependency_graph[current].dependents:
                    if dependent not in reachable:
                        queue.append(dependent)

        # Return tasks that are not reachable
        all_tasks = set(self.dependency_graph.keys())
        orphaned = all_tasks - reachable
        return list(orphaned)

    async def _topological_sort_levels(self) -> List[List[str]]:
        """
        Perform topological sort and group tasks into execution levels.

        Returns:
            List of lists, where each inner list contains task IDs that can
            be executed at the same level (in parallel)
        """
        # Calculate in-degrees
        in_degree = {
            task_id: len(task.dependencies) for task_id, task in self.dependency_graph.items()
        }

        # Initialize queue with tasks that have no dependencies
        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])

        execution_levels = []

        while queue:
            # All tasks in current queue can be executed in parallel
            current_level = []
            next_queue = deque()

            # Process all tasks at current level
            while queue:
                task_id = queue.popleft()
                current_level.append(task_id)

                # Reduce in-degree of dependents
                if task_id in self.dependency_graph:
                    for dependent in self.dependency_graph[task_id].dependents:
                        in_degree[dependent] -= 1
                        if in_degree[dependent] == 0:
                            next_queue.append(dependent)

            if current_level:
                execution_levels.append(current_level)

            queue = next_queue

        return execution_levels

    async def _analyze_dependency_chains(self, bottlenecks: List[BottleneckInfo]) -> None:
        """Analyze for long dependency chains that limit parallelization."""
        critical_path, duration = await self.calculate_critical_path()

        if len(critical_path) > 5:  # Threshold for "long" chain
            bottleneck = BottleneckInfo(
                bottleneck_id=f"dependency_chain_{len(critical_path)}",
                bottleneck_type=BottleneckType.DEPENDENCY_CHAIN,
                affected_tasks=critical_path,
                severity_score=min(1.0, len(critical_path) / 20.0),  # Scale severity
                estimated_delay=duration * 0.2,  # Estimate 20% overhead
                description=f"Long dependency chain of {len(critical_path)} tasks limits parallelization",  # noqa: E501
                suggested_resolution="Consider breaking dependencies or parallelizing sub-tasks",
                can_auto_resolve=False,
                resolution_confidence=0.3,
            )
            bottlenecks.append(bottleneck)

    async def _analyze_resource_contention(self, bottlenecks: List[BottleneckInfo]) -> None:
        """Analyze for resource contention based on capability requirements."""
        capability_usage = defaultdict(list)

        # Group tasks by required capabilities
        for task_id, task in self.dependency_graph.items():
            for capability in task.required_capabilities:
                capability_usage[capability].append(task_id)

        # Find capabilities with high contention
        for capability, task_ids in capability_usage.items():
            if len(task_ids) > 3:  # Threshold for high contention
                bottleneck = BottleneckInfo(
                    bottleneck_id=f"resource_contention_{capability}",
                    bottleneck_type=BottleneckType.RESOURCE_CONTENTION,
                    affected_tasks=task_ids,
                    severity_score=min(1.0, len(task_ids) / 10.0),
                    estimated_delay=len(task_ids) * 5.0,  # Estimate 5s per conflicting task
                    description=f"High contention for '{capability}' capability among {len(task_ids)} tasks",  # noqa: E501
                    suggested_resolution=f"Add more agents with '{capability}' capability",
                    can_auto_resolve=True,
                    resolution_confidence=0.7,
                    resource_context={"capability": capability, "contending_tasks": task_ids},
                )
                bottlenecks.append(bottleneck)

    async def _analyze_critical_path_bottlenecks(self, bottlenecks: List[BottleneckInfo]) -> None:
        """Analyze critical path for potential bottlenecks."""
        critical_path, duration = await self.calculate_critical_path()

        if not critical_path:
            return

        # Find tasks on critical path with high duration
        for task_id in critical_path:
            if task_id in self.dependency_graph:
                task = self.dependency_graph[task_id]
                if task.estimated_duration > 60.0:  # Threshold for "long" task
                    bottleneck = BottleneckInfo(
                        bottleneck_id=f"critical_path_task_{task_id}",
                        bottleneck_type=BottleneckType.CRITICAL_PATH,
                        affected_tasks=[task_id],
                        severity_score=min(
                            1.0, task.estimated_duration / 300.0
                        ),  # Scale by 5 minutes
                        estimated_delay=task.estimated_duration * 0.1,  # 10% overhead
                        description=f"Long-running task '{task_id}' on critical path ({task.estimated_duration}s)",  # noqa: E501
                        suggested_resolution="Consider breaking task into smaller subtasks",
                        can_auto_resolve=False,
                        resolution_confidence=0.4,
                    )
                    bottlenecks.append(bottleneck)

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get a summary of the dependency analysis."""
        if not self.dependency_graph:
            return {}

        total_tasks = len(self.dependency_graph)
        total_groups = len(self.parallel_groups)
        max_parallelism = (
            max(len(group.task_ids) for group in self.parallel_groups)
            if self.parallel_groups
            else 1
        )

        critical_path, critical_duration = asyncio.run(self.calculate_critical_path())

        return {
            "total_tasks": total_tasks,
            "parallel_groups": total_groups,
            "max_parallelism": max_parallelism,
            "critical_path_length": len(critical_path),
            "critical_path_duration": critical_duration,
            "average_group_size": sum(len(g.task_ids) for g in self.parallel_groups)
            / max(total_groups, 1),
            "parallelization_ratio": max_parallelism / max(total_tasks, 1),
        }
