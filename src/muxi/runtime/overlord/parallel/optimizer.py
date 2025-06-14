"""
Parallel Workflow Optimizer for MUXI Overlord.

This module coordinates dependency analysis, resource management, and bottleneck
detection to create optimized parallel execution plans for complex workflows.
"""

import asyncio

import uuid
from typing import Dict, List, Any, Optional

from .types import (
    TaskNode,
    ParallelGroup,
    ResourceAllocation,
    BottleneckInfo,
    ExecutionPlan,
    OptimizedWorkflow,
    AgentCapability
)
from .dependency_analyzer import DependencyAnalyzer
from .resource_manager import ResourceManager
from .bottleneck_detector import BottleneckDetector




class ParallelWorkflowOptimizer:
    """
    Main optimizer that coordinates all parallel workflow optimization components.

    This class provides the high-level interface for optimizing workflows for
    parallel execution, combining dependency analysis, resource allocation,
    and bottleneck detection.
    """

    def __init__(self, sensitivity_threshold: float = 0.5):
        """
        Initialize the parallel workflow optimizer.

        Args:
            sensitivity_threshold: Threshold for bottleneck detection (0-1)
        """
        self.dependency_analyzer = DependencyAnalyzer()
        self.resource_manager = ResourceManager()
        self.bottleneck_detector = BottleneckDetector(sensitivity_threshold)

        self.optimization_history: List[OptimizedWorkflow] = []

    async def register_agent_capabilities(
        self,
        agent_capabilities: List[AgentCapability]
    ) -> None:
        """Register agent capabilities for resource allocation."""
        for capability in agent_capabilities:
            await self.resource_manager.register_agent(capability)

    async def optimize_workflow(
        self,
        workflow_definition: Dict[str, Any],
        available_agents: List[str],
        optimization_goals: Optional[Dict[str, Any]] = None
    ) -> OptimizedWorkflow:
        """
        Optimize a workflow for parallel execution.

        Args:
            workflow_definition: The workflow to optimize
            available_agents: List of available agent IDs
            optimization_goals: Optional optimization parameters

        Returns:
            OptimizedWorkflow with execution plan and metadata
        """
        workflow_id = workflow_definition.get('id', f"workflow_{uuid.uuid4().hex[:8]}")

        #  Info - add observability event

        # Step 1: Build dependency graph
        dependency_graph = await self.dependency_analyzer.build_dependency_graph(
            workflow_definition.get('tasks', {})
        )

        # Step 2: Validate dependencies
        validation_errors = await self.dependency_analyzer.validate_dependencies()
        if validation_errors:
            #  Warning - add observability event

        # Step 3: Find parallel groups
        parallel_groups = await self.dependency_analyzer.find_parallel_groups()

        # Step 4: Calculate critical path
        critical_path, critical_duration = await self.dependency_analyzer.calculate_critical_path()

        # Step 5: Optimize resource allocation
        resource_allocation = await self.resource_manager.optimize_allocation(
            parallel_groups, available_agents
        )

        # Step 6: Create execution plan
        execution_plan = ExecutionPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            parallel_groups=parallel_groups,
            resource_allocation=resource_allocation,
            execution_order=[group.group_id for group in parallel_groups]
        )

        # Calculate plan metrics
        await self._calculate_plan_metrics(execution_plan, critical_duration)

        # Step 7: Detect bottlenecks
        bottlenecks = await self.bottleneck_detector.analyze_workflow_bottlenecks(
            execution_plan, resource_allocation
        )
        execution_plan.bottlenecks = bottlenecks

        # Step 8: Generate optimization suggestions if needed
        optimization_suggestions = []
        if bottlenecks:
            optimization_suggestions = await self.bottleneck_detector.suggest_optimizations(
                bottlenecks
            )

        # Step 9: Create optimized workflow
        optimized_workflow = OptimizedWorkflow(
            workflow_id=workflow_id,
            original_workflow=workflow_definition,
            execution_plan=execution_plan,
            optimization_metadata={
                "optimization_goals": optimization_goals or {},
                "dependency_validation_errors": validation_errors,
                "bottleneck_count": len(bottlenecks),
                "optimization_suggestions": optimization_suggestions,
                "agent_count": len(available_agents),
                "task_count": len(dependency_graph)
            }
        )

        # Calculate optimization results
        await self._calculate_optimization_results(optimized_workflow)

        # Store in history
        self.optimization_history.append(optimized_workflow)

        #  Info - add observability event
                   f"Expected speedup: {optimized_workflow.expected_speedup:.1f}x, "
                   f"Confidence: {optimized_workflow.optimization_confidence:.2f}")

        return optimized_workflow

    async def reoptimize_workflow(
        self,
        optimized_workflow: OptimizedWorkflow,
        feedback: Optional[Dict[str, Any]] = None
    ) -> OptimizedWorkflow:
        """
        Re-optimize a workflow based on execution feedback.

        Args:
            optimized_workflow: Previously optimized workflow
            feedback: Execution feedback for improvement

        Returns:
            Re-optimized workflow
        """
        #  Info - add observability event

        # Update agent performance based on feedback
        if feedback and "agent_performance" in feedback:
            await self._update_agent_performance(feedback["agent_performance"])

        # Extract available agents from original allocation
        available_agents = list(
            optimized_workflow.execution_plan.resource_allocation.agent_workloads.keys()
        )

        # Re-run optimization with updated information
        return await self.optimize_workflow(
            optimized_workflow.original_workflow,
            available_agents,
            optimization_goals=feedback.get("optimization_goals")
        )

    async def analyze_optimization_effectiveness(
        self,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Analyze the effectiveness of optimization for a specific workflow.

        Args:
            workflow_id: ID of the workflow to analyze

        Returns:
            Analysis results
        """
        # Find workflow in history
        workflow_optimizations = [
            opt for opt in self.optimization_history
            if opt.workflow_id == workflow_id
        ]

        if not workflow_optimizations:
            return {"error": f"No optimization history found for workflow {workflow_id}"}

        latest_optimization = workflow_optimizations[-1]

        analysis = {
            "workflow_id": workflow_id,
            "optimization_count": len(workflow_optimizations),
            "latest_optimization": {
                "expected_speedup": latest_optimization.expected_speedup,
                "optimization_confidence": latest_optimization.optimization_confidence,
                "bottleneck_count": len(latest_optimization.execution_plan.bottlenecks),
                "parallel_groups": len(latest_optimization.execution_plan.parallel_groups),
                "max_parallelism": latest_optimization.execution_plan.get_max_group_size()
            }
        }

        # Calculate improvement over optimizations
        if len(workflow_optimizations) > 1:
            first_optimization = workflow_optimizations[0]
            improvement = {
                "speedup_improvement": (
                    latest_optimization.expected_speedup / first_optimization.expected_speedup
                ),
                "confidence_improvement": (
                    latest_optimization.optimization_confidence - first_optimization.optimization_confidence
                ),
                "bottleneck_reduction": (
                    len(first_optimization.execution_plan.bottlenecks) -
                    len(latest_optimization.execution_plan.bottlenecks)
                )
            }
            analysis["improvement_over_time"] = improvement

        return analysis

    async def get_optimization_recommendations(
        self,
        workflow_definition: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get optimization recommendations before running full optimization.

        Args:
            workflow_definition: The workflow to analyze

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Quick dependency analysis
        dependency_graph = await self.dependency_analyzer.build_dependency_graph(
            workflow_definition.get('tasks', {})
        )

        task_count = len(dependency_graph)

        # Basic workflow structure recommendations
        if task_count > 20:
            recommendations.append({
                "type": "complexity_warning",
                "priority": "high",
                "description": f"Large workflow with {task_count} tasks may benefit from decomposition",
                "suggested_action": "Consider breaking into smaller sub-workflows"
            })

        # Analyze task dependencies
        validation_errors = await self.dependency_analyzer.validate_dependencies()
        if validation_errors:
            recommendations.append({
                "type": "dependency_issues",
                "priority": "critical",
                "description": "Dependency validation found issues",
                "details": validation_errors,
                "suggested_action": "Fix dependency issues before optimization"
            })

        # Quick parallel group analysis
        parallel_groups = await self.dependency_analyzer.find_parallel_groups()
        max_parallelism = max(len(group.task_ids) for group in parallel_groups) if parallel_groups else 1

        if max_parallelism < task_count * 0.3:  # Less than 30% parallelizable
            recommendations.append({
                "type": "parallelization_opportunity",
                "priority": "medium",
                "description": f"Low parallelization potential ({max_parallelism}/{task_count} tasks)",
                "suggested_action": "Review dependencies to increase parallelization opportunities"
            })

        return recommendations

    async def _calculate_plan_metrics(
        self,
        execution_plan: ExecutionPlan,
        critical_duration: float
    ) -> None:
        """Calculate metrics for the execution plan."""

        # Calculate total estimated time (sum of group durations)
        execution_plan.estimated_total_time = sum(
            group.estimated_duration for group in execution_plan.parallel_groups
        )

        # Set critical path time
        execution_plan.critical_path_time = critical_duration

        # Calculate max concurrent agents needed
        execution_plan.max_concurrent_agents = max(
            len(group.task_ids) for group in execution_plan.parallel_groups
        ) if execution_plan.parallel_groups else 1

        # Calculate total agent time (sum of all task durations)
        execution_plan.total_agent_time = sum(
            group.estimated_duration * len(group.task_ids)
            for group in execution_plan.parallel_groups
        )

        # Calculate parallelization speedup
        if execution_plan.estimated_total_time > 0:
            sequential_time = execution_plan.total_agent_time
            execution_plan.parallelization_speedup = sequential_time / execution_plan.estimated_total_time
        else:
            execution_plan.parallelization_speedup = 1.0

        # Calculate plan confidence based on various factors
        confidence_factors = []

        # Resource allocation quality
        if execution_plan.resource_allocation.parallel_efficiency > 0:
            confidence_factors.append(execution_plan.resource_allocation.parallel_efficiency)

        # Load balance quality
        if execution_plan.resource_allocation.load_balance_score > 0:
            confidence_factors.append(execution_plan.resource_allocation.load_balance_score)

        # Parallelization effectiveness
        parallelization_effectiveness = min(1.0, execution_plan.parallelization_speedup / 5.0)
        confidence_factors.append(parallelization_effectiveness)

        # Calculate average confidence
        execution_plan.plan_confidence = sum(confidence_factors) / max(len(confidence_factors), 1)

    async def _calculate_optimization_results(
        self,
        optimized_workflow: OptimizedWorkflow
    ) -> None:
        """Calculate the results of optimization."""

        # Estimate original sequential execution time
        total_task_time = optimized_workflow.execution_plan.total_agent_time
        optimized_workflow.original_estimated_time = total_task_time

        # Get optimized time
        optimized_workflow.optimized_estimated_time = optimized_workflow.execution_plan.estimated_total_time

        # Calculate expected speedup
        if optimized_workflow.optimized_estimated_time > 0:
            optimized_workflow.expected_speedup = (
                optimized_workflow.original_estimated_time / optimized_workflow.optimized_estimated_time
            )
        else:
            optimized_workflow.expected_speedup = 1.0

        # Calculate optimization confidence
        plan_confidence = optimized_workflow.execution_plan.plan_confidence
        bottleneck_penalty = len(optimized_workflow.execution_plan.bottlenecks) * 0.1

        optimized_workflow.optimization_confidence = max(0.0, plan_confidence - bottleneck_penalty)

    async def _update_agent_performance(
        self,
        agent_performance: Dict[str, Dict[str, Any]]
    ) -> None:
        """Update agent performance based on execution feedback."""

        for agent_id, performance_data in agent_performance.items():
            if agent_id in self.resource_manager.agent_capabilities:
                agent = self.resource_manager.agent_capabilities[agent_id]

                # Update success rate
                if "success_rate" in performance_data:
                    agent.success_rate = performance_data["success_rate"]

                # Update average response time
                if "average_response_time" in performance_data:
                    agent.average_response_time = performance_data["average_response_time"]

                # Update capability scores
                if "capability_scores" in performance_data:
                    agent.performance_scores.update(performance_data["capability_scores"])

                #  Debug - add observability event

    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get a summary of optimization activities."""
        if not self.optimization_history:
            return {"total_optimizations": 0}

        recent_optimizations = self.optimization_history[-10:]  # Last 10

        return {
            "total_optimizations": len(self.optimization_history),
            "recent_optimizations": len(recent_optimizations),
            "average_speedup": sum(
                opt.expected_speedup for opt in recent_optimizations
            ) / len(recent_optimizations),
            "average_confidence": sum(
                opt.optimization_confidence for opt in recent_optimizations
            ) / len(recent_optimizations),
            "dependency_analyzer_summary": self.dependency_analyzer.get_execution_summary(),
            "bottleneck_detector_summary": self.bottleneck_detector.get_detection_summary()
        }
