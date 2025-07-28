"""
Tests for WorkflowExecutor - Workflow execution engine.

Tests the workflow execution engine that orchestrates multi-agent workflows
with DAG-based coordination and parallel execution.
"""

import pytest
from unittest.mock import AsyncMock

from src.muxi.formation.workflow.executor import WorkflowExecutor, ProgressTracker
from src.muxi.datatypes.workflow import (
    Workflow, SubTask, TaskStatus, WorkflowStatus, TaskResult
)
from src.muxi.formation.agents import Agent


class TestWorkflowExecutor:
    """Test WorkflowExecutor functionality."""

    @pytest.fixture
    def mock_agents(self):
        """Create mock agents for testing."""
        agent1 = AsyncMock(spec=Agent)
        agent1.agent_id = "research_agent"
        agent1.process_message.return_value = "Research completed successfully"

        agent2 = AsyncMock(spec=Agent)
        agent2.agent_id = "writing_agent"
        agent2.process_message.return_value = "Report written successfully"

        return {
            "research_agent": agent1,
            "writing_agent": agent2
        }

    @pytest.fixture
    def executor(self, mock_agents):
        """Create WorkflowExecutor with mock agents."""
        return WorkflowExecutor(agent_registry=mock_agents)

    @pytest.fixture
    def simple_workflow(self):
        """Create simple workflow for testing."""
        return Workflow(
            id="test_workflow",
            user_request="Research and write report",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="Research AI trends",
                    required_capabilities=['research'],
                    dependencies=[],
                    estimated_complexity=6.0,
                    status=TaskStatus.PENDING
                ),
                "task_2": SubTask(
                    id="task_2",
                    description="Write report on findings",
                    required_capabilities=['writing'],
                    dependencies=['task_1'],
                    estimated_complexity=7.0,
                    status=TaskStatus.PENDING
                )
            },
            status=WorkflowStatus.PENDING
        )

    @pytest.fixture
    def parallel_workflow(self):
        """Create workflow with parallel tasks."""
        return Workflow(
            id="parallel_workflow",
            user_request="Multi-track project",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="Research market trends",
                    required_capabilities=['research'],
                    dependencies=[],
                    estimated_complexity=5.0
                ),
                "task_2": SubTask(
                    id="task_2",
                    description="Analyze competitor data",
                    required_capabilities=['analysis'],
                    dependencies=[],
                    estimated_complexity=5.0
                ),
                "task_3": SubTask(
                    id="task_3",
                    description="Synthesize findings",
                    required_capabilities=['writing'],
                    dependencies=['task_1', 'task_2'],
                    estimated_complexity=7.0
                )
            },
            status=WorkflowStatus.PENDING
        )

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self, executor, simple_workflow, mock_agents):
        """Test execution of simple sequential workflow."""

        # Execute
        result_workflow = await executor.execute_workflow(simple_workflow)

        # Verify workflow completion
        assert result_workflow.status == WorkflowStatus.COMPLETED
        assert result_workflow.started_at is not None
        assert result_workflow.completed_at is not None

        # Verify tasks completed
        task1 = result_workflow.tasks['task_1']
        task2 = result_workflow.tasks['task_2']

        assert task1.status == TaskStatus.DONE
        assert task2.status == TaskStatus.DONE
        assert task1.completed_at < task2.started_at  # Sequential execution

        # Verify agent calls
        mock_agents["research_agent"].process_message.assert_called_once()
        mock_agents["writing_agent"].process_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_parallel_workflow(self, executor, parallel_workflow):
        """Test execution of workflow with parallel tasks."""

        # Execute
        result_workflow = await executor.execute_workflow(parallel_workflow)

        # Verify completion
        assert result_workflow.status == WorkflowStatus.COMPLETED

        # Verify parallel tasks ran independently
        task1 = result_workflow.tasks['task_1']
        task2 = result_workflow.tasks['task_2']
        task3 = result_workflow.tasks['task_3']

        assert task1.status == TaskStatus.DONE
        assert task2.status == TaskStatus.DONE
        assert task3.status == TaskStatus.DONE

        # Task 3 should start after tasks 1 and 2 complete
        assert task3.started_at >= max(task1.completed_at, task2.completed_at)

    @pytest.mark.asyncio
    async def test_task_failure_handling(self, executor, simple_workflow, mock_agents):
        """Test handling of task failures."""

        # Setup task failure
        mock_agents["research_agent"].process_message.side_effect = Exception("Research failed")

        # Execute
        result_workflow = await executor.execute_workflow(simple_workflow)

        # Verify workflow failed
        assert result_workflow.status == WorkflowStatus.FAILED

        # Verify failed task
        task1 = result_workflow.tasks['task_1']
        assert task1.status == TaskStatus.FAILED
        assert task1.error_message == "Research failed"

        # Verify dependent task was not executed
        task2 = result_workflow.tasks['task_2']
        assert task2.status == TaskStatus.PENDING  # Should not have started

    @pytest.mark.asyncio
    async def test_collect_task_inputs(self, executor, simple_workflow):
        """Test collection of inputs from dependency tasks."""

        # Setup completed dependency task
        task1 = simple_workflow.tasks['task_1']
        task1.status = TaskStatus.DONE
        task1.outputs = {"research_data": "AI trends analysis"}

        # Store result in executor cache
        executor.task_results['task_1'] = TaskResult(
            task_id='task_1',
            status=TaskStatus.DONE,
            outputs={"research_data": "AI trends analysis"}
        )

        task2 = simple_workflow.tasks['task_2']

        # Collect inputs
        inputs = await executor._collect_task_inputs(task2, simple_workflow)

        # Verify inputs collected
        assert 'from_task_1' in inputs
        assert inputs['from_task_1']['research_data'] == "AI trends analysis"

    def test_select_agent_for_task(self, executor):
        """Test agent selection for tasks."""

        # Test research task
        research_task = SubTask(
            id="test_task",
            description="Research something",
            required_capabilities=['research'],
            dependencies=[],
            estimated_complexity=5.0
        )

        agent = executor._select_agent_for_task(research_task)
        assert agent is not None
        assert agent.agent_id in ["research_agent", "writing_agent"]

        # Test task with no specific capabilities
        general_task = SubTask(
            id="general_task",
            description="General task",
            required_capabilities=[],
            dependencies=[],
            estimated_complexity=3.0
        )

        agent = executor._select_agent_for_task(general_task)
        assert agent is not None

    @pytest.mark.asyncio
    async def test_execute_task_with_agent(self, executor, mock_agents):
        """Test individual task execution with agent."""

        task = SubTask(
            id="test_task",
            description="Test task",
            required_capabilities=['research'],
            dependencies=[],
            estimated_complexity=5.0
        )

        agent = mock_agents["research_agent"]
        context = {
            "workflow_id": "test_workflow",
            "user_request": "Test request",
            "inputs": {}
        }

        # Execute
        result = await executor._execute_task_with_agent(task, agent, context)

        # Verify
        assert result.task_id == "test_task"
        assert result.agent_id == "research_agent"
        assert result.status == TaskStatus.DONE
        assert "content" in result.outputs

    def test_create_task_prompt(self, executor):
        """Test task prompt creation."""

        task = SubTask(
            id="test_task",
            description="Research AI trends",
            required_capabilities=['research'],
            dependencies=[],
            estimated_complexity=6.0
        )

        context = {
            "user_request": "Research and analyze AI trends",
            "inputs": {"previous_data": "some data"}
        }

        prompt = executor._create_task_prompt(task, context)

        assert "Research AI trends" in prompt
        assert "Research and analyze AI trends" in prompt
        assert "research" in prompt
        assert "previous_data" in prompt

    def test_parse_task_response(self, executor):
        """Test parsing of task responses."""

        task = SubTask(
            id="test_task",
            description="Research task",
            required_capabilities=['research'],
            dependencies=[],
            estimated_complexity=5.0
        )

        response = "Here are the research findings..."

        outputs = executor._parse_task_response(response, task)

        assert "content" in outputs
        assert outputs["content"] == response
        assert outputs["task_id"] == "test_task"
        assert outputs["completed"] is True
        assert "research_findings" in outputs

    def test_should_continue_execution(self, executor, simple_workflow):
        """Test workflow continuation logic."""

        # No failures - should continue
        assert executor._should_continue_execution(simple_workflow) is True

        # Add failed task
        simple_workflow.tasks['task_1'].status = TaskStatus.FAILED

        # Should not continue with failures
        assert executor._should_continue_execution(simple_workflow) is False

    def test_determine_final_status(self, executor, simple_workflow):
        """Test final status determination."""

        # All tasks completed
        for task in simple_workflow.tasks.values():
            task.status = TaskStatus.DONE

        status = executor._determine_final_status(simple_workflow)
        assert status == WorkflowStatus.COMPLETED

        # Some tasks failed
        simple_workflow.tasks['task_1'].status = TaskStatus.FAILED

        status = executor._determine_final_status(simple_workflow)
        assert status == WorkflowStatus.FAILED

    def test_progress_callbacks(self, executor):
        """Test progress callback system."""

        callback_called = False
        callback_workflow_id = None

        def test_callback(workflow_id, workflow):
            nonlocal callback_called, callback_workflow_id
            callback_called = True
            callback_workflow_id = workflow_id

        # Add callback
        executor.add_progress_callback(test_callback)

        # Trigger notification
        test_workflow = Workflow(id="test", user_request="test", tasks={})
        executor._notify_progress("test", test_workflow)

        assert callback_called is True
        assert callback_workflow_id == "test"

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, executor, simple_workflow):
        """Test workflow cancellation."""

        # Start workflow (simulate in-progress)
        simple_workflow.status = WorkflowStatus.IN_PROGRESS
        simple_workflow.tasks['task_1'].status = TaskStatus.IN_PROGRESS
        executor.active_workflows[simple_workflow.id] = simple_workflow

        # Cancel workflow
        result = await executor.cancel_workflow(simple_workflow.id)

        assert result is True
        assert simple_workflow.status == WorkflowStatus.CANCELLED
        assert simple_workflow.tasks['task_1'].status == TaskStatus.CANCELLED

    def test_get_workflow_progress(self, executor, simple_workflow):
        """Test workflow progress reporting."""

        # Setup workflow in progress
        simple_workflow.tasks['task_1'].status = TaskStatus.DONE
        simple_workflow.tasks['task_2'].status = TaskStatus.IN_PROGRESS
        executor.active_workflows[simple_workflow.id] = simple_workflow

        # Get progress
        progress = executor.get_workflow_progress(simple_workflow.id)

        assert progress is not None
        assert progress['total_tasks'] == 2
        assert progress['completed_tasks'] == 1
        assert progress['in_progress_tasks'] == 1
        assert progress['progress_percentage'] == 50.0


class TestProgressTracker:
    """Test ProgressTracker functionality."""

    @pytest.fixture
    def progress_tracker(self):
        """Create ProgressTracker instance."""
        return ProgressTracker()

    @pytest.fixture
    def test_workflow(self):
        """Create test workflow."""
        return Workflow(
            id="test_workflow",
            user_request="Test request",
            tasks={
                "task_1": SubTask(
                    id="task_1",
                    description="Task 1",
                    required_capabilities=['general'],
                    dependencies=[],
                    estimated_complexity=5.0,
                    status=TaskStatus.DONE
                ),
                "task_2": SubTask(
                    id="task_2",
                    description="Task 2",
                    required_capabilities=['general'],
                    dependencies=[],
                    estimated_complexity=5.0,
                    status=TaskStatus.IN_PROGRESS
                ),
                "task_3": SubTask(
                    id="task_3",
                    description="Task 3",
                    required_capabilities=['general'],
                    dependencies=[],
                    estimated_complexity=5.0,
                    status=TaskStatus.PENDING
                )
            },
            status=WorkflowStatus.IN_PROGRESS
        )

    def test_update_workflow_progress(self, progress_tracker, test_workflow):
        """Test workflow progress updates."""

        # Update progress
        progress_tracker.update_workflow_progress("test_workflow", test_workflow)

        # Verify progress stored
        progress = progress_tracker.get_progress("test_workflow")
        assert progress is not None
        assert progress['total_tasks'] == 3
        assert progress['completed_tasks'] == 1
        assert progress['failed_tasks'] == 0
        assert progress['progress_percentage'] == 33.33333333333333

    def test_get_progress_nonexistent(self, progress_tracker):
        """Test getting progress for non-existent workflow."""

        progress = progress_tracker.get_progress("nonexistent")
        assert progress is None

    def test_progress_calculation(self, progress_tracker, test_workflow):
        """Test progress percentage calculation."""

        # All tasks pending
        for task in test_workflow.tasks.values():
            task.status = TaskStatus.PENDING

        progress_tracker.update_workflow_progress("test", test_workflow)
        progress = progress_tracker.get_progress("test")
        assert progress['progress_percentage'] == 0.0

        # All tasks completed
        for task in test_workflow.tasks.values():
            task.status = TaskStatus.DONE

        progress_tracker.update_workflow_progress("test", test_workflow)
        progress = progress_tracker.get_progress("test")
        assert progress['progress_percentage'] == 100.0
