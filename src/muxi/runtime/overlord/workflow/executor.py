import asyncio
from typing import Optional, Dict, Any, List, Set, Callable
from datetime import datetime
import json
# Loguru import removed - add observability import

from .types import (
    Workflow, SubTask, TaskStatus, WorkflowStatus,
    TaskResult, build_execution_phases
)
from ...agent import Agent


class WorkflowExecutor:
    """
    Manages execution of multi-agent workflows with DAG-based orchestration.

    The WorkflowExecutor coordinates multiple agents to complete complex workflows,
    ensuring proper dependency ordering and parallel execution where possible.
    """

    def __init__(self, agent_registry: Dict[str, Agent]):
        """
        Initialize workflow executor.

        Args:
            agent_registry: Dictionary mapping agent IDs to Agent instances
        """
        self.agent_registry = agent_registry
        self.active_workflows: Dict[str, Workflow] = {}
        self.task_results: Dict[str, TaskResult] = {}

        # Progress tracking callbacks
        self.progress_callbacks: List[Callable[[str, Workflow], None]] = []

    async def execute_workflow(
        self,
        workflow: Workflow,
        context: Optional[Dict[str, Any]] = None
    ) -> Workflow:
        """
        Execute complete workflow with DAG orchestration.

        Execution Strategy:
        1. Build execution phases based on dependencies
        2. Execute phases sequentially with parallel task execution within phases
        3. Track task results and propagate outputs to dependent tasks
        4. Handle failures gracefully with partial completion
        5. Report progress throughout execution

        Args:
            workflow: Workflow to execute
            context: Optional execution context

        Returns:
            Updated workflow with execution results
        """
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()

        # Track this workflow
        self.active_workflows[workflow.id] = workflow

        try:
            # Build execution phases
            phases = build_execution_phases(workflow)
            #  Info - add observability event

            # Execute each phase
            for phase_num, task_ids in enumerate(phases, 1):
                #  Info - add observability event

                # Execute tasks in parallel within this phase
                await self._execute_phase(workflow, task_ids, context)

                # Check if we should continue
                if not self._should_continue_execution(workflow):
                    break

                # Update progress
                self._notify_progress(workflow.id, workflow)

            # Finalize workflow
            workflow.completed_at = datetime.now()
            workflow.status = self._determine_final_status(workflow)

            #  Info - add observability event

        except Exception as e:
            #  Error - add observability event
            workflow.status = WorkflowStatus.FAILED
            workflow.error_message = str(e)
            workflow.completed_at = datetime.now()

        finally:
            # Clean up
            if workflow.id in self.active_workflows:
                del self.active_workflows[workflow.id]

        return workflow

    async def _execute_phase(
        self,
        workflow: Workflow,
        task_ids: List[str],
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Execute all tasks in a phase concurrently.

        Args:
            workflow: Workflow being executed
            task_ids: Task IDs in this phase
            context: Optional execution context
        """
        # Create coroutines for all tasks in this phase
        task_coroutines = []
        for task_id in task_ids:
            if task_id in workflow.tasks:
                coroutine = self._execute_task(workflow.tasks[task_id], workflow, context)
                task_coroutines.append(coroutine)

        # Execute all tasks concurrently
        if task_coroutines:
            await asyncio.gather(*task_coroutines, return_exceptions=True)

    async def _execute_task(
        self,
        task: SubTask,
        workflow: Workflow,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        Execute individual task by routing to appropriate agent.

        Args:
            task: Task to execute
            workflow: Parent workflow
            context: Optional execution context

        Returns:
            Task execution result
        """
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()

        try:
            # Collect inputs from dependencies
            task_inputs = await self._collect_task_inputs(task, workflow)

            # Build execution context
            execution_context = {
                "workflow_id": workflow.id,
                "task_id": task.id,
                "user_request": workflow.user_request,
                "task_description": task.description,
                "inputs": task_inputs,
                **(context or {})
            }

            # Select and execute with appropriate agent
            agent = self._select_agent_for_task(task)
            if not agent:
                raise ValueError(f"No suitable agent found for task {task.id}")

            #  Info - add observability event

            # Execute task
            result = await self._execute_task_with_agent(
                task, agent, execution_context
            )

            # Store result
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now()
            task.outputs = result.outputs if result else {}

            # Store in results cache
            if result:
                self.task_results[task.id] = result

            #  Info - add observability event
            return result

        except Exception as e:
            #  Error - add observability event
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now()

            # Create error result
            error_result = TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                outputs={},
                error_message=str(e)
            )
            self.task_results[task.id] = error_result
            return error_result

    async def _collect_task_inputs(
        self,
        task: SubTask,
        workflow: Workflow
    ) -> Dict[str, Any]:
        """
        Collect outputs from dependency tasks as inputs.

        Args:
            task: Task to collect inputs for
            workflow: Parent workflow

        Returns:
            Dictionary of collected inputs
        """
        inputs = {}

        for dep_task_id in task.dependencies:
            if dep_task_id in self.task_results:
                result = self.task_results[dep_task_id]
                inputs[f"from_{dep_task_id}"] = result.outputs
            elif dep_task_id in workflow.tasks:
                # Dependency task exists but no result yet
                dep_task = workflow.tasks[dep_task_id]
                if dep_task.status == TaskStatus.DONE:
                    inputs[f"from_{dep_task_id}"] = dep_task.outputs or {}

        return inputs

    def _select_agent_for_task(self, task: SubTask) -> Optional[Agent]:
        """
        Select best agent for task based on required capabilities.

        Args:
            task: Task to find agent for

        Returns:
            Selected agent or None if no suitable agent found
        """
        # For now, simple selection based on first required capability
        # In a full implementation, this would use sophisticated matching

        if not task.required_capabilities:
            # Use any available agent
            return next(iter(self.agent_registry.values()), None)

        # Try to find agent with matching capability
        for capability in task.required_capabilities:
            # Look for agents with matching specialization
            for agent_id, agent in self.agent_registry.items():
                # Simple matching - in real implementation would be more sophisticated
                if capability in ['research', 'writing', 'analysis', 'coding', 'general']:
                    return agent

        # Fallback to any available agent
        return next(iter(self.agent_registry.values()), None)

    async def _execute_task_with_agent(
        self,
        task: SubTask,
        agent: Agent,
        context: Dict[str, Any]
    ) -> TaskResult:
        """
        Execute task with selected agent.

        Args:
            task: Task to execute
            agent: Agent to execute with
            context: Execution context

        Returns:
            Task execution result
        """
        # Create task prompt
        task_prompt = self._create_task_prompt(task, context)

        try:
            # Execute with agent
            response = await agent.process_message(
                task_prompt,
                user_id=context.get('user_id', 0),
                conversation_id=context.get('conversation_id'),
                context=context
            )

            # Parse response into structured outputs
            outputs = self._parse_task_response(response, task)

            return TaskResult(
                task_id=task.id,
                agent_id=agent.agent_id,
                status=TaskStatus.DONE,
                outputs=outputs,
                raw_response=response
            )

        except Exception as e:
            #  Error - add observability event
            return TaskResult(
                task_id=task.id,
                agent_id=agent.agent_id,
                status=TaskStatus.FAILED,
                outputs={},
                error_message=str(e)
            )

    def _create_task_prompt(self, task: SubTask, context: Dict[str, Any]) -> str:
        """
        Create prompt for task execution.

        Args:
            task: Task to create prompt for
            context: Execution context

        Returns:
            Task execution prompt
        """
        prompt_parts = [
            f"## Task: {task.description}",
            f"",
            f"Original Request: {context.get('user_request', 'N/A')}",
            f"",
            f"Task Details:",
            f"- Required Capabilities: {', '.join(task.required_capabilities)}",
            f"- Estimated Complexity: {task.estimated_complexity}/10"
        ]

        # Add inputs if available
        if context.get('inputs'):
            prompt_parts.extend([
                f"",
                f"Available Inputs:",
                json.dumps(context['inputs'], indent=2)
            ])

        prompt_parts.extend([
            f"",
            f"Please complete this task thoroughly and provide the results.",
            f"Focus on delivering exactly what's needed for this specific task."
        ])

        return "\n".join(prompt_parts)

    def _parse_task_response(self, response: str, task: SubTask) -> Dict[str, Any]:
        """
        Parse agent response into structured outputs.

        Args:
            response: Raw agent response
            task: Task that was executed

        Returns:
            Structured outputs dictionary
        """
        # For now, simple output structure
        # In full implementation, would parse based on task type and expected outputs

        outputs = {
            "content": response,
            "task_id": task.id,
            "completed": True
        }

        # Add capability-specific parsing
        if 'research' in task.required_capabilities:
            outputs["research_findings"] = response
        elif 'writing' in task.required_capabilities:
            outputs["written_content"] = response
        elif 'analysis' in task.required_capabilities:
            outputs["analysis_results"] = response

        return outputs

    def _should_continue_execution(self, workflow: Workflow) -> bool:
        """
        Determine if workflow execution should continue.

        Args:
            workflow: Workflow to check

        Returns:
            True if execution should continue
        """
        # Check if any critical tasks failed
        critical_failures = [
            task for task in workflow.tasks.values()
            if task.status == TaskStatus.FAILED
        ]

        # For now, continue unless there are critical failures
        # In full implementation, would have more sophisticated failure handling
        return len(critical_failures) == 0

    def _determine_final_status(self, workflow: Workflow) -> WorkflowStatus:
        """
        Determine final workflow status based on task results.

        Args:
            workflow: Workflow to analyze

        Returns:
            Final workflow status
        """
        task_statuses = [task.status for task in workflow.tasks.values()]

        if all(status == TaskStatus.DONE for status in task_statuses):
            return WorkflowStatus.COMPLETED
        elif any(status == TaskStatus.FAILED for status in task_statuses):
            return WorkflowStatus.FAILED
        else:
            return WorkflowStatus.FAILED  # Incomplete execution

    def _notify_progress(self, workflow_id: str, workflow: Workflow):
        """
        Notify progress callbacks of workflow updates.

        Args:
            workflow_id: ID of workflow
            workflow: Updated workflow
        """
        for callback in self.progress_callbacks:
            try:
                callback(workflow_id, workflow)
            except Exception as e:
                #  Error - add observability event

    # Public methods for workflow management

    def add_progress_callback(self, callback: Callable[[str, Workflow], None]):
        """
        Add callback for workflow progress updates.

        Args:
            callback: Function to call with (workflow_id, workflow) on updates
        """
        self.progress_callbacks.append(callback)

    def get_workflow_status(self, workflow_id: str) -> Optional[Workflow]:
        """
        Get current status of active workflow.

        Args:
            workflow_id: ID of workflow to check

        Returns:
            Current workflow state or None if not found
        """
        return self.active_workflows.get(workflow_id)

    def get_active_workflows(self) -> Dict[str, Workflow]:
        """
        Get all currently active workflows.

        Returns:
            Dictionary of active workflows
        """
        return self.active_workflows.copy()

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel an active workflow.

        Args:
            workflow_id: ID of workflow to cancel

        Returns:
            True if workflow was cancelled successfully
        """
        if workflow_id in self.active_workflows:
            workflow = self.active_workflows[workflow_id]
            workflow.status = WorkflowStatus.CANCELLED
            workflow.completed_at = datetime.now()

            # Cancel in-progress tasks
            for task in workflow.tasks.values():
                if task.status == TaskStatus.IN_PROGRESS:
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = datetime.now()

            #  Info - add observability event
            return True

        return False

    def get_workflow_progress(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get progress information for a workflow.

        Args:
            workflow_id: ID of workflow

        Returns:
            Progress information or None if workflow not found
        """
        if workflow_id not in self.active_workflows:
            return None

        workflow = self.active_workflows[workflow_id]
        total_tasks = len(workflow.tasks)
        completed_tasks = sum(1 for task in workflow.tasks.values() if task.status == TaskStatus.DONE)
        failed_tasks = sum(1 for task in workflow.tasks.values() if task.status == TaskStatus.FAILED)
        in_progress_tasks = sum(1 for task in workflow.tasks.values() if task.status == TaskStatus.IN_PROGRESS)

        return {
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "progress_percentage": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "started_at": workflow.started_at.isoformat() if workflow.started_at else None
        }


class ProgressTracker:
    """
    Track and report workflow execution progress.
    """

    def __init__(self):
        self.workflow_progress: Dict[str, Dict[str, Any]] = {}

    def update_workflow_progress(self, workflow_id: str, workflow: Workflow):
        """
        Update progress tracking for a workflow.

        Args:
            workflow_id: ID of workflow
            workflow: Updated workflow
        """
        total_tasks = len(workflow.tasks)
        completed_tasks = sum(1 for task in workflow.tasks.values() if task.status == TaskStatus.DONE)
        failed_tasks = sum(1 for task in workflow.tasks.values() if task.status == TaskStatus.FAILED)

        progress_info = {
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "progress_percentage": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "last_updated": datetime.now().isoformat()
        }

        self.workflow_progress[workflow_id] = progress_info

        #  Info - add observability event
            f"Workflow {workflow_id} progress: {completed_tasks}/{total_tasks} tasks completed "
            f"({progress_info['progress_percentage']:.1f}%)"
        )

    def get_progress(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get progress information for a workflow.

        Args:
            workflow_id: ID of workflow

        Returns:
            Progress information or None if not found
        """
        return self.workflow_progress.get(workflow_id)

    def cleanup_completed_workflows(self):
        """
        Clean up progress tracking for completed workflows.
        """
        # Keep progress info for completed workflows for a while
        # In full implementation, would have configurable retention
        pass
