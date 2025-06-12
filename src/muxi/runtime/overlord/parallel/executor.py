"""
Parallel Executor for optimized workflows in MUXI Overlord.

This module executes optimized parallel workflows with real-time monitoring,
load balancing, and adaptive execution strategies.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

from .types import (
    TaskStatus,
    ExecutionPlan,
    OptimizedWorkflow,
    ParallelExecutionResult,
    ParallelGroup
)

logger = logging.getLogger(__name__)


@dataclass
class TaskExecution:
    """Runtime tracking for individual task execution."""
    task_id: str
    agent_id: str
    status: TaskStatus = TaskStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_context: Dict[str, Any] = None


class ParallelExecutor:
    """Executes optimized parallel workflows with real-time monitoring."""

    def __init__(self):
        """Initialize the parallel executor."""
        self.active_executions: Dict[str, ParallelExecutionResult] = {}
        self.execution_history: List[ParallelExecutionResult] = []

        # Task execution tracking
        self.task_executions: Dict[str, TaskExecution] = {}

        # Performance metrics
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0

    async def execute_workflow(
        self,
        optimized_workflow: OptimizedWorkflow,
        task_executor: Callable[[str, str, Dict[str, Any]], Any],
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> ParallelExecutionResult:
        """
        Execute an optimized workflow with parallel task execution.

        Args:
            optimized_workflow: The optimized workflow to execute
            task_executor: Function to execute individual tasks
            progress_callback: Optional callback for progress updates

        Returns:
            ParallelExecutionResult with execution details
        """
        execution_id = f"exec_{int(time.time())}_{optimized_workflow.workflow_id}"
        start_time = time.time()

        logger.info(f"Starting parallel execution {execution_id}")

        # Initialize execution result
        execution_result = ParallelExecutionResult(
            execution_id=execution_id,
            workflow_id=optimized_workflow.workflow_id,
            execution_plan=optimized_workflow.execution_plan,
            start_time=datetime.now()
        )

        # Track active execution
        self.active_executions[execution_id] = execution_result

        try:
            # Execute workflow groups in sequence
            await self._execute_workflow_groups(
                optimized_workflow.execution_plan,
                task_executor,
                execution_result,
                progress_callback
            )

            # Calculate final results
            end_time = time.time()
            execution_result.actual_duration = end_time - start_time
            execution_result.end_time = datetime.now()
            # Task completed successfully - status tracking removed

            # Calculate actual speedup
            await self._calculate_actual_speedup(execution_result, optimized_workflow)

            # Success metrics
            self.successful_executions += 1
            execution_result.success = True

            logger.info(f"Execution {execution_id} completed successfully. "
                       f"Duration: {execution_result.actual_duration:.1f}s, "
                       f"Speedup: {execution_result.actual_speedup:.1f}x")

        except Exception as e:
            # Handle execution failure
            # Task failed - status tracking removed
            execution_result.end_time = datetime.now()
            execution_result.execution_error = str(e)
            execution_result.success = False

            self.failed_executions += 1

            logger.error(f"Execution {execution_id} failed: {e}")

        finally:
            # Clean up
            self.total_executions += 1

            # Move to history
            self.execution_history.append(execution_result)
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]

            # Clean up task executions
            await self._cleanup_task_executions(execution_id)

        return execution_result

    async def _execute_workflow_groups(
        self,
        execution_plan: ExecutionPlan,
        task_executor: Callable,
        execution_result: ParallelExecutionResult,
        progress_callback: Optional[Callable] = None
    ) -> None:
        """Execute workflow groups in parallel according to the plan."""

        # Execute groups sequentially (groups contain parallel tasks)
        for group_index, group in enumerate(execution_plan.parallel_groups):
            logger.debug(f"Executing group {group.group_id} ({group_index + 1}/{len(execution_plan.parallel_groups)})")

            # Execute tasks in this group in parallel
            await self._execute_group_tasks(
                group,
                execution_plan.resource_allocation,
                task_executor,
                execution_result,
                progress_callback
            )

            # Update progress
            if progress_callback:
                progress = (group_index + 1) / len(execution_plan.parallel_groups)
                progress_callback({
                    "execution_id": execution_result.execution_id,
                    "progress": progress,
                    "current_group": group.group_id,
                    "completed_groups": group_index + 1,
                    "total_groups": len(execution_plan.parallel_groups)
                })

    async def _execute_group_tasks(
        self,
        group: ParallelGroup,
        resource_allocation: Any,
        task_executor: Callable,
        execution_result: ParallelExecutionResult,
        progress_callback: Optional[Callable] = None
    ) -> None:
        """Execute all tasks in a parallel group concurrently."""

        # Create task execution objects
        task_executions = []
        for task_id in group.task_ids:
            agent_id = resource_allocation.task_assignments.get(task_id)
            if not agent_id:
                logger.warning(f"No agent assigned to task {task_id}, skipping")
                continue

            task_execution = TaskExecution(
                task_id=task_id,
                agent_id=agent_id,
                execution_context={"group_id": group.group_id}
            )
            task_executions.append(task_execution)
            self.task_executions[f"{execution_result.execution_id}_{task_id}"] = task_execution

        # Execute tasks concurrently
        tasks = []
        for task_execution in task_executions:
            task = asyncio.create_task(
                self._execute_single_task(task_execution, task_executor, execution_result)
            )
            tasks.append(task)

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Update execution result
        for task_execution in task_executions:
            if task_execution.status == TaskStatus.COMPLETED:
                execution_result.completed_tasks.add(task_execution.task_id)
            elif task_execution.status == TaskStatus.FAILED:
                execution_result.failed_tasks.add(task_execution.task_id)

    async def _execute_single_task(
        self,
        task_execution: TaskExecution,
        task_executor: Callable,
        execution_result: ParallelExecutionResult
    ) -> None:
        """Execute a single task and track its progress."""

        task_execution.status = TaskStatus.RUNNING
        task_execution.start_time = time.time()

        try:
            logger.debug(f"Starting task {task_execution.task_id} on agent {task_execution.agent_id}")

            # Execute the task
            result = await task_executor(
                task_execution.task_id,
                task_execution.agent_id,
                task_execution.execution_context or {}
            )

            # Task completed successfully
            task_execution.result = result
            task_execution.status = TaskStatus.COMPLETED
            task_execution.end_time = time.time()

            logger.debug(f"Task {task_execution.task_id} completed successfully")

        except Exception as e:
            # Task failed
            task_execution.error = str(e)
            task_execution.status = TaskStatus.FAILED
            task_execution.end_time = time.time()

            logger.error(f"Task {task_execution.task_id} failed: {e}")

    async def _calculate_actual_speedup(
        self,
        execution_result: ParallelExecutionResult,
        optimized_workflow: OptimizedWorkflow
    ) -> None:
        """Calculate the actual speedup achieved during execution."""

        # Calculate sequential time (sum of all task times)
        total_task_time = 0.0
        for task_key, task_execution in self.task_executions.items():
            if task_key.startswith(execution_result.execution_id) and task_execution.start_time and task_execution.end_time:
                task_duration = task_execution.end_time - task_execution.start_time
                total_task_time += task_duration

        # Calculate actual speedup
        if execution_result.actual_duration > 0:
            execution_result.actual_speedup = total_task_time / execution_result.actual_duration
        else:
            execution_result.actual_speedup = 1.0

        # Compare to expected speedup
        expected_speedup = optimized_workflow.expected_speedup
        speedup_efficiency = execution_result.actual_speedup / max(expected_speedup, 1.0)
        execution_result.optimization_effectiveness = min(1.0, speedup_efficiency)

    async def _cleanup_task_executions(self, execution_id: str) -> None:
        """Clean up task execution tracking for a completed execution."""

        # Remove task executions for this execution
        keys_to_remove = [
            key for key in self.task_executions.keys()
            if key.startswith(execution_id)
        ]

        for key in keys_to_remove:
            del self.task_executions[key]

    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of an execution."""

        if execution_id in self.active_executions:
            execution = self.active_executions[execution_id]

            # Calculate progress
            total_tasks = len(execution.completed_tasks) + len(execution.failed_tasks)
            total_expected = sum(len(group.task_ids) for group in execution.execution_plan.parallel_groups)
            progress = total_tasks / max(total_expected, 1)

            # Get current task statuses
            current_tasks = {}
            for task_key, task_execution in self.task_executions.items():
                if task_key.startswith(execution_id):
                    current_tasks[task_execution.task_id] = {
                        "status": task_execution.status.value,
                        "agent_id": task_execution.agent_id,
                        "duration": (
                            time.time() - task_execution.start_time
                            if task_execution.start_time else 0
                        )
                    }

            return {
                "execution_id": execution_id,
                "status": execution.status.value,
                "progress": progress,
                "completed_tasks": len(execution.completed_tasks),
                "failed_tasks": len(execution.failed_tasks),
                "current_tasks": current_tasks,
                "elapsed_time": (datetime.now() - execution.start_time).total_seconds()
            }

        # Check history
        for execution in self.execution_history:
            if execution.execution_id == execution_id:
                return {
                    "execution_id": execution_id,
                    "status": execution.status.value,
                    "success": execution.success,
                    "duration": execution.actual_duration,
                    "speedup": execution.actual_speedup,
                    "completed_tasks": len(execution.completed_tasks),
                    "failed_tasks": len(execution.failed_tasks)
                }

        return None

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an active execution."""

        if execution_id not in self.active_executions:
            return False

        execution = self.active_executions[execution_id]
        # Mark as cancelled - status tracking removed
        execution.end_time = datetime.now()
        execution.success = False
        execution.execution_error = "Cancelled by user"

        # Move to history
        self.execution_history.append(execution)
        del self.active_executions[execution_id]

        # Clean up task executions
        await self._cleanup_task_executions(execution_id)

        logger.info(f"Execution {execution_id} cancelled")
        return True

    def get_execution_statistics(self) -> Dict[str, Any]:
        """Get overall execution statistics."""

        success_rate = (
            self.successful_executions / max(self.total_executions, 1) * 100
        )

        # Calculate average metrics from recent executions
        recent_executions = self.execution_history[-10:]  # Last 10
        avg_duration = 0.0
        avg_speedup = 0.0

        if recent_executions:
            valid_executions = [e for e in recent_executions if e.success and e.actual_duration]
            if valid_executions:
                avg_duration = sum(e.actual_duration for e in valid_executions) / len(valid_executions)
                avg_speedup = sum(e.actual_speedup for e in valid_executions) / len(valid_executions)

        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate_percentage": success_rate,
            "active_executions": len(self.active_executions),
            "average_duration_seconds": avg_duration,
            "average_speedup": avg_speedup,
            "recent_executions": len(recent_executions)
        }

    async def get_detailed_execution_report(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get a detailed report for a specific execution."""

        # Find execution in history
        execution = None
        for exec_result in self.execution_history:
            if exec_result.execution_id == execution_id:
                execution = exec_result
                break

        if not execution:
            return None

        # Gather task-level details
        task_details = []
        for task_key, task_execution in self.task_executions.items():
            if task_key.startswith(execution_id):
                task_detail = {
                    "task_id": task_execution.task_id,
                    "agent_id": task_execution.agent_id,
                    "status": task_execution.status.value,
                    "duration": (
                        task_execution.end_time - task_execution.start_time
                        if task_execution.start_time and task_execution.end_time else 0
                    ),
                    "error": task_execution.error
                }
                task_details.append(task_detail)

        return {
            "execution_id": execution_id,
            "workflow_id": execution.workflow_id,
            "success": execution.success,
            "total_duration": execution.actual_duration,
            "actual_speedup": execution.actual_speedup,
            "optimization_effectiveness": execution.optimization_effectiveness,
            "completed_tasks": len(execution.completed_tasks),
            "failed_tasks": len(execution.failed_tasks),
            "task_details": task_details,
            "execution_plan": {
                "total_groups": len(execution.execution_plan.parallel_groups),
                "max_parallelism": execution.execution_plan.get_max_group_size(),
                "estimated_duration": execution.execution_plan.estimated_total_time
            }
        }
