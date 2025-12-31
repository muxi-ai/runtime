import asyncio
from collections import defaultdict
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
import json
import re

from ...datatypes.workflow import (
    Workflow,
    SubTask,
    TaskStatus,
    WorkflowStatus,
    TaskResult,
    build_execution_phases,
)
from ...datatypes.workflow_models import (
    TaskSpecification,
    TaskExecutionState,
    create_execution_result,
)
from ...services import observability, streaming
from ...datatypes.exceptions import WorkflowTimeoutError

from ..agents.agent import Agent

from .config import (
    WorkflowConfig,
    WorkflowErrorHandler,
    TaskRoutingStrategy,
    AgentRoutingRule,
)


class WorkflowExecutor:
    """
    Manages execution of multi-agent workflows with DAG-based orchestration.

    The WorkflowExecutor coordinates multiple agents to complete complex workflows,
    ensuring proper dependency ordering and parallel execution where possible.
    Enhanced with configurable error handling, retry logic, and routing strategies.
    """

    def __init__(self, agent_registry: Dict[str, Agent], config: Optional[WorkflowConfig] = None):
        """
        Initialize workflow executor with enhanced configuration.

        Args:
            agent_registry: Dictionary mapping agent IDs to Agent instances
            config: Enhanced workflow configuration
        """
        self.agent_registry = agent_registry
        self.config = config or WorkflowConfig()
        self.error_handler = WorkflowErrorHandler(self.config)

        self.active_workflows: Dict[str, Workflow] = {}
        self.task_results: Dict[str, TaskResult] = {}
        self.workflow_history: Dict[str, Workflow] = {}  # Track completed workflows

        # Enhanced tracking
        self.agent_task_history: Dict[str, List[Dict[str, Any]]] = defaultdict(
            list
        )  # Track agent performance
        self.workflow_start_times: Dict[str, datetime] = {}
        self.task_execution_times: Dict[str, float] = {}  # Track task execution times

        # Custom routing function
        self.custom_routing_fn: Optional[Callable] = None
        self.routing_rules: List[AgentRoutingRule] = []

        # Progress tracking callbacks
        self.progress_callbacks: List[Callable[[str, Workflow], None]] = []

        # Round-robin routing index
        self._rr_index: int = 0

    async def _workflow_timeout_monitor(self, workflow_id: str):
        """Monitor workflow timeout"""
        try:
            if not self.config.timeout_config.workflow_timeout:
                return

            await asyncio.sleep(self.config.timeout_config.workflow_timeout)

            # Check if workflow still active
            if workflow_id in self.active_workflows:
                workflow = self.active_workflows[workflow_id]
                if workflow.status == WorkflowStatus.IN_PROGRESS:
                    # Cancel all in-progress tasks
                    for task in workflow.tasks.values():
                        if task.status == TaskStatus.IN_PROGRESS:
                            task.status = TaskStatus.FAILED
                            task.error_message = "Workflow timeout exceeded"
                            task.end_time = datetime.now()

                    workflow.status = WorkflowStatus.FAILED
                    workflow.completed_at = datetime.now()
                    # Note: Workflow model doesn't have error_message field

                    # Log timeout event
                    observability.observe(
                        event_type=observability.ErrorEvents.CONNECTION_TIMEOUT,
                        level=observability.EventLevel.WARNING,
                        data={
                            "workflow_id": workflow_id,
                            "timeout": self.config.timeout_config.workflow_timeout,
                            "status": "workflow_timeout_enforced",
                        },
                        description=(
                            f"Workflow {workflow_id} timed out after "
                            f"{self.config.timeout_config.workflow_timeout}s"
                        ),
                    )

        except asyncio.CancelledError:
            # Task was cancelled, this is expected behavior
            pass
        except Exception as e:
            # Log any unexpected errors but don't crash
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "function": "_workflow_timeout_monitor",
                },
                description=f"Error in workflow timeout monitor: {str(e)}",
            )

    def _validate_and_initialize_workflow(
        self, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Validate workflow inputs and initialize workflow state.

        Args:
            workflow: Workflow to validate and initialize
            context: Optional execution context to validate

        Raises:
            ValueError: If validation fails
        """
        # Validate workflow
        if not isinstance(workflow, Workflow):
            raise ValueError("Workflow must be a Workflow instance")
        if not workflow.id:
            raise ValueError("Workflow must have an ID")
        if not workflow.tasks:
            raise ValueError("Workflow must have at least one task")

        # Validate context
        if context is not None and not isinstance(context, dict):
            raise ValueError("Context must be a dictionary or None")

        # Initialize workflow state
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()
        self.workflow_start_times[workflow.id] = workflow.started_at

        # Track this workflow
        self.active_workflows[workflow.id] = workflow

    async def execute_workflow(
        self, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> Workflow:
        """
        Execute complete workflow with DAG orchestration and enhanced error handling.

        Execution Strategy:
        1. Build execution phases based on dependencies
        2. Execute phases sequentially with parallel task execution within phases
        3. Track task results and propagate outputs to dependent tasks
        4. Handle failures with configured recovery strategies
        5. Apply timeouts and resource limits
        6. Report progress throughout execution

        Args:
            workflow: Workflow to execute
            context: Optional execution context

        Returns:
            Updated workflow with execution results
        """
        # Wrap entire execution with hard max timeout if configured
        max_timeout = self.config.timeout_config.max_timeout_seconds
        if max_timeout:
            try:
                return await asyncio.wait_for(
                    self._execute_workflow_internal(workflow, context),
                    timeout=max_timeout
                )
            except asyncio.TimeoutError:
                # Workflow exceeded maximum allowed time
                workflow.status = WorkflowStatus.FAILED
                workflow.completed_at = datetime.now()

                elapsed = (workflow.completed_at - workflow.started_at).total_seconds() if workflow.started_at else 0

                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "workflow_id": workflow.id,
                        "failure_reason": "max_timeout_exceeded",
                        "max_timeout_seconds": max_timeout,
                        "elapsed_seconds": elapsed,
                        "total_tasks": len(workflow.tasks),
                        "completed_tasks": sum(1 for t in workflow.tasks.values() if t.status == TaskStatus.COMPLETED),
                    },
                    description=(
                        f"Workflow {workflow.id} exceeded maximum timeout of {max_timeout}s "
                        f"(ran for {elapsed:.1f}s)"
                    ),
                )

                # Clean up
                if workflow.id in self.active_workflows:
                    del self.active_workflows[workflow.id]
                if workflow.id in self.workflow_start_times:
                    del self.workflow_start_times[workflow.id]

                raise WorkflowTimeoutError(
                    f"Workflow exceeded maximum duration of {max_timeout}s (ran for {elapsed:.1f}s)"
                ) from None
        else:
            # No hard timeout configured, execute normally
            return await self._execute_workflow_internal(workflow, context)

    async def _execute_workflow_internal(
        self, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> Workflow:
        """
        Internal workflow execution logic (separated for timeout wrapping).

        Args:
            workflow: Workflow to execute
            context: Optional execution context

        Returns:
            Updated workflow with execution results
        """
        # Validate and initialize workflow
        self._validate_and_initialize_workflow(workflow, context)

        # Create workflow timeout task if configured
        timeout_task = None
        if self.config.timeout_config.workflow_timeout:
            timeout_task = asyncio.create_task(self._workflow_timeout_monitor(workflow.id))

        try:
            # Build execution phases
            phases = build_execution_phases(workflow)
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow.id,
                    "total_phases": len(phases),
                    "total_tasks": len(workflow.tasks),
                },
                description=f"Starting workflow {workflow.id} execution with {len(phases)} phases",
            )

            # Execute each phase
            for phase_num, task_ids in enumerate(phases, 1):
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "workflow_id": workflow.id,
                        "phase_number": phase_num,
                        "tasks_in_phase": len(task_ids),
                    },
                    description=f"Executing phase {phase_num}/{len(phases)} with {len(task_ids)} tasks",
                )

                # Apply phase timeout if configured
                phase_timeout = self.config.timeout_config.phase_timeout
                if phase_timeout:
                    try:
                        await asyncio.wait_for(
                            self._execute_phase(workflow, task_ids, context), timeout=phase_timeout
                        )
                    except asyncio.TimeoutError:
                        # Handle phase timeout
                        for task_id in task_ids:
                            if task_id in workflow.tasks:
                                task = workflow.tasks[task_id]
                                if task.status == TaskStatus.IN_PROGRESS:
                                    task.status = TaskStatus.FAILED
                                    task.error_message = "Phase timeout exceeded"
                else:
                    # Execute without phase timeout
                    await self._execute_phase(workflow, task_ids, context)

                # Check if we should continue
                if not self._should_continue_execution(workflow):
                    break

                # Update progress
                self._notify_progress(workflow.id, workflow)

            # Finalize workflow
            workflow.completed_at = datetime.now()
            workflow.status = self._determine_final_status(workflow)

            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow.id,
                    "status": workflow.status.value,
                    "total_tasks": len(workflow.tasks),
                    "execution_time_ms": (datetime.now() - workflow.created_at).total_seconds() * 1000,
                },
                description=f"Workflow {workflow.id} completed with status {workflow.status.value}",
            )

        except Exception as e:
            #  Error - add observability
            workflow.status = WorkflowStatus.FAILED
            workflow.completed_at = datetime.now()
            # Note: Workflow model doesn't have error_message field
            # Log error for debuggability since workflow doesn't store error_message
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "status": str(workflow.status),
                    "user_request": workflow.user_request[:100] if workflow.user_request else None,
                },
                description=f"Workflow {workflow.id} failed: {str(e)}",
            )

        finally:
            # Cancel timeout monitor if still running
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()

            # Clean up
            if workflow.id in self.active_workflows:
                del self.active_workflows[workflow.id]
            if workflow.id in self.workflow_start_times:
                del self.workflow_start_times[workflow.id]

        return workflow

    async def execute_workflow_streaming(
        self,
        workflow: Workflow,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Workflow:
        """
        Execute workflow with streaming progress updates.

        This method executes the workflow while calling the progress_callback
        with real-time updates about task execution.

        Args:
            workflow: Workflow to execute
            context: Optional execution context
            progress_callback: Callback function for progress updates
                              Called with (workflow_id, workflow, task_update)

        Returns:
            Updated workflow with execution results
        """
        # Validate and initialize workflow
        self._validate_and_initialize_workflow(workflow, context)

        try:
            # Build execution phases
            phases = build_execution_phases(workflow)

            # Notify workflow started
            if progress_callback:
                progress_callback(
                    workflow.id,
                    workflow,
                    {
                        "type": "workflow_started",
                        "workflow_id": workflow.id,
                        "total_phases": len(phases),
                        "total_tasks": len(workflow.tasks),
                    },
                )

            # Execute each phase
            for phase_num, task_ids in enumerate(phases, 1):
                # Notify phase started
                if progress_callback:
                    progress_callback(
                        workflow.id,
                        workflow,
                        {
                            "type": "phase_started",
                            "phase_num": phase_num,
                            "total_phases": len(phases),
                            "task_ids": task_ids,
                        },
                    )

                # Execute tasks in parallel within this phase with streaming
                await self._execute_phase_streaming(workflow, task_ids, context, progress_callback)

                # Check if we should continue
                if not self._should_continue_execution(workflow):
                    break

            # Finalize workflow
            workflow.completed_at = datetime.now()
            workflow.status = self._determine_final_status(workflow)

            # Notify workflow completed
            if progress_callback:
                progress_callback(
                    workflow.id,
                    workflow,
                    {
                        "type": "workflow_completed",
                        "workflow_id": workflow.id,
                        "status": (
                            workflow.status.value
                            if hasattr(workflow.status, "value")
                            else str(workflow.status)
                        ),
                        "total_time": (workflow.completed_at - workflow.started_at).total_seconds(),
                    },
                )

        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.completed_at = datetime.now()
            # Note: Workflow model doesn't have error_message field
            # Log error for debuggability since workflow doesn't store error_message
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "workflow_id": workflow.id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "status": str(workflow.status),
                    "user_request": workflow.user_request[:100] if workflow.user_request else None,
                    "streaming": True,
                },
                description=f"Workflow {workflow.id} failed during streaming: {str(e)}",
            )

            # Notify workflow failed
            if progress_callback:
                progress_callback(
                    workflow.id,
                    workflow,
                    {"type": "workflow_failed", "workflow_id": workflow.id, "error": str(e)},
                )

        finally:
            # Clean up
            if workflow.id in self.active_workflows:
                del self.active_workflows[workflow.id]

        return workflow

    async def _execute_phase_streaming(
        self,
        workflow: Workflow,
        task_ids: List[str],
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ):
        """
        Execute all tasks in a phase concurrently with streaming updates.

        Args:
            workflow: Workflow being executed
            task_ids: Task IDs in this phase
            context: Optional execution context
            progress_callback: Optional callback for progress updates
        """
        # Create task list regardless of execution mode
        tasks_to_execute = []
        for task_id in task_ids:
            if task_id in workflow.tasks:
                tasks_to_execute.append(workflow.tasks[task_id])

        if not tasks_to_execute:
            return

        # Execute based on configuration
        if not self.config.enable_parallel_execution:
            # Sequential execution
            for task in tasks_to_execute:
                await self._execute_task_streaming(task, workflow, context, progress_callback)
                # Check if we should continue after each task
                if not self._should_continue_execution(workflow):
                    break
        else:
            # Parallel execution with batching
            # Create coroutines for all tasks
            task_coroutines = [
                self._execute_task_streaming(task, workflow, context, progress_callback)
                for task in tasks_to_execute
            ]

            max_parallel = self.config.max_parallel_tasks

            if max_parallel and max_parallel < len(task_coroutines):
                # Execute in batches respecting max_parallel_tasks
                for i in range(0, len(task_coroutines), max_parallel):
                    batch = task_coroutines[i:i + max_parallel]
                    await asyncio.gather(*batch, return_exceptions=True)
                    # Check if we should continue after each batch
                    if not self._should_continue_execution(workflow):
                        break
            else:
                # Execute all tasks concurrently
                await asyncio.gather(*task_coroutines, return_exceptions=True)

    async def _execute_task_streaming(
        self,
        task: SubTask,
        workflow: Workflow,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> TaskResult:
        """
        Execute individual task with streaming progress updates.

        Args:
            task: Task to execute
            workflow: Parent workflow
            context: Optional execution context
            progress_callback: Optional callback for progress updates

        Returns:
            Task execution result
        """
        task.status = TaskStatus.IN_PROGRESS
        task.start_time = datetime.now()

        # Notify task started
        if progress_callback:
            agent = self._select_agent_for_task(task)
            progress_callback(
                workflow.id,
                workflow,
                {
                    "type": "task_started",
                    "task_id": task.id,
                    "description": task.description,
                    "agent_id": agent.id if agent else None,
                    "dependencies": task.depends_on,
                },
            )

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
                **(context or {}),
            }

            # Select and execute with appropriate agent
            agent = self._select_agent_for_task(task)
            if not agent:
                raise ValueError(f"No suitable agent found for task {task.id}")

            # Notify task execution starting
            if progress_callback:
                progress_callback(
                    workflow.id,
                    workflow,
                    {
                        "type": "task_progress",
                        "task_id": task.id,
                        "progress": f"Executing with agent {agent.id}",
                    },
                )

            # Execute task
            result = await self._execute_task_with_agent(task, agent, execution_context)

            # Store result
            task.status = TaskStatus.DONE
            task.end_time = datetime.now()
            task.result = result.outputs if result else {}

            # Store in results cache
            if result:
                self.task_results[task.id] = result

            # Emit streaming event for task completion
            streaming.stream(
                "progress",
                f"Completed task: {task.description}",
                stage="task_complete",
                task_id=task.id,
                task_type=task.task_type if hasattr(task, 'task_type') else None
            )

            # Notify task completed
            if progress_callback:
                progress_callback(
                    workflow.id,
                    workflow,
                    {
                        "type": "task_completed",
                        "task_id": task.id,
                        "description": task.description,
                        "status": "completed",
                        "outputs": task.outputs,
                        "execution_time": (task.end_time - task.start_time).total_seconds(),
                    },
                )

            return result

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.end_time = datetime.now()

            # Notify task failed
            if progress_callback:
                progress_callback(
                    workflow.id,
                    workflow,
                    {
                        "type": "task_completed",
                        "task_id": task.id,
                        "description": task.description,
                        "status": "failed",
                        "error": str(e),
                    },
                )

            # Create error result
            error_result = TaskResult(
                task_id=task.id, status=TaskStatus.FAILED, outputs={}, error_message=str(e)
            )
            self.task_results[task.id] = error_result
            return error_result

    def _calculate_task_timeout(self, task: SubTask) -> Optional[float]:
        """Calculate timeout for a task based on complexity"""
        if not self.config.timeout_config.task_timeout:
            return None

        base_timeout = self.config.timeout_config.task_timeout

        if self.config.timeout_config.enable_adaptive_timeout:
            # Adjust based on complexity
            multiplier = 1.0 + (task.estimated_complexity - 5) * 0.1
            multiplier = max(0.5, min(multiplier, self.config.timeout_config.timeout_multiplier))
            return base_timeout * multiplier

        return base_timeout

    def _update_agent_history(
        self, agent_id: str, task: SubTask, status: str, execution_time: float
    ) -> None:
        """Update agent performance history"""
        self.agent_task_history[agent_id].append(
            {
                "task_id": task.id,
                "capabilities": task.required_capabilities,
                "complexity": task.estimated_complexity,
                "status": status,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Keep only recent history (last 100 tasks)
        if len(self.agent_task_history[agent_id]) > 100:
            self.agent_task_history[agent_id] = self.agent_task_history[agent_id][-100:]

    async def _execute_phase(
        self, workflow: Workflow, task_ids: List[str], context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Execute all tasks in a phase concurrently.

        Args:
            workflow: Workflow being executed
            task_ids: Task IDs in this phase
            context: Optional execution context
        """
        # Check if parallel execution is enabled
        if not self.config.enable_parallel_execution:
            # Execute tasks sequentially
            for task_id in task_ids:
                if task_id in workflow.tasks:
                    task = workflow.tasks[task_id]
                    await self._execute_task(task, workflow, context)
                    # Check if we should continue after each task
                    if not self._should_continue_execution(workflow):
                        break
            return

        # Create coroutines for all tasks in this phase
        task_coroutines = []
        for task_id in task_ids:
            if task_id in workflow.tasks:
                coroutine = self._execute_task(workflow.tasks[task_id], workflow, context)
                task_coroutines.append(coroutine)

        # Execute tasks with max_parallel_tasks limit
        if task_coroutines:
            max_parallel = self.config.max_parallel_tasks
            if max_parallel and max_parallel < len(task_coroutines):
                # Execute in batches respecting max_parallel_tasks
                for i in range(0, len(task_coroutines), max_parallel):
                    batch = task_coroutines[i:i + max_parallel]
                    await asyncio.gather(*batch, return_exceptions=True)
                    # Check if we should continue after each batch
                    if not self._should_continue_execution(workflow):
                        break
            else:
                # Execute all tasks concurrently
                await asyncio.gather(*task_coroutines, return_exceptions=True)

    async def _execute_task(
        self, task: SubTask, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        Execute individual task with enhanced error handling and retry logic.

        This method now uses the new separated models internally for cleaner logic
        while maintaining compatibility with the SubTask interface.

        Args:
            task: Task to execute
            workflow: Parent workflow
            context: Optional execution context

        Returns:
            Task execution result
        """
        # Import adapter at method level to avoid circular imports
        from .task_adapter import TaskAdapter

        # Validate inputs
        if not isinstance(task, SubTask):
            raise ValueError("Task must be a SubTask instance")
        if not isinstance(workflow, Workflow):
            raise ValueError("Workflow must be a Workflow instance")
        if context is not None and not isinstance(context, dict):
            raise ValueError("Context must be a dictionary or None")

        # Convert SubTask to separated models for cleaner internal logic
        # Pass workflow context to calculate blocked_by field properly
        spec, state = TaskAdapter.from_subtask(task, workflow=workflow)

        # Mark task as starting (agent will be assigned later)
        state.status = TaskStatus.IN_PROGRESS
        state.start_time = datetime.now()

        # Apply state changes back to SubTask for compatibility
        task.status = state.status
        task.start_time = state.start_time

        # Event 7: COMMENTED OUT - too granular task start event
        # # Emit streaming event for task start
        # streaming.stream(
        #     "progress",
        #     f"Starting task: {task.description}",
        #     stage="task_start",
        #     task_id=task.id,
        #     task_type=task.task_type if hasattr(task, 'task_type') else None,
        #     required_capabilities=task.required_capabilities if hasattr(task, 'required_capabilities') else None
        # )

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
                "task_critical": task.estimated_complexity >= 7,  # High complexity = critical
                **(context or {}),
            }

            # Select agent using the specification for cleaner logic
            agent = self._select_agent_for_spec(spec, state)

            if not agent:
                raise ValueError(f"No suitable agent found for task {task.id}")

            # Update both state and SubTask
            state.assigned_agent_id = agent.agent_id
            task.assigned_agent_id = agent.agent_id

            # Calculate task timeout
            task_timeout = self._calculate_task_timeout(task)

            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_TASK_ASSIGNED,
                level=observability.EventLevel.INFO,
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "agent_id": agent.agent_id,
                    "task_complexity": task.estimated_complexity if hasattr(task, 'estimated_complexity') else None,
                    "estimated_duration_s": task_timeout,
                    "dependencies_completed": len(task.dependencies) if hasattr(task, 'dependencies') else 0,
                    "workflow_id": workflow.id if workflow else None,
                },
                description=(
                    f"Task '{task.name}' "
                    f"(complexity {task.estimated_complexity if hasattr(task, 'estimated_complexity') else 'N/A'}) "
                    f"assigned to agent '{agent.agent_id}'"
                ),
            )

            # Execute task with timeout
            try:
                if task_timeout:
                    result = await asyncio.wait_for(
                        self._execute_task_with_agent(task, agent, execution_context),
                        timeout=task_timeout,
                    )
                else:
                    result = await self._execute_task_with_agent(task, agent, execution_context)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Task {task.id} exceeded timeout of {task_timeout}s")

            # Create execution result using the new model for better structure
            execution_result = create_execution_result(
                task_id=spec.id,
                agent_id=agent.agent_id,
                start_time=state.start_time,
                end_time=datetime.now(),
                success=True,
                outputs=result.outputs if result else {},
                attempt_number=state.attempt_count + 1,  # Convert 0-based to 1-based
            )

            # Update SubTask with result information
            task = TaskAdapter.update_subtask_from_result(task, execution_result)

            # Track execution time
            execution_time = execution_result.execution_time
            self.task_execution_times[task.id] = execution_time

            # Update agent history
            self._update_agent_history(agent.agent_id, task, "success", execution_time)

            # Store in results cache
            if result:
                self.task_results[task.id] = result

            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_TASK_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "agent_id": task.assigned_agent_id,
                    "status": result.status.value if result else "unknown",
                    "duration_ms": execution_time * 1000 if execution_time else None,
                    "task_complexity": task.estimated_complexity if hasattr(task, 'estimated_complexity') else None,
                    "success": result.status.value == "completed" if result else False,
                    "workflow_id": workflow.id if workflow else None,
                },
                description=(
                    f"Task '{task.name}' completed in {execution_time:.2f}s "
                    f"by agent '{task.assigned_agent_id}'"
                ),
            )
            return result

        except Exception as e:
            # Handle error with configured strategy
            error_action = await self.error_handler.handle_task_error(task.id, e, execution_context)

            if error_action["action"] == "retry":
                # Wait and retry
                await asyncio.sleep(error_action["delay"])
                return await self._execute_task(task, workflow, context)

            elif error_action["action"] == "retry_alternate":
                # Try with different agent
                # Mark current agent as failed for this task type
                if task.assigned_agent_id:
                    self._update_agent_history(task.assigned_agent_id, task, "failed", 0)

                # Exclude current agent and retry
                excluded_agents = [task.assigned_agent_id] if task.assigned_agent_id else []
                alt_agent = self._select_agent_for_task_excluding(task, excluded_agents)

                if alt_agent:
                    task.assigned_agent_id = alt_agent.agent_id
                    return await self._execute_task(task, workflow, context)

            elif error_action["action"] == "skip":
                # Skip non-critical task
                task.status = TaskStatus.DONE
                task.end_time = datetime.now()
                task.result = {"skipped": True, "reason": error_action["reason"]}

                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    outputs=task.result if isinstance(task.result, dict) else {},
                    error_message=f"Task skipped: {error_action['reason']}",
                )

            # Default: mark as failed
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "assigned_agent_id": task.assigned_agent_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "workflow_id": getattr(task, 'workflow_id', None),
                },
                description=f"Task '{task.name}' execution failed",
            )
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.end_time = datetime.now()

            # Update agent history
            if task.assigned_agent_id:
                self._update_agent_history(task.assigned_agent_id, task, "failed", 0)

            # Create error result
            error_result = TaskResult(
                task_id=task.id, status=TaskStatus.FAILED, outputs={}, error_message=str(e)
            )
            self.task_results[task.id] = error_result
            return error_result

    async def _collect_task_inputs(self, task: SubTask, workflow: Workflow) -> Dict[str, Any]:
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

    def _select_agent_for_spec(
        self, spec: TaskSpecification, state: TaskExecutionState
    ) -> Optional[Agent]:
        """
        Select best agent based on task specification.

        This is a cleaner version that works with the separated model.

        Args:
            spec: Task specification with requirements
            state: Current execution state

        Returns:
            Selected agent or None if no suitable agent found
        """
        # Direct routing implementation without creating temporary SubTask
        strategy = self.config.routing_strategy

        # Special case: custom routing function still needs SubTask for backward compatibility
        if strategy == TaskRoutingStrategy.CUSTOM and self.custom_routing_fn:
            from ...datatypes.workflow import SubTask

            temp_task = SubTask(
                id=spec.id,
                description=spec.description,
                required_capabilities=list(spec.required_capabilities),
                dependencies=list(spec.dependencies),
                estimated_complexity=spec.estimated_complexity,
                status=state.status,
                assigned_agent_id=state.assigned_agent_id,
            )
            return self.custom_routing_fn(temp_task, list(self.agent_registry.values()))

        # Handle no capability requirements - return any available agent
        if not spec.required_capabilities:
            return next(iter(self.agent_registry.values()), None)

        # Apply routing rules directly using spec
        if self.routing_rules:
            for rule in self.routing_rules:
                # Match pattern against description or capabilities
                pattern_match = rule.task_pattern.lower() in spec.description.lower()
                capability_match = rule.required_capabilities and all(
                    cap in spec.required_capabilities for cap in rule.required_capabilities
                )

                if pattern_match or capability_match:
                    for agent_id in rule.preferred_agents:
                        if agent_id in self.agent_registry:
                            return self.agent_registry[agent_id]

        # Main routing logic based on strategy
        best_agent = None

        if strategy == TaskRoutingStrategy.ROUND_ROBIN:
            # Simple round-robin without affinity check
            agents = list(self.agent_registry.values())
            if agents:
                if not hasattr(self, "_rr_index"):
                    self._rr_index = 0
                best_agent = agents[self._rr_index % len(agents)]
                self._rr_index += 1
                return best_agent

        # For all other strategies, find agents with required capabilities
        capable_agents = []
        for agent_id, agent in self.agent_registry.items():
            # Check if agent has any required capability - try both specialties and specialization
            agent_caps = (
                getattr(agent, "specialties", None) or getattr(agent, "specialization", None) or []
            )

            # Check if any required capability matches agent capabilities OR agent ID
            # This handles cases where the decomposer uses agent IDs as capabilities
            capability_match = any(cap in agent_caps for cap in spec.required_capabilities)
            id_match = agent_id in spec.required_capabilities

            if capability_match or id_match:
                capable_agents.append((agent_id, agent))

        if not capable_agents:
            # No capable agents found, return any available
            return next(iter(self.agent_registry.values()), None)

        # Apply strategy-specific selection from capable agents
        if strategy == TaskRoutingStrategy.LOAD_BALANCED:
            # Select agent with least recent tasks
            min_tasks = float("inf")
            for agent_id, agent in capable_agents:
                task_count = len(self.agent_task_history[agent_id])
                if task_count < min_tasks:
                    min_tasks = task_count
                    best_agent = agent

        elif strategy == TaskRoutingStrategy.SPECIALIZED:
            # Select agent with most matching capabilities
            max_matches = 0
            for agent_id, agent in capable_agents:
                agent_caps = (
                    getattr(agent, "specialties", None)
                    or getattr(agent, "specialization", None)
                    or []
                )
                matches = sum(1 for cap in spec.required_capabilities if cap in agent_caps)
                if matches > max_matches:
                    max_matches = matches
                    best_agent = agent

        else:  # Default: CAPABILITY_BASED or PRIORITY_BASED
            # Use affinity if enabled
            if self.config.enable_agent_affinity:
                best_score = -1
                for agent_id, agent in capable_agents:
                    if agent_id in self.agent_task_history:
                        history = self.agent_task_history[agent_id]
                        relevant = [
                            h
                            for h in history
                            if any(
                                cap in h.get("capabilities", [])
                                for cap in spec.required_capabilities
                            )
                        ]
                        if relevant:
                            success_count = sum(1 for h in relevant if h.get("status") == "success")
                            score = success_count / len(relevant) if relevant else 0
                            if score > best_score:
                                best_score = score
                                best_agent = agent

            # If no affinity match or affinity disabled, use first capable
            if not best_agent:
                best_agent = capable_agents[0][1]

        return best_agent

    def _select_agent_for_task(self, task: SubTask) -> Optional[Agent]:
        """
        Select best agent for task based on configured routing strategy.

        Args:
            task: Task to find agent for

        Returns:
            Selected agent or None if no suitable agent found
        """
        strategy = self.config.routing_strategy

        # Use custom routing function if available
        if strategy == TaskRoutingStrategy.CUSTOM and self.custom_routing_fn:
            return self.custom_routing_fn(task, list(self.agent_registry.values()))

        # Apply routing rules if configured
        if self.routing_rules:
            for rule in self.routing_rules:
                if self._matches_routing_rule(task, rule):
                    for agent_id in rule.preferred_agents:
                        if agent_id in self.agent_registry:
                            return self.agent_registry[agent_id]

        # Strategy-based routing
        if strategy == TaskRoutingStrategy.CAPABILITY_BASED:
            return self._route_by_capability(task)
        elif strategy == TaskRoutingStrategy.LOAD_BALANCED:
            return self._route_by_load_balance(task)
        elif strategy == TaskRoutingStrategy.PRIORITY_BASED:
            return self._route_by_priority(task)
        elif strategy == TaskRoutingStrategy.ROUND_ROBIN:
            return self._route_round_robin(task)
        elif strategy == TaskRoutingStrategy.SPECIALIZED:
            return self._route_to_specialized(task)

        # Fallback to capability-based routing
        return self._route_by_capability(task)

    def _route_by_capability(self, task: SubTask) -> Optional[Agent]:
        """Route based on agent capabilities with smart matching"""
        if not task.required_capabilities:
            # Use any available agent
            return next(iter(self.agent_registry.values()), None)

        # Find the best agent based on capability matching
        best_agent = None
        best_score = 0

        # Priority capabilities (more specific/rare capabilities get higher priority)
        priority_caps = {"linear", "github", "slack", "mcp"}  # Tool-specific capabilities

        for agent_id, agent in self.agent_registry.items():
            # Check agent affinity if enabled
            if self.config.enable_agent_affinity:
                affinity_score = self._calculate_agent_affinity(agent_id, task)
                if affinity_score > 0.7:  # High affinity threshold
                    return agent

            # Check if agent has required capabilities
            agent_caps = (
                getattr(agent, "specialties", None) or getattr(agent, "specialization", None) or []
            )

            # Calculate matching score - include agent ID as a capability
            matching_caps = [
                cap for cap in task.required_capabilities if cap in agent_caps or cap == agent_id
            ]
            if not matching_caps:
                continue  # Agent doesn't match any required capabilities

            # Calculate score: base score + bonus for priority capabilities
            score = len(matching_caps)  # Base score: number of matching capabilities

            # Add bonus for priority capabilities (like "linear" for Linear issues)
            priority_bonus = sum(2 for cap in matching_caps if cap in priority_caps)
            score += priority_bonus

            # Prefer agents that match more capabilities
            if score > best_score:
                best_score = score
                best_agent = agent

        if best_agent:
            return best_agent

        # No matching agent found - try to find the most general agent
        # Look for agents with "general" or broad capabilities
        for agent_id, agent in self.agent_registry.items():
            agent_caps = (
                getattr(agent, "specialties", None) or getattr(agent, "specialization", None) or []
            )
            if "general" in agent_caps or len(agent_caps) == 0:
                return agent

        # Last resort fallback - return first available agent with logging
        fallback_agent = next(iter(self.agent_registry.values()), None)
        if fallback_agent:
            print(
                f"⚠️  WARNING: No suitable agent found for capabilities {task.required_capabilities}"
            )
            print(f"   Falling back to: {fallback_agent.name} (id: {fallback_agent.agent_id})")
        return fallback_agent

    def _route_by_load_balance(self, task: SubTask) -> Optional[Agent]:
        """Route to least loaded agent"""
        if not self.agent_registry:
            return None

        # Calculate load for each agent
        agent_loads = {}
        for agent_id in self.agent_registry:
            # Count active tasks for this agent
            active_count = sum(
                1
                for wf in self.active_workflows.values()
                for t in wf.tasks.values()
                if t.assigned_agent_id == agent_id and t.status == TaskStatus.IN_PROGRESS
            )
            agent_loads[agent_id] = active_count

        # Select agent with lowest load
        min_load_agent_id = min(agent_loads, key=agent_loads.get)
        return self.agent_registry.get(min_load_agent_id)

    def _route_round_robin(self, task: SubTask) -> Optional[Agent]:
        """Simple round-robin routing"""
        agents = list(self.agent_registry.values())
        if not agents:
            return None

        agent = agents[self._rr_index % len(agents)]
        self._rr_index += 1
        return agent

    def _route_by_priority(self, task: SubTask) -> Optional[Agent]:
        """Route based on task priority (using complexity as proxy)"""
        # For high complexity tasks, use best performing agents
        if task.estimated_complexity >= 8:
            return self._get_best_performing_agent(task)

        # For lower complexity, use standard routing
        return self._route_by_capability(task)

    def _route_to_specialized(self, task: SubTask) -> Optional[Agent]:
        """Route to most specialized agent for the task"""
        # This would require agent metadata about specializations
        # For now, falls back to capability-based routing
        return self._route_by_capability(task)

    def _calculate_agent_affinity(self, agent_id: str, task: SubTask) -> float:
        """Calculate affinity score based on past performance"""
        history = self.agent_task_history[agent_id]
        relevant_tasks = [
            h
            for h in history
            if any(cap in h.get("capabilities", []) for cap in task.required_capabilities)
        ]

        if not relevant_tasks:
            return 0.0

        # Calculate success rate
        successful = sum(1 for t in relevant_tasks if t.get("status") == "success")
        success_rate = successful / len(relevant_tasks)

        # Factor in recency (more recent = higher weight)
        recency_weight = 0.5 + 0.5 * (len(relevant_tasks) / max(len(history), 1))

        return success_rate * recency_weight

    def _get_best_performing_agent(self, task: SubTask) -> Optional[Agent]:
        """Get agent with best performance for given task"""
        best_agent = None
        best_score = -1

        for agent_id, agent in self.agent_registry.items():
            score = self._calculate_agent_affinity(agent_id, task)
            if score > best_score:
                best_score = score
                best_agent = agent

        return best_agent or next(iter(self.agent_registry.values()), None)

    def _matches_routing_rule(self, task: SubTask, rule: AgentRoutingRule) -> bool:
        """Check if task matches routing rule"""
        # Check task description
        if rule.task_pattern.lower() in task.description.lower():
            return True

        # Check capabilities
        if rule.required_capabilities:
            if all(cap in task.required_capabilities for cap in rule.required_capabilities):
                return True

        return False

    async def _execute_task_with_agent(
        self, task: SubTask, agent: Agent, context: Dict[str, Any]
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
        # # DEBUG: Log all task executions to find the Linear task

        # Create task prompt
        task_prompt = self._create_task_prompt(task, context)

        try:
            # Execute with agent
            response = await agent.process_message(
                task_prompt,
                user_id=context.get("user_id", 0),
                session_id=context.get("session_id"),
                request_id=context.get("request_id"),
            )

            # Extract content from muxi.runtimeResponse
            response_content = response.content if hasattr(response, "content") else str(response)

            # Extract artifacts if present
            artifacts = []
            if hasattr(response, "artifacts") and response.artifacts:
                artifacts = response.artifacts

            # Parse response into structured outputs
            outputs = self._parse_task_response(response_content, task)

            # Add artifacts to outputs if present
            if artifacts:
                outputs["artifacts"] = {
                    "result": artifacts,
                    "status": "success",
                    "metrics": {"artifact_count": len(artifacts)}
                }

            return TaskResult(
                task_id=task.id,
                agent_id=agent.agent_id,
                status=TaskStatus.DONE,
                outputs=outputs,
                raw_response=response_content,
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "task_id": task.id,
                    "task_name": task.name,
                    "agent_id": agent.agent_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Failed to execute task '{task.name}' with agent '{agent.agent_id}'",
            )
            return TaskResult(
                task_id=task.id,
                agent_id=agent.agent_id,
                status=TaskStatus.FAILED,
                outputs={},
                error_message=str(e),
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
            "",
            "Task Details:",
            f"- Required Capabilities: {', '.join(task.required_capabilities)}",
            f"- Estimated Complexity: {task.estimated_complexity}/10",
        ]

        # Add inputs if available
        if context.get("inputs"):
            prompt_parts.extend(["", "Available Inputs:", json.dumps(context["inputs"], indent=2)])

        # Add topic/subject context if the task description is generic
        if "write" in task.description.lower() or "create" in task.description.lower():
            # Try to extract topic from original request or previous task outputs
            topic = None
            if context.get("inputs"):
                # Look for research findings or topic in inputs
                for input_key, input_val in context.get("inputs", {}).items():
                    if isinstance(input_val, dict) and "topic" in input_val:
                        topic = input_val["topic"]
                        break
                    elif isinstance(input_val, str) and len(input_val) > 50:
                        # Use first substantial input as context
                        topic = input_val[:200] + "..."
                        break

            if topic:
                prompt_parts.extend(["", f"Context/Topic: {topic}"])

        prompt_parts.extend(
            [
                "",
                "Please complete THIS SPECIFIC TASK ONLY. Do not attempt to complete other parts of the workflow.",
                "Focus on delivering exactly what's described in the task above.",
                "Your output will be used by other agents to complete the overall workflow.",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_task_response(self, response: str, task: SubTask) -> Dict[str, Any]:
        """
        Parse agent response into structured outputs.

        Args:
            response: Raw agent response
            task: Task that was executed

        Returns:
            Structured outputs dictionary where each value is a TaskOutput
        """
        from ...datatypes.type_definitions import TaskOutput

        # Create main content output
        main_output: TaskOutput = {
            "result": response,
            "status": "success",
            "metrics": {"response_length": len(response)},
            "warnings": [],
            "artifacts": [],
        }

        outputs = {
            "main": main_output,
            "task_id": {"result": task.id, "status": "success"},
            "completed": {"result": True, "status": "success"},
        }

        # Add capability-specific outputs with dynamic metrics
        if "research" in task.required_capabilities:
            outputs["research_findings"] = {
                "result": response,
                "status": "success",
                "metrics": self._calculate_research_metrics(response),
            }
        elif "writing" in task.required_capabilities:
            outputs["written_content"] = {
                "result": response,
                "status": "success",
                "metrics": {"word_count": len(response.split())},
            }
        elif "analysis" in task.required_capabilities:
            outputs["analysis_results"] = {
                "result": response,
                "status": "success",
                "metrics": self._calculate_analysis_metrics(response),
            }

        return outputs

    def _calculate_research_metrics(self, response: str) -> Dict[str, Any]:
        """
        Calculate research-specific metrics based on response content.

        Args:
            response: The research response text

        Returns:
            Dictionary of research metrics
        """
        # Calculate research depth based on content characteristics
        metrics = {
            "word_count": len(response.split()),
            "paragraph_count": len(response.split("\n\n")),
            "research_depth": 1,  # Base depth
        }

        # Increase depth based on content indicators
        depth_indicators = {
            "source": 2,
            "citation": 2,
            "reference": 2,
            "study": 3,
            "analysis": 3,
            "finding": 2,
            "evidence": 3,
            "data": 2,
            "research": 2,
            "conclusion": 2,
        }

        response_lower = response.lower()
        for indicator, weight in depth_indicators.items():
            if indicator in response_lower:
                metrics["research_depth"] += weight

        # Cap research depth at 10
        metrics["research_depth"] = min(metrics["research_depth"], 10)

        # Add source count if URLs are present
        url_pattern = r"https?://[^\s]+"
        urls = re.findall(url_pattern, response)
        if urls:
            metrics["source_count"] = len(urls)

        return metrics

    def _calculate_analysis_metrics(self, response: str) -> Dict[str, Any]:
        """
        Calculate analysis-specific metrics based on response content.

        Args:
            response: The analysis response text

        Returns:
            Dictionary of analysis metrics
        """
        # Calculate analysis depth based on content structure
        metrics = {
            "word_count": len(response.split()),
            "analysis_depth": 1,  # Base depth
        }

        # Increase depth based on analytical indicators
        depth_indicators = {
            "compare": 2,
            "contrast": 2,
            "evaluate": 3,
            "assess": 3,
            "examine": 2,
            "investigate": 3,
            "conclusion": 2,
            "recommendation": 3,
            "implication": 3,
            "trend": 2,
            "pattern": 2,
            "correlation": 3,
        }

        response_lower = response.lower()
        for indicator, weight in depth_indicators.items():
            if indicator in response_lower:
                metrics["analysis_depth"] += weight

        # Additional depth for structured analysis
        if any(marker in response for marker in ["1.", "2.", "•", "-", "*"]):
            metrics["analysis_depth"] += 2

        # Cap analysis depth at 10
        metrics["analysis_depth"] = min(metrics["analysis_depth"], 10)

        # Count analytical sections
        section_markers = ["however", "furthermore", "therefore", "in conclusion", "additionally"]
        section_count = sum(1 for marker in section_markers if marker in response_lower)
        if section_count > 0:
            metrics["section_count"] = section_count

        return metrics

    def _should_continue_execution(self, workflow: Workflow) -> bool:
        """
        Determine if workflow execution should continue based on configuration.

        Args:
            workflow: Workflow to check

        Returns:
            True if execution should continue
        """
        # Check if workflow has been cancelled
        if workflow.status == WorkflowStatus.CANCELLED:
            return False

        # Check workflow timeout
        if workflow.id in self.workflow_start_times:
            elapsed = (datetime.now() - self.workflow_start_times[workflow.id]).total_seconds()
            if (
                self.config.timeout_config.workflow_timeout
                and elapsed > self.config.timeout_config.workflow_timeout
            ):
                workflow.status = WorkflowStatus.FAILED
                # Note: Workflow model doesn't have error_message field
                # Log timeout for debuggability since workflow doesn't store error_message
                observability.observe(
                    event_type=observability.ErrorEvents.CONNECTION_TIMEOUT,
                    level=observability.EventLevel.WARNING,
                    data={
                        "workflow_id": workflow.id,
                        "timeout": self.config.timeout_config.workflow_timeout,
                        "elapsed": elapsed,
                        "status": str(workflow.status),
                    },
                    description=(
                        f"Workflow {workflow.id} exceeded timeout of "
                        f"{self.config.timeout_config.workflow_timeout}s"
                    ),
                )
                return False

        # Check failure strategy
        failed_tasks = [
            task for task in workflow.tasks.values() if task.status == TaskStatus.FAILED
        ]

        if not failed_tasks:
            return True

        # Check if we should continue with partial results
        if self.config.enable_partial_results:
            # Continue if we have any successful tasks
            successful_tasks = [
                task for task in workflow.tasks.values() if task.status == TaskStatus.DONE
            ]
            return len(successful_tasks) > 0

        # Check if failed tasks are critical
        critical_failures = [
            task
            for task in failed_tasks
            if task.estimated_complexity >= 7  # High complexity = critical
        ]

        # Continue only if no critical failures
        return len(critical_failures) == 0

    def _determine_final_status(self, workflow: Workflow) -> WorkflowStatus:
        """
        Determine final workflow status based on task results.

        Args:
            workflow: Workflow to analyze

        Returns:
            Final workflow status
        """
        # Check if workflow was cancelled
        if workflow.status == WorkflowStatus.CANCELLED:
            return WorkflowStatus.CANCELLED

        task_statuses = [task.status for task in workflow.tasks.values()]

        # Handle both enum objects and string values due to use_enum_values=True
        # Include both DONE and COMPLETED as success states
        success_values = {
            TaskStatus.DONE,
            TaskStatus.DONE.value,
            TaskStatus.COMPLETED,
            TaskStatus.COMPLETED.value,
        }
        failed_values = {TaskStatus.FAILED, TaskStatus.FAILED.value}

        if all(status in success_values for status in task_statuses):
            return WorkflowStatus.COMPLETED
        elif any(status in failed_values for status in task_statuses):
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
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "workflow_id": workflow_id,
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "operation": "completion_callback",
                    },
                    description="Workflow completion callback failed",
                )

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
            cancelled_tasks = []
            for task in workflow.tasks.values():
                if task.status == TaskStatus.IN_PROGRESS:
                    task.status = TaskStatus.CANCELLED
                    task.end_time = datetime.now()
                    cancelled_tasks.append(task.id)

            # Emit workflow cancelled event
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_WORKFLOW_CANCELLED,
                level=observability.EventLevel.INFO,
                data={
                    "workflow_id": workflow_id,
                    "cancelled_tasks": cancelled_tasks,
                    "total_tasks": len(workflow.tasks),
                },
                description=f"Workflow {workflow_id} cancelled with {len(cancelled_tasks)} in-progress tasks",
            )

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
        completed_tasks = sum(
            1 for task in workflow.tasks.values() if task.status == TaskStatus.DONE
        )
        failed_tasks = sum(
            1 for task in workflow.tasks.values() if task.status == TaskStatus.FAILED
        )
        in_progress_tasks = sum(
            1 for task in workflow.tasks.values() if task.status == TaskStatus.IN_PROGRESS
        )

        return {
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "in_progress_tasks": in_progress_tasks,
            "progress_percentage": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
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
        completed_tasks = sum(
            1 for task in workflow.tasks.values() if task.status == TaskStatus.DONE
        )
        failed_tasks = sum(
            1 for task in workflow.tasks.values() if task.status == TaskStatus.FAILED
        )

        progress_info = {
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "progress_percentage": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "last_updated": datetime.now().isoformat(),
        }

        self.workflow_progress[workflow_id] = progress_info

        observability.observe(
            event_type=observability.ConversationEvents.WORKFLOW_EXECUTION_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "workflow_id": workflow_id,
                "completed_tasks": completed_tasks,
                "total_tasks": total_tasks,
                "progress_percentage": progress_info['progress_percentage'],
            },
            description=(
                f"Workflow {workflow_id} progress: {completed_tasks}/{total_tasks} tasks "
                f"({progress_info['progress_percentage']:.1f}%)"
            ),
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

    def cleanup_completed_workflows(self, retention_hours: int = 24) -> int:
        """
        Clean up progress tracking and history for completed workflows.

        Removes workflow data older than the retention period to prevent
        unbounded memory growth. Keeps recent data for debugging and monitoring.

        Args:
            retention_hours: Hours to retain completed workflow data (default: 24)

        Returns:
            Number of workflows cleaned up
        """
        if retention_hours < 0:
            raise ValueError("Retention hours must be non-negative")

        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=retention_hours)
        workflows_cleaned = 0

        # Identify workflows to clean up from history
        workflows_to_clean = []
        for workflow_id, workflow in self.workflow_history.items():
            if workflow.completed_at and workflow.completed_at < cutoff_time:
                workflows_to_clean.append(workflow_id)

        # Clean up all associated data for old workflows
        for workflow_id in workflows_to_clean:
            # Remove from workflow history
            if workflow_id in self.workflow_history:
                workflow = self.workflow_history[workflow_id]
                del self.workflow_history[workflow_id]

                # Clean up task results for this workflow's tasks
                for task_id in workflow.tasks:
                    if task_id in self.task_results:
                        del self.task_results[task_id]
                    if task_id in self.task_execution_times:
                        del self.task_execution_times[task_id]

            # Clean up workflow tracking data
            if workflow_id in self.workflow_progress:
                del self.workflow_progress[workflow_id]
            if workflow_id in self.workflow_start_times:
                del self.workflow_start_times[workflow_id]

            workflows_cleaned += 1

        # Clean up old agent task history (keep last 1000 entries per agent)
        for agent_id in self.agent_task_history:
            history = self.agent_task_history[agent_id]
            if len(history) > 1000:
                # Keep only the most recent 1000 entries
                self.agent_task_history[agent_id] = history[-1000:]

        return workflows_cleaned

    def _select_agent_for_task_excluding(
        self, task: SubTask, excluded_agents: List[str]
    ) -> Optional[Agent]:
        """Select agent excluding specific agents"""
        available_agents = {
            aid: agent for aid, agent in self.agent_registry.items() if aid not in excluded_agents
        }

        if not available_agents:
            return None

        # Create temporary registry and use normal selection
        original_registry = self.agent_registry
        self.agent_registry = available_agents

        try:
            return self._select_agent_for_task(task)
        finally:
            self.agent_registry = original_registry

    def set_custom_routing_function(self, fn: Callable[[SubTask, List[Agent]], Agent]) -> None:
        """Set custom routing function"""
        self.custom_routing_fn = fn

    def add_routing_rule(self, rule: AgentRoutingRule) -> None:
        """Add agent routing rule"""
        self.routing_rules.append(rule)
        # Sort by weight
        self.routing_rules.sort(key=lambda r: r.weight, reverse=True)

    def get_workflow_metrics(self, workflow_id: str) -> Dict[str, Any]:
        """Get detailed metrics for a workflow"""
        if workflow_id not in self.active_workflows and workflow_id not in self.workflow_history:
            return {"error": "Workflow not found"}

        workflow = self.active_workflows.get(workflow_id) or self.workflow_history.get(workflow_id)

        # Calculate metrics
        total_tasks = len(workflow.tasks)
        completed_tasks = sum(1 for t in workflow.tasks.values() if t.status == TaskStatus.DONE)
        failed_tasks = sum(1 for t in workflow.tasks.values() if t.status == TaskStatus.FAILED)

        # Task execution times
        task_times = [
            self.task_execution_times.get(tid, 0)
            for tid in workflow.tasks.keys()
            if tid in self.task_execution_times
        ]

        metrics = {
            "workflow_id": workflow_id,
            "status": (
                workflow.status.value if hasattr(workflow.status, "value") else str(workflow.status)
            ),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "average_task_time": sum(task_times) / len(task_times) if task_times else 0,
            "total_execution_time": (
                (workflow.completed_at - workflow.started_at).total_seconds()
                if workflow.completed_at and workflow.started_at
                else 0
            ),
            "error_summary": self._get_workflow_error_summary(workflow),
            "agent_utilization": self._get_agent_utilization(workflow),
        }

        return metrics

    def _get_workflow_error_summary(self, workflow: Workflow) -> Dict[str, Any]:
        """Get error summary for workflow"""
        errors = []
        for task in workflow.tasks.values():
            if task.error_message:
                errors.append(
                    {
                        "task_id": task.id,
                        "error": task.error_message,
                        "task_description": task.description,
                    }
                )

        return {"total_errors": len(errors), "errors": errors}

    def _get_agent_utilization(self, workflow: Workflow) -> Dict[str, Any]:
        """Get agent utilization for workflow"""
        agent_tasks = {}

        for task in workflow.tasks.values():
            if task.assigned_agent_id:
                if task.assigned_agent_id not in agent_tasks:
                    agent_tasks[task.assigned_agent_id] = {"total": 0, "completed": 0, "failed": 0}

                agent_tasks[task.assigned_agent_id]["total"] += 1

                if task.status == TaskStatus.DONE:
                    agent_tasks[task.assigned_agent_id]["completed"] += 1
                elif task.status == TaskStatus.FAILED:
                    agent_tasks[task.assigned_agent_id]["failed"] += 1

        return agent_tasks

    # ===================================================================
    # VALIDATION METHODS FOR TYPE SAFETY
    # ===================================================================

    def _validate_workflow(self, workflow: Workflow) -> None:
        """
        Validate workflow object integrity before execution.

        Args:
            workflow: Workflow to validate

        Raises:
            ValueError: If workflow is invalid
        """
        if not isinstance(workflow, Workflow):
            raise ValueError("Workflow must be a Workflow instance")

        if not workflow.id:
            raise ValueError("Workflow must have an ID")

        if not workflow.tasks:
            raise ValueError("Workflow must have at least one task")

        # Validate all tasks
        task_ids = set(workflow.tasks.keys())
        for task_id, task in workflow.tasks.items():
            if task_id != task.id:
                raise ValueError(f"Task ID mismatch: {task_id} != {task.id}")

            # Validate dependencies exist
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise ValueError(f"Task {task.id} has invalid dependency: {dep_id}")

            # Validate required capabilities
            if not task.required_capabilities:
                raise ValueError(f"Task {task.id} must have required capabilities")

    def _validate_task_result(self, result: TaskResult, task: SubTask) -> None:
        """
        Validate task execution result.

        Args:
            result: Task execution result
            task: Original task

        Raises:
            ValueError: If result is invalid
        """
        if not isinstance(result, TaskResult):
            raise ValueError("Result must be a TaskResult instance")

        if result.task_id != task.id:
            raise ValueError(f"Task ID mismatch in result: {result.task_id} != {task.id}")

        if result.status == TaskStatus.FAILED and not result.error_message:
            raise ValueError("Failed task must have an error message")

        # Allow None execution_time for completed tasks to handle quick completions or timing issues
        # Log a warning instead of raising an error
        if result.status == TaskStatus.DONE and result.execution_time is None:
            import warnings

            warnings.warn(
                f"Task {result.task_id} completed without execution_time. "
                "This may indicate a very quick completion or timing measurement issue.",
                RuntimeWarning,
            )

    def _validate_context(self, context: Optional[Dict[str, Any]]) -> None:
        """
        Validate execution context.

        Args:
            context: Execution context

        Raises:
            ValueError: If context is invalid
        """
        if context is not None and not isinstance(context, dict):
            raise ValueError("Context must be a dictionary if provided")
