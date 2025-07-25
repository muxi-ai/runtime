"""
Bottleneck detection for parallel workflow optimization.

This module detects and analyzes bottlenecks in workflow execution to identify
performance constraints and suggest optimizations for parallel execution.
"""

from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict

from ...datatypes.parallel import (
    ResourceAllocation,
    BottleneckInfo,
    BottleneckType,
    ExecutionPlan,
    ParallelExecutionResult,
)


class BottleneckDetector:
    """Detects and analyzes bottlenecks in parallel workflow execution."""

    def __init__(self, sensitivity_threshold: float = 0.5):
        """
        Initialize bottleneck detector.

        Args:
            sensitivity_threshold: Threshold for bottleneck detection (0-1)
                                 Lower values detect more bottlenecks
        """
        self.sensitivity_threshold = sensitivity_threshold
        self.detection_history: List[Dict[str, Any]] = []
        self.bottleneck_patterns: Dict[str, int] = defaultdict(int)

    async def analyze_workflow_bottlenecks(
        self, execution_plan: ExecutionPlan, resource_allocation: ResourceAllocation
    ) -> List[BottleneckInfo]:
        """
        Analyze a workflow execution plan for potential bottlenecks.

        Args:
            execution_plan: The execution plan to analyze
            resource_allocation: The resource allocation for the plan

        Returns:
            List of detected bottlenecks
        """
        bottlenecks = []

        # Analyze different types of bottlenecks
        bottlenecks.extend(await self._detect_critical_path_bottlenecks(execution_plan))
        bottlenecks.extend(await self._detect_resource_bottlenecks(resource_allocation))
        bottlenecks.extend(await self._detect_dependency_bottlenecks(execution_plan))
        bottlenecks.extend(await self._detect_parallelization_bottlenecks(execution_plan))

        # Score and prioritize bottlenecks
        scored_bottlenecks = await self._score_bottlenecks(bottlenecks)

        # Filter by sensitivity threshold
        significant_bottlenecks = [
            bottleneck
            for bottleneck in scored_bottlenecks
            if bottleneck.severity_score >= self.sensitivity_threshold
        ]

        # Record detection
        await self._record_detection(execution_plan.plan_id, significant_bottlenecks)

        return significant_bottlenecks

    async def analyze_runtime_bottlenecks(
        self, execution_result: ParallelExecutionResult
    ) -> List[BottleneckInfo]:
        """
        Analyze runtime execution for actual bottlenecks that occurred.

        Args:
            execution_result: The completed execution result

        Returns:
            List of runtime bottlenecks
        """
        bottlenecks = []

        # Analyze timing-based bottlenecks
        bottlenecks.extend(await self._detect_timing_bottlenecks(execution_result))

        # Analyze failure-based bottlenecks
        bottlenecks.extend(await self._detect_failure_bottlenecks(execution_result))

        # Analyze efficiency bottlenecks
        bottlenecks.extend(await self._detect_efficiency_bottlenecks(execution_result))

        return bottlenecks

    async def suggest_optimizations(
        self, bottlenecks: List[BottleneckInfo]
    ) -> List[Dict[str, Any]]:
        """
        Suggest optimizations based on detected bottlenecks.

        Args:
            bottlenecks: List of detected bottlenecks

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        # Group bottlenecks by type for targeted suggestions
        bottleneck_groups = defaultdict(list)
        for bottleneck in bottlenecks:
            bottleneck_groups[bottleneck.bottleneck_type].append(bottleneck)

        # Generate type-specific suggestions
        for bottleneck_type, type_bottlenecks in bottleneck_groups.items():
            type_suggestions = await self._generate_type_specific_suggestions(
                bottleneck_type, type_bottlenecks
            )
            suggestions.extend(type_suggestions)

        # Sort by impact potential
        suggestions.sort(key=lambda x: x.get("impact_score", 0), reverse=True)

        return suggestions

    async def _detect_critical_path_bottlenecks(
        self, execution_plan: ExecutionPlan
    ) -> List[BottleneckInfo]:
        """Detect bottlenecks along the critical path."""
        bottlenecks = []

        # Check if critical path time is significantly longer than parallel time
        critical_path_ratio = execution_plan.critical_path_time / max(
            execution_plan.estimated_total_time, 1.0
        )

        if critical_path_ratio > 0.8:  # Critical path dominates execution time
            bottleneck = BottleneckInfo(
                bottleneck_id=f"critical_path_dominance_{execution_plan.plan_id}",
                bottleneck_type=BottleneckType.CRITICAL_PATH,
                affected_tasks=[],  # Would need to extract from plan
                severity_score=min(1.0, critical_path_ratio),
                estimated_delay=execution_plan.critical_path_time * 0.2,
                description=f"Critical path dominates execution time ({critical_path_ratio:.1%})",
                suggested_resolution="Break down critical path tasks or parallelize components",
                can_auto_resolve=False,
                resolution_confidence=0.6,
            )
            bottlenecks.append(bottleneck)

        # Check for groups with very uneven task durations
        for group in execution_plan.parallel_groups:
            if len(group.task_ids) > 1:
                # Would need task duration data to analyze distribution
                # This is a simplified check
                if group.estimated_duration > 120.0:  # Long-running group
                    bottleneck = BottleneckInfo(
                        bottleneck_id=f"long_group_{group.group_id}",
                        bottleneck_type=BottleneckType.CRITICAL_PATH,
                        affected_tasks=group.task_ids,
                        severity_score=min(1.0, group.estimated_duration / 300.0),
                        estimated_delay=group.estimated_duration * 0.1,
                        description=f"Long-running parallel group ({group.estimated_duration}s)",
                        suggested_resolution="Break down long tasks in this group",
                        can_auto_resolve=False,
                        resolution_confidence=0.4,
                    )
                    bottlenecks.append(bottleneck)

        return bottlenecks

    async def _detect_resource_bottlenecks(
        self, resource_allocation: ResourceAllocation
    ) -> List[BottleneckInfo]:
        """Detect resource-related bottlenecks."""
        bottlenecks = []

        # Check load balance
        if resource_allocation.load_balance_score < 0.6:  # Poor load balance
            bottleneck = BottleneckInfo(
                bottleneck_id=f"load_imbalance_{resource_allocation.allocation_id}",
                bottleneck_type=BottleneckType.AGENT_OVERLOAD,
                affected_tasks=[],
                severity_score=1.0 - resource_allocation.load_balance_score,
                estimated_delay=resource_allocation.total_estimated_time * 0.3,
                description=f"Poor load balance across agents ({resource_allocation.load_balance_score:.2f})",  # noqa: E501
                suggested_resolution="Redistribute tasks more evenly across agents",
                can_auto_resolve=True,
                resolution_confidence=0.8,
            )
            bottlenecks.append(bottleneck)

        # Check parallel efficiency
        if resource_allocation.parallel_efficiency < 0.5:  # Low parallelization
            bottleneck = BottleneckInfo(
                bottleneck_id=f"low_parallelization_{resource_allocation.allocation_id}",
                bottleneck_type=BottleneckType.RESOURCE_CONTENTION,
                affected_tasks=[],
                severity_score=1.0 - resource_allocation.parallel_efficiency,
                estimated_delay=resource_allocation.total_estimated_time * 0.5,
                description=f"Low parallel efficiency ({resource_allocation.parallel_efficiency:.2f})",  # noqa: E501
                suggested_resolution="Increase parallelization opportunities or add more agents",
                can_auto_resolve=False,
                resolution_confidence=0.5,
            )
            bottlenecks.append(bottleneck)

        # Check for highly utilized agents
        for agent_id, utilization in resource_allocation.utilization_scores.items():
            if utilization > 0.9:  # Over 90% utilization
                tasks = resource_allocation.agent_workloads.get(agent_id, [])
                bottleneck = BottleneckInfo(
                    bottleneck_id=f"agent_overutilization_{agent_id}",
                    bottleneck_type=BottleneckType.AGENT_OVERLOAD,
                    affected_tasks=tasks,
                    severity_score=utilization,
                    estimated_delay=len(tasks) * 10.0,  # Estimate 10s delay per task
                    description=f"Agent {agent_id} is over-utilized ({utilization:.1%})",
                    suggested_resolution=f"Redistribute some tasks from agent {agent_id}",
                    can_auto_resolve=True,
                    resolution_confidence=0.9,
                )
                bottlenecks.append(bottleneck)

        return bottlenecks

    async def _detect_dependency_bottlenecks(
        self, execution_plan: ExecutionPlan
    ) -> List[BottleneckInfo]:
        """Detect dependency-related bottlenecks."""
        bottlenecks = []

        # Check for too many sequential groups (poor parallelization)
        total_groups = len(execution_plan.parallel_groups)
        if total_groups > 8:  # Too many sequential levels
            bottleneck = BottleneckInfo(
                bottleneck_id=f"excessive_sequentiality_{execution_plan.plan_id}",
                bottleneck_type=BottleneckType.DEPENDENCY_CHAIN,
                affected_tasks=[],
                severity_score=min(1.0, total_groups / 20.0),
                estimated_delay=total_groups * 5.0,  # Estimate 5s overhead per level
                description=f"Too many sequential execution levels ({total_groups})",
                suggested_resolution="Reduce dependencies to enable more parallelization",
                can_auto_resolve=False,
                resolution_confidence=0.4,
            )
            bottlenecks.append(bottleneck)

        # Check for groups with only one task (missed parallelization)
        single_task_groups = [
            group for group in execution_plan.parallel_groups if len(group.task_ids) == 1
        ]

        if len(single_task_groups) > total_groups * 0.5:  # More than 50% single-task groups
            bottleneck = BottleneckInfo(
                bottleneck_id=f"missed_parallelization_{execution_plan.plan_id}",
                bottleneck_type=BottleneckType.DEPENDENCY_CHAIN,
                affected_tasks=[],
                severity_score=len(single_task_groups) / max(total_groups, 1),
                estimated_delay=len(single_task_groups) * 15.0,
                description="Many single-task groups indicate missed parallelization opportunities",
                suggested_resolution="Review dependencies to enable task grouping",
                can_auto_resolve=False,
                resolution_confidence=0.3,
            )
            bottlenecks.append(bottleneck)

        return bottlenecks

    async def _detect_parallelization_bottlenecks(
        self, execution_plan: ExecutionPlan
    ) -> List[BottleneckInfo]:
        """Detect parallelization-related bottlenecks."""
        bottlenecks = []

        # Check if we're not using enough agents concurrently
        max_concurrent = execution_plan.max_concurrent_agents
        max_group_size = execution_plan.get_max_group_size()

        if max_concurrent > 0 and max_group_size / max_concurrent < 0.5:
            bottleneck = BottleneckInfo(
                bottleneck_id=f"underutilized_agents_{execution_plan.plan_id}",
                bottleneck_type=BottleneckType.RESOURCE_CONTENTION,
                affected_tasks=[],
                severity_score=1.0 - (max_group_size / max_concurrent),
                estimated_delay=execution_plan.estimated_total_time * 0.2,
                description=f"Not fully utilizing available agents ({max_group_size}/{max_concurrent})",  # noqa: E501
                suggested_resolution="Increase parallelization or reduce agent count",
                can_auto_resolve=True,
                resolution_confidence=0.7,
            )
            bottlenecks.append(bottleneck)

        # Check speedup ratio
        if execution_plan.parallelization_speedup < 1.5:  # Less than 50% speedup
            bottleneck = BottleneckInfo(
                bottleneck_id=f"low_speedup_{execution_plan.plan_id}",
                bottleneck_type=BottleneckType.DEPENDENCY_CHAIN,
                affected_tasks=[],
                severity_score=1.0 - (execution_plan.parallelization_speedup / 2.0),
                estimated_delay=execution_plan.estimated_total_time * 0.3,
                description=f"Low parallelization speedup ({execution_plan.parallelization_speedup:.1f}x)",  # noqa: E501
                suggested_resolution="Restructure workflow for better parallelization",
                can_auto_resolve=False,
                resolution_confidence=0.4,
            )
            bottlenecks.append(bottleneck)

        return bottlenecks

    async def _detect_timing_bottlenecks(
        self, execution_result: ParallelExecutionResult
    ) -> List[BottleneckInfo]:
        """Detect bottlenecks based on actual execution timing."""
        bottlenecks = []

        # Check if actual time significantly exceeded estimated time
        time_overrun = (
            execution_result.actual_duration - execution_result.execution_plan.estimated_total_time
        )
        if time_overrun > 30.0:  # More than 30 seconds overrun
            overrun_ratio = time_overrun / execution_result.execution_plan.estimated_total_time
            bottleneck = BottleneckInfo(
                bottleneck_id=f"time_overrun_{execution_result.execution_id}",
                bottleneck_type=BottleneckType.CRITICAL_PATH,
                affected_tasks=[],
                severity_score=min(1.0, overrun_ratio),
                estimated_delay=time_overrun,
                description=f"Execution took {time_overrun:.1f}s longer than estimated",
                suggested_resolution="Improve time estimation or identify blocking factors",
                can_auto_resolve=False,
                resolution_confidence=0.6,
            )
            bottlenecks.append(bottleneck)

        return bottlenecks

    async def _detect_failure_bottlenecks(
        self, execution_result: ParallelExecutionResult
    ) -> List[BottleneckInfo]:
        """Detect bottlenecks based on task failures."""
        bottlenecks = []

        if execution_result.failed_tasks:
            failure_rate = len(execution_result.failed_tasks) / max(
                len(execution_result.completed_tasks) + len(execution_result.failed_tasks), 1
            )

            if failure_rate > 0.1:  # More than 10% failure rate
                bottleneck = BottleneckInfo(
                    bottleneck_id=f"high_failure_rate_{execution_result.execution_id}",
                    bottleneck_type=BottleneckType.AGENT_OVERLOAD,
                    affected_tasks=list(execution_result.failed_tasks),
                    severity_score=failure_rate,
                    estimated_delay=len(execution_result.failed_tasks) * 60.0,  # 1 min per failure
                    description=f"High task failure rate ({failure_rate:.1%})",
                    suggested_resolution="Investigate agent reliability or task complexity",
                    can_auto_resolve=False,
                    resolution_confidence=0.7,
                )
                bottlenecks.append(bottleneck)

        return bottlenecks

    async def _detect_efficiency_bottlenecks(
        self, execution_result: ParallelExecutionResult
    ) -> List[BottleneckInfo]:
        """Detect efficiency-related bottlenecks."""
        bottlenecks = []

        # Check if actual speedup was much lower than expected
        expected_speedup = execution_result.execution_plan.parallelization_speedup
        actual_speedup = execution_result.actual_speedup

        speedup_gap = expected_speedup - actual_speedup
        if speedup_gap > 0.5:  # Significant speedup gap
            bottleneck = BottleneckInfo(
                bottleneck_id=f"speedup_gap_{execution_result.execution_id}",
                bottleneck_type=BottleneckType.RESOURCE_CONTENTION,
                affected_tasks=[],
                severity_score=min(1.0, speedup_gap / expected_speedup),
                estimated_delay=execution_result.actual_duration * 0.2,
                description=f"Actual speedup ({actual_speedup:.1f}x) below expected ({expected_speedup:.1f}x)",  # noqa: E501
                suggested_resolution="Optimize resource allocation or reduce coordination overhead",
                can_auto_resolve=True,
                resolution_confidence=0.6,
            )
            bottlenecks.append(bottleneck)

        return bottlenecks

    async def _score_bottlenecks(self, bottlenecks: List[BottleneckInfo]) -> List[BottleneckInfo]:
        """Score and prioritize bottlenecks."""
        for bottleneck in bottlenecks:
            # Enhance severity score based on impact and resolution confidence
            impact_factor = bottleneck.estimated_delay / 60.0  # Convert to minutes

            # Adjust severity score
            bottleneck.severity_score = min(
                1.0, bottleneck.severity_score * (1 + impact_factor * 0.1)
            )

            # Track patterns
            pattern_key = f"{bottleneck.bottleneck_type.value}_{bottleneck.affected_tasks[:3]}"
            self.bottleneck_patterns[pattern_key] += 1

        # Sort by severity score
        bottlenecks.sort(key=lambda x: x.severity_score, reverse=True)
        return bottlenecks

    async def _record_detection(self, plan_id: str, bottlenecks: List[BottleneckInfo]) -> None:
        """Record bottleneck detection for historical analysis."""
        detection_record = {
            "timestamp": datetime.now().isoformat(),
            "plan_id": plan_id,
            "bottleneck_count": len(bottlenecks),
            "bottleneck_types": [b.bottleneck_type.value for b in bottlenecks],
            "total_severity": sum(b.severity_score for b in bottlenecks),
            "auto_resolvable": sum(1 for b in bottlenecks if b.can_auto_resolve),
        }

        self.detection_history.append(detection_record)

        # Keep only recent history (last 100 detections)
        if len(self.detection_history) > 100:
            self.detection_history = self.detection_history[-100:]

    async def _generate_type_specific_suggestions(
        self, bottleneck_type: BottleneckType, bottlenecks: List[BottleneckInfo]
    ) -> List[Dict[str, Any]]:
        """Generate optimization suggestions for a specific bottleneck type."""
        suggestions = []

        if bottleneck_type == BottleneckType.CRITICAL_PATH:
            suggestions.append(
                {
                    "type": "task_decomposition",
                    "description": "Break down critical path tasks into smaller parallel subtasks",
                    "impact_score": 0.8,
                    "effort_level": "medium",
                    "affected_bottlenecks": len(bottlenecks),
                }
            )

        elif bottleneck_type == BottleneckType.AGENT_OVERLOAD:
            suggestions.append(
                {
                    "type": "load_balancing",
                    "description": "Redistribute tasks more evenly across available agents",
                    "impact_score": 0.7,
                    "effort_level": "low",
                    "affected_bottlenecks": len(bottlenecks),
                }
            )

        elif bottleneck_type == BottleneckType.RESOURCE_CONTENTION:
            suggestions.append(
                {
                    "type": "resource_scaling",
                    "description": "Add more agents or optimize resource allocation",
                    "impact_score": 0.6,
                    "effort_level": "high",
                    "affected_bottlenecks": len(bottlenecks),
                }
            )

        elif bottleneck_type == BottleneckType.DEPENDENCY_CHAIN:
            suggestions.append(
                {
                    "type": "dependency_optimization",
                    "description": "Reduce unnecessary dependencies to enable more parallelization",
                    "impact_score": 0.9,
                    "effort_level": "high",
                    "affected_bottlenecks": len(bottlenecks),
                }
            )

        elif bottleneck_type == BottleneckType.CAPABILITY_SHORTAGE:
            suggestions.append(
                {
                    "type": "capability_expansion",
                    "description": "Add agents with required capabilities or cross-train existing agents",  # noqa: E501
                    "impact_score": 0.8,
                    "effort_level": "high",
                    "affected_bottlenecks": len(bottlenecks),
                }
            )

        return suggestions

    def get_detection_summary(self) -> Dict[str, Any]:
        """Get a summary of bottleneck detection history."""
        if not self.detection_history:
            return {}

        recent_detections = self.detection_history[-10:]  # Last 10 detections

        return {
            "total_detections": len(self.detection_history),
            "recent_detections": len(recent_detections),
            "average_bottlenecks_per_detection": sum(
                d["bottleneck_count"] for d in recent_detections
            )
            / len(recent_detections),
            "most_common_bottleneck_patterns": dict(
                sorted(self.bottleneck_patterns.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
            "auto_resolvable_percentage": sum(d["auto_resolvable"] for d in recent_detections)
            / max(sum(d["bottleneck_count"] for d in recent_detections), 1)
            * 100,
        }
