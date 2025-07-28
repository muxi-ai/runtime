import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import json
import time

from ...datatypes.workflow import (
    Workflow,
    SubTask,
    TaskStatus,
    WorkflowStatus,
    TaskResult,
    build_execution_phases,
)
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

        # Enhanced tracking
        self.agent_task_history: Dict[str, List[Dict[str, Any]]] = {}  # Track agent performance
        self.workflow_start_times: Dict[str, datetime] = {}
        self.task_execution_times: Dict[str, float] = {}  # Track task execution times

        # Custom routing function
        self.custom_routing_fn: Optional[Callable] = None
        self.routing_rules: List[AgentRoutingRule] = []

        # Progress tracking callbacks
        self.progress_callbacks: List[Callable[[str, Workflow], None]] = []

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
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()
        self.workflow_start_times[workflow.id] = workflow.started_at

        # Track this workflow
        self.active_workflows[workflow.id] = workflow

        # Create workflow timeout task if configured
        timeout_task = None
        if self.config.timeout_config.workflow_timeout:
            timeout_task = asyncio.create_task(self._workflow_timeout_monitor(workflow.id))

        try:
            # Build execution phases
            phases = build_execution_phases(workflow)
            #  Info - TODO: add observability

            # Execute each phase
            for phase_num, task_ids in enumerate(phases, 1):
                #  Info - TODO: add observability

                # Apply phase timeout if configured
                phase_timeout = self.config.timeout_config.phase_timeout
                if phase_timeout:
                    try:
                        await asyncio.wait_for(
                            self._execute_phase(workflow, task_ids, context),
                            timeout=phase_timeout
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

            #  Info - TODO: add observability

        except Exception as e:
            #  Error - TODO: add observability
            workflow.status = WorkflowStatus.FAILED
            workflow.error_message = str(e)
            workflow.completed_at = datetime.now()

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
        progress_callback: Optional[Callable] = None
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
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()

        # Track this workflow
        self.active_workflows[workflow.id] = workflow

        try:
            # Build execution phases
            phases = build_execution_phases(workflow)

            # Notify workflow started
            if progress_callback:
                progress_callback(workflow.id, workflow, {
                    "type": "workflow_started",
                    "workflow_id": workflow.id,
                    "total_phases": len(phases),
                    "total_tasks": len(workflow.tasks)
                })

            # Execute each phase
            for phase_num, task_ids in enumerate(phases, 1):
                # Notify phase started
                if progress_callback:
                    progress_callback(workflow.id, workflow, {
                        "type": "phase_started",
                        "phase_num": phase_num,
                        "total_phases": len(phases),
                        "task_ids": task_ids
                    })

                # Execute tasks in parallel within this phase with streaming
                await self._execute_phase_streaming(
                    workflow, task_ids, context, progress_callback
                )

                # Check if we should continue
                if not self._should_continue_execution(workflow):
                    break

            # Finalize workflow
            workflow.completed_at = datetime.now()
            workflow.status = self._determine_final_status(workflow)

            # Notify workflow completed
            if progress_callback:
                progress_callback(workflow.id, workflow, {
                    "type": "workflow_completed",
                    "workflow_id": workflow.id,
                    "status": workflow.status.value if hasattr(workflow.status, 'value') else str(workflow.status),
                    "total_time": (workflow.completed_at - workflow.started_at).total_seconds()
                })

        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.error_message = str(e)
            workflow.completed_at = datetime.now()

            # Notify workflow failed
            if progress_callback:
                progress_callback(workflow.id, workflow, {
                    "type": "workflow_failed",
                    "workflow_id": workflow.id,
                    "error": str(e)
                })

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
        progress_callback: Optional[Callable] = None
    ):
        """
        Execute all tasks in a phase concurrently with streaming updates.

        Args:
            workflow: Workflow being executed
            task_ids: Task IDs in this phase
            context: Optional execution context
            progress_callback: Optional callback for progress updates
        """
        # Create coroutines for all tasks in this phase
        task_coroutines = []
        for task_id in task_ids:
            if task_id in workflow.tasks:
                coroutine = self._execute_task_streaming(
                    workflow.tasks[task_id], workflow, context, progress_callback
                )
                task_coroutines.append(coroutine)

        # Execute all tasks concurrently
        if task_coroutines:
            await asyncio.gather(*task_coroutines, return_exceptions=True)

    async def _execute_task_streaming(
        self,
        task: SubTask,
        workflow: Workflow,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None
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
        task.started_at = datetime.now()

        # Notify task started
        if progress_callback:
            agent = self._select_agent_for_task(task)
            progress_callback(workflow.id, workflow, {
                "type": "task_started",
                "task_id": task.id,
                "description": task.description,
                "agent_id": agent.id if agent else None,
                "dependencies": task.depends_on
            })

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
                progress_callback(workflow.id, workflow, {
                    "type": "task_progress",
                    "task_id": task.id,
                    "progress": f"Executing with agent {agent.id}"
                })

            # Execute task
            result = await self._execute_task_with_agent(task, agent, execution_context)

            # Store result
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now()
            task.outputs = result.outputs if result else {}

            # Store in results cache
            if result:
                self.task_results[task.id] = result

            # Notify task completed
            if progress_callback:
                progress_callback(workflow.id, workflow, {
                    "type": "task_completed",
                    "task_id": task.id,
                    "description": task.description,
                    "status": "completed",
                    "outputs": task.outputs,
                    "execution_time": (task.completed_at - task.started_at).total_seconds()
                })

            return result

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now()

            # Notify task failed
            if progress_callback:
                progress_callback(workflow.id, workflow, {
                    "type": "task_completed",
                    "task_id": task.id,
                    "description": task.description,
                    "status": "failed",
                    "error": str(e)
                })

            # Create error result
            error_result = TaskResult(
                task_id=task.id, status=TaskStatus.FAILED, outputs={}, error_message=str(e)
            )
            self.task_results[task.id] = error_result
            return error_result

    async def _execute_phase(
        self, workflow: Workflow, task_ids: List[str], context: Optional[Dict[str, Any]] = None
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
        self, task: SubTask, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> TaskResult:
        """
        Execute individual task with enhanced error handling and retry logic.

        Args:
            task: Task to execute
            workflow: Parent workflow
            context: Optional execution context

        Returns:
            Task execution result
        """
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()
        start_time = time.time()

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

            # Select agent
            agent = self._select_agent_for_task(task)
            if not agent:
                raise ValueError(f"No suitable agent found for task {task.id}")

            task.assigned_agent_id = agent.agent_id

            #  Info - TODO: add observability

            # Calculate task timeout
            task_timeout = self._calculate_task_timeout(task)

            # Execute task with timeout
            try:
                if task_timeout:
                    result = await asyncio.wait_for(
                        self._execute_task_with_agent(task, agent, execution_context),
                        timeout=task_timeout
                    )
                else:
                    result = await self._execute_task_with_agent(task, agent, execution_context)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Task {task.id} exceeded timeout of {task_timeout}s")

            # Store result
            task.status = TaskStatus.DONE
            task.completed_at = datetime.now()
            task.outputs = result.outputs if result else {}

            # Track execution time
            execution_time = time.time() - start_time
            self.task_execution_times[task.id] = execution_time

            # Update agent history
            self._update_agent_history(agent.agent_id, task, "success", execution_time)

            # Store in results cache
            if result:
                self.task_results[task.id] = result

            #  Info - TODO: add observability
            return result

        except Exception as e:
            # Handle error with configured strategy
            error_action = await self.error_handler.handle_task_error(
                task.id, e, execution_context
            )

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
                task.completed_at = datetime.now()
                task.outputs = {"skipped": True, "reason": error_action["reason"]}

                return TaskResult(
                    task_id=task.id,
                    status=TaskStatus.DONE,
                    outputs=task.outputs,
                    error_message=f"Task skipped: {error_action['reason']}"
                )

            # Default: mark as failed
            #  Error - TODO: add observability
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now()

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
        """Route based on agent capabilities"""
        if not task.required_capabilities:
            # Use any available agent
            return next(iter(self.agent_registry.values()), None)

        # Try to find agent with matching capability
        for capability in task.required_capabilities:
            # Look for agents with matching specialization
            for agent_id, agent in self.agent_registry.items():
                # Check agent affinity if enabled
                if self.config.enable_agent_affinity:
                    affinity_score = self._calculate_agent_affinity(agent_id, task)
                    if affinity_score > 0.7:  # High affinity threshold
                        return agent

                # Simple capability matching
                if capability in ["research", "writing", "analysis", "coding", "general"]:
                    return agent

        # Fallback to any available agent
        return next(iter(self.agent_registry.values()), None)

    def _route_by_load_balance(self, task: SubTask) -> Optional[Agent]:
        """Route to least loaded agent"""
        if not self.agent_registry:
            return None

        # Calculate load for each agent
        agent_loads = {}
        for agent_id in self.agent_registry:
            # Count active tasks for this agent
            active_count = sum(
                1 for wf in self.active_workflows.values()
                for t in wf.tasks.values()
                if t.assigned_agent_id == agent_id and t.status == TaskStatus.IN_PROGRESS
            )
            agent_loads[agent_id] = active_count

        # Select agent with lowest load
        min_load_agent_id = min(agent_loads, key=agent_loads.get)
        return self.agent_registry.get(min_load_agent_id)

    def _route_round_robin(self, task: SubTask) -> Optional[Agent]:
        """Simple round-robin routing"""
        if not hasattr(self, '_rr_index'):
            self._rr_index = 0

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
            return self._get_best_performing_agent(task.required_capabilities)

        # For lower complexity, use standard routing
        return self._route_by_capability(task)

    def _route_to_specialized(self, task: SubTask) -> Optional[Agent]:
        """Route to most specialized agent for the task"""
        # This would require agent metadata about specializations
        # For now, falls back to capability-based routing
        return self._route_by_capability(task)

    def _calculate_agent_affinity(self, agent_id: str, task: SubTask) -> float:
        """Calculate affinity score based on past performance"""
        if agent_id not in self.agent_task_history:
            return 0.0

        history = self.agent_task_history[agent_id]
        relevant_tasks = [
            h for h in history
            if any(cap in h.get('capabilities', []) for cap in task.required_capabilities)
        ]

        if not relevant_tasks:
            return 0.0

        # Calculate success rate
        successful = sum(1 for t in relevant_tasks if t.get('status') == 'success')
        success_rate = successful / len(relevant_tasks)

        # Factor in recency (more recent = higher weight)
        recency_weight = 0.5 + 0.5 * (len(relevant_tasks) / max(len(history), 1))

        return success_rate * recency_weight

    def _get_best_performing_agent(self, capabilities: List[str]) -> Optional[Agent]:
        """Get agent with best performance for given capabilities"""
        best_agent = None
        best_score = -1

        for agent_id, agent in self.agent_registry.items():
            score = self._calculate_agent_affinity(agent_id, capabilities)
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
        # Create task prompt
        task_prompt = self._create_task_prompt(task, context)

        try:
            # Execute with agent
            response = await agent.process_message(
                task_prompt,
                user_id=context.get("user_id", 0),
                conversation_id=context.get("conversation_id"),
                context=context,
            )

            # Parse response into structured outputs
            outputs = self._parse_task_response(response, task)

            return TaskResult(
                task_id=task.id,
                agent_id=agent.agent_id,
                status=TaskStatus.DONE,
                outputs=outputs,
                raw_response=response,
            )

        except Exception as e:
            #  Error - TODO: add observability
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
            f"Original Request: {context.get('user_request', 'N/A')}",
            "",
            "Task Details:",
            f"- Required Capabilities: {', '.join(task.required_capabilities)}",
            f"- Estimated Complexity: {task.estimated_complexity}/10",
        ]

        # Add inputs if available
        if context.get("inputs"):
            prompt_parts.extend(["", "Available Inputs:", json.dumps(context["inputs"], indent=2)])

        prompt_parts.extend(
            [
                "",
                "Please complete this task thoroughly and provide the results.",
                "Focus on delivering exactly what's needed for this specific task.",
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
            Structured outputs dictionary
        """
        # For now, simple output structure
        # In full implementation, would parse based on task type and expected outputs

        outputs = {"content": response, "task_id": task.id, "completed": True}

        # Add capability-specific parsing
        if "research" in task.required_capabilities:
            outputs["research_findings"] = response
        elif "writing" in task.required_capabilities:
            outputs["written_content"] = response
        elif "analysis" in task.required_capabilities:
            outputs["analysis_results"] = response

        return outputs

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
            if self.config.timeout_config.workflow_timeout and elapsed > self.config.timeout_config.workflow_timeout:
                workflow.status = WorkflowStatus.FAILED
                workflow.error_message = "Workflow timeout exceeded"
                return False

        # Check failure strategy
        failed_tasks = [
            task for task in workflow.tasks.values()
            if task.status == TaskStatus.FAILED
        ]

        if not failed_tasks:
            return True

        # Check if we should continue with partial results
        if self.config.enable_partial_results:
            # Continue if we have any successful tasks
            successful_tasks = [
                task for task in workflow.tasks.values()
                if task.status == TaskStatus.DONE
            ]
            return len(successful_tasks) > 0

        # Check if failed tasks are critical
        critical_failures = [
            task for task in failed_tasks
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
                #  Error - TODO: add observability
                _ = e  # remove this after implementing observability

    # Public methods for workflow management

    def add_progress_callback(self, callback: Callable[[str, Workflow], None]):
        """
        Add callback for workflow progress updates.

        Args:
            callback: Function to call with (workflow_id, workflow) on updates
        """
        self.progress_callbacks.append(callback)

    # Add property to track workflow history
    workflow_history: Dict[str, Workflow] = {}

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

            #  Info - TODO: add observability
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

        # #  Info - TODO: add observability
        #     f"Workflow {workflow_id} progress: {completed_tasks}/{total_tasks} tasks completed "
        #     f"({progress_info['progress_percentage']:.1f}%)"
        # )

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

    def _update_agent_history(self, agent_id: str, task: SubTask, status: str, execution_time: float):
        """Update agent performance history"""
        if agent_id not in self.agent_task_history:
            self.agent_task_history[agent_id] = []

        self.agent_task_history[agent_id].append({
            "task_id": task.id,
            "capabilities": task.required_capabilities,
            "complexity": task.estimated_complexity,
            "status": status,
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat()
        })

        # Keep only recent history (last 100 tasks)
        if len(self.agent_task_history[agent_id]) > 100:
            self.agent_task_history[agent_id] = self.agent_task_history[agent_id][-100:]

    def _select_agent_for_task_excluding(self, task: SubTask, excluded_agents: List[str]) -> Optional[Agent]:
        """Select agent excluding specific agents"""
        available_agents = {
            aid: agent for aid, agent in self.agent_registry.items()
            if aid not in excluded_agents
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

    async def _workflow_timeout_monitor(self, workflow_id: str):
        """Monitor workflow timeout"""
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
                        task.completed_at = datetime.now()

                workflow.status = WorkflowStatus.FAILED
                workflow.error_message = "Workflow timeout exceeded"
                workflow.completed_at = datetime.now()

    def set_custom_routing_function(self, fn: Callable[[SubTask, List[Agent]], Agent]):
        """Set custom routing function"""
        self.custom_routing_fn = fn

    def add_routing_rule(self, rule: AgentRoutingRule):
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
            "status": workflow.status.value if hasattr(workflow.status, 'value') else str(workflow.status),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "average_task_time": sum(task_times) / len(task_times) if task_times else 0,
            "total_execution_time": (
                (workflow.completed_at - workflow.started_at).total_seconds()
                if workflow.completed_at and workflow.started_at else 0
            ),
            "error_summary": self._get_workflow_error_summary(workflow),
            "agent_utilization": self._get_agent_utilization(workflow)
        }

        return metrics

    def _get_workflow_error_summary(self, workflow: Workflow) -> Dict[str, Any]:
        """Get error summary for workflow"""
        errors = []
        for task in workflow.tasks.values():
            if task.error_message:
                errors.append({
                    "task_id": task.id,
                    "error": task.error_message,
                    "task_description": task.description
                })

        return {
            "total_errors": len(errors),
            "errors": errors
        }

    def _get_agent_utilization(self, workflow: Workflow) -> Dict[str, Any]:
        """Get agent utilization for workflow"""
        agent_tasks = {}

        for task in workflow.tasks.values():
            if task.assigned_agent_id:
                if task.assigned_agent_id not in agent_tasks:
                    agent_tasks[task.assigned_agent_id] = {
                        "total": 0,
                        "completed": 0,
                        "failed": 0
                    }

                agent_tasks[task.assigned_agent_id]["total"] += 1

                if task.status == TaskStatus.DONE:
                    agent_tasks[task.assigned_agent_id]["completed"] += 1
                elif task.status == TaskStatus.FAILED:
                    agent_tasks[task.assigned_agent_id]["failed"] += 1

        return agent_tasks
