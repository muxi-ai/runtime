"""
Tests for workflow data structures and utility functions.

Tests the foundational workflow types, validation, and DAG operations
as implemented in overlord.workflow.types.
"""

import pytest
from datetime import datetime

from src.muxi.datatypes.workflow import (
    TaskStatus, WorkflowStatus, ApprovalStatus,
    SubTask, Workflow, RequestAnalysis, TaskResult,
    generate_workflow_id, generate_task_id,
    validate_workflow_dag, build_execution_phases
)


class TestEnums:
    """Test enum definitions and values."""

    def test_task_status_enum(self):
        """Test TaskStatus enum has all required values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.DEFERRED.value == "deferred"
        assert TaskStatus.REVIEW.value == "review"

    def test_workflow_status_enum(self):
        """Test WorkflowStatus enum has all required values."""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.IN_PROGRESS.value == "in_progress"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"
        assert WorkflowStatus.AWAITING_APPROVAL.value == "awaiting_approval"

    def test_approval_status_enum(self):
        """Test ApprovalStatus enum has all required values."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.MODIFIED.value == "modified"


class TestSubTask:
    """Test SubTask dataclass."""

    def test_subtask_creation(self):
        """Test creating a SubTask with required fields."""
        task = SubTask(
            id="task_1",
            description="Test task",
            required_capabilities=["general"],
            estimated_complexity=5
        )

        assert task.id == "task_1"
        assert task.description == "Test task"
        assert task.required_capabilities == ["general"]
        assert task.estimated_complexity == 5
        assert task.status == TaskStatus.PENDING
        assert task.dependencies == []
        assert task.outputs == {}

    def test_subtask_with_dependencies(self):
        """Test SubTask with dependencies."""
        task = SubTask(
            id="task_2",
            description="Dependent task",
            required_capabilities=["analysis"],
            estimated_complexity=7,
            dependencies=["task_1"]
        )

        assert task.dependencies == ["task_1"]

    def test_subtask_timestamps(self):
        """Test SubTask timestamp handling."""
        task = SubTask(
            id="task_3",
            description="Timestamp test",
            required_capabilities=["general"],
            estimated_complexity=3
        )

        # Initially no timestamps
        assert task.started_at is None
        assert task.completed_at is None

        # Set timestamps
        now = datetime.now()
        task.started_at = now
        assert task.started_at == now


class TestWorkflow:
    """Test Workflow dataclass."""

    def test_workflow_creation(self):
        """Test creating a Workflow."""
        task1 = SubTask(
            id="task_1",
            description="First task",
            required_capabilities=["general"],
            estimated_complexity=5
        )

        workflow = Workflow(
            id="workflow_1",
            user_request="Test workflow",
            tasks={"task_1": task1}
        )

        assert workflow.id == "workflow_1"
        assert workflow.user_request == "Test workflow"
        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.approval_status == ApprovalStatus.PENDING
        assert len(workflow.tasks) == 1
        assert "task_1" in workflow.tasks

    def test_workflow_with_multiple_tasks(self):
        """Test Workflow with multiple tasks."""
        tasks = {}
        for i in range(3):
            task_id = f"task_{i+1}"
            tasks[task_id] = SubTask(
                id=task_id,
                description=f"Task {i+1}",
                required_capabilities=["general"],
                estimated_complexity=5
            )

        workflow = Workflow(
            id="workflow_multi",
            user_request="Multi-task workflow",
            tasks=tasks
        )

        assert len(workflow.tasks) == 3
        assert all(f"task_{i+1}" in workflow.tasks for i in range(3))


class TestRequestAnalysis:
    """Test RequestAnalysis dataclass."""

    def test_request_analysis_creation(self):
        """Test creating RequestAnalysis."""
        analysis = RequestAnalysis(
            complexity_score=8.5,
            requires_decomposition=True,
            requires_approval=False,
            identified_capabilities=["research", "writing"],
            confidence_score=0.9
        )

        assert analysis.complexity_score == 8.5
        assert analysis.requires_decomposition is True
        assert analysis.requires_approval is False
        assert analysis.identified_capabilities == ["research", "writing"]
        assert analysis.confidence_score == 0.9

    def test_request_analysis_with_reasoning(self):
        """Test RequestAnalysis with reasoning."""
        analysis = RequestAnalysis(
            complexity_score=6.0,
            requires_decomposition=True,
            requires_approval=True,
            identified_capabilities=["analysis"],
            confidence_score=0.8,
            reasoning="Complex analytical task requiring multiple steps"
        )

        assert analysis.reasoning == "Complex analytical task requiring multiple steps"


class TestTaskResult:
    """Test TaskResult dataclass."""

    def test_task_result_creation(self):
        """Test creating TaskResult."""
        result = TaskResult(
            task_id="task_1",
            status=TaskStatus.DONE,
            outputs={"content": "Task completed successfully"},
            agent_id="agent_1"
        )

        assert result.task_id == "task_1"
        assert result.status == TaskStatus.DONE
        assert result.outputs == {"content": "Task completed successfully"}
        assert result.agent_id == "agent_1"
        assert result.error_message is None

    def test_task_result_with_error(self):
        """Test TaskResult with error."""
        result = TaskResult(
            task_id="task_2",
            status=TaskStatus.FAILED,
            outputs={},
            error_message="Task execution failed"
        )

        assert result.status == TaskStatus.FAILED
        assert result.error_message == "Task execution failed"
        assert result.outputs == {}


class TestUtilityFunctions:
    """Test utility functions."""

    def test_generate_workflow_id(self):
        """Test workflow ID generation."""
        id1 = generate_workflow_id()
        id2 = generate_workflow_id()

        # IDs should be different
        assert id1 != id2

        # IDs should have expected format
        assert id1.startswith("wf_")
        assert len(id1) > 10  # Should be reasonably long

    def test_generate_task_id(self):
        """Test task ID generation."""
        id1 = generate_task_id()
        id2 = generate_task_id()

        # IDs should be different
        assert id1 != id2

        # IDs should have expected format
        assert id1.startswith("task_")
        assert len(id1) > 15  # Should be reasonably long

    def test_validate_workflow_dag_valid(self):
        """Test DAG validation with valid workflow."""
        # Create tasks with valid dependencies
        task1 = SubTask(
            id="task_1",
            description="First task",
            required_capabilities=["general"],
            estimated_complexity=5
        )

        task2 = SubTask(
            id="task_2",
            description="Second task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]
        )

        task3 = SubTask(
            id="task_3",
            description="Third task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1", "task_2"]
        )

        workflow = Workflow(
            id="test_workflow",
            user_request="Test",
            tasks={
                "task_1": task1,
                "task_2": task2,
                "task_3": task3
            }
        )

        is_valid, errors = validate_workflow_dag(workflow)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_workflow_dag_circular_dependency(self):
        """Test DAG validation with circular dependency."""
        # Create tasks with circular dependencies
        task1 = SubTask(
            id="task_1",
            description="First task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_2"]  # Circular: task_1 -> task_2 -> task_1
        )

        task2 = SubTask(
            id="task_2",
            description="Second task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]  # Circular: task_2 -> task_1 -> task_2
        )

        workflow = Workflow(
            id="circular_workflow",
            user_request="Test circular",
            tasks={
                "task_1": task1,
                "task_2": task2
            }
        )

        is_valid, errors = validate_workflow_dag(workflow)
        assert is_valid is False
        assert len(errors) > 0
        assert any("circular" in error.lower() for error in errors)

    def test_validate_workflow_dag_missing_dependency(self):
        """Test DAG validation with missing dependency."""
        task1 = SubTask(
            id="task_1",
            description="Task with missing dependency",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["nonexistent_task"]
        )

        workflow = Workflow(
            id="missing_dep_workflow",
            user_request="Test missing dependency",
            tasks={"task_1": task1}
        )

        is_valid, errors = validate_workflow_dag(workflow)
        assert is_valid is False
        assert len(errors) > 0
        assert any("nonexistent_task" in error for error in errors)

    def test_build_execution_phases_simple(self):
        """Test execution phase building for simple workflow."""
        # Create linear dependency chain: task_1 -> task_2 -> task_3
        task1 = SubTask(
            id="task_1",
            description="First task",
            required_capabilities=["general"],
            estimated_complexity=5
        )

        task2 = SubTask(
            id="task_2",
            description="Second task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]
        )

        task3 = SubTask(
            id="task_3",
            description="Third task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_2"]
        )

        workflow = Workflow(
            id="linear_workflow",
            user_request="Linear test",
            tasks={
                "task_1": task1,
                "task_2": task2,
                "task_3": task3
            }
        )

        phases = build_execution_phases(workflow)

        # Should have 3 phases for linear execution
        assert len(phases) == 3
        assert phases[0] == ["task_1"]  # Phase 1: no dependencies
        assert phases[1] == ["task_2"]  # Phase 2: depends on task_1
        assert phases[2] == ["task_3"]  # Phase 3: depends on task_2

    def test_build_execution_phases_parallel(self):
        """Test execution phase building for parallel workflow."""
        # Create parallel tasks: task_1 -> [task_2, task_3] -> task_4
        task1 = SubTask(
            id="task_1",
            description="First task",
            required_capabilities=["general"],
            estimated_complexity=5
        )

        task2 = SubTask(
            id="task_2",
            description="Second task (parallel)",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]
        )

        task3 = SubTask(
            id="task_3",
            description="Third task (parallel)",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]
        )

        task4 = SubTask(
            id="task_4",
            description="Fourth task",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_2", "task_3"]
        )

        workflow = Workflow(
            id="parallel_workflow",
            user_request="Parallel test",
            tasks={
                "task_1": task1,
                "task_2": task2,
                "task_3": task3,
                "task_4": task4
            }
        )

        phases = build_execution_phases(workflow)

        # Should have 3 phases
        assert len(phases) == 3
        assert phases[0] == ["task_1"]  # Phase 1: no dependencies
        assert set(phases[1]) == {"task_2", "task_3"}  # Phase 2: parallel execution
        assert phases[2] == ["task_4"]  # Phase 3: depends on both parallel tasks

    def test_build_execution_phases_complex(self):
        """Test execution phase building for complex workflow."""
        # Complex DAG:
        # task_1 -> task_2 -> task_4
        #     ↓       ↓       ↑
        # task_3 ------> task_5

        tasks = {}

        tasks["task_1"] = SubTask(
            id="task_1",
            description="Root task",
            required_capabilities=["general"],
            estimated_complexity=5
        )

        tasks["task_2"] = SubTask(
            id="task_2",
            description="Task 2",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]
        )

        tasks["task_3"] = SubTask(
            id="task_3",
            description="Task 3",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_1"]
        )

        tasks["task_4"] = SubTask(
            id="task_4",
            description="Task 4",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_2", "task_5"]
        )

        tasks["task_5"] = SubTask(
            id="task_5",
            description="Task 5",
            required_capabilities=["general"],
            estimated_complexity=5,
            dependencies=["task_2", "task_3"]
        )

        workflow = Workflow(
            id="complex_workflow",
            user_request="Complex test",
            tasks=tasks
        )

        phases = build_execution_phases(workflow)

        # Verify phases make sense
        assert len(phases) >= 3
        assert phases[0] == ["task_1"]  # First phase: no dependencies
        assert set(phases[1]) == {"task_2", "task_3"}  # Second phase: depend on task_1

        # task_5 should come before task_4 (since task_4 depends on task_5)
        task_5_phase = None
        task_4_phase = None
        for i, phase in enumerate(phases):
            if "task_5" in phase:
                task_5_phase = i
            if "task_4" in phase:
                task_4_phase = i

        assert task_5_phase is not None
        assert task_4_phase is not None
        assert task_5_phase < task_4_phase


@pytest.fixture
def sample_workflow():
    """Create sample workflow for testing."""
    task1 = SubTask(
        id="task_1",
        description="Research topic",
        required_capabilities=["research"],
        estimated_complexity=6
    )

    task2 = SubTask(
        id="task_2",
        description="Write report",
        required_capabilities=["writing"],
        estimated_complexity=7,
        dependencies=["task_1"]
    )

    return Workflow(
        id="sample_workflow",
        user_request="Create a research report",
        tasks={"task_1": task1, "task_2": task2}
    )


class TestWorkflowIntegration:
    """Integration tests for workflow components."""

    def test_workflow_lifecycle(self, sample_workflow):
        """Test complete workflow lifecycle."""
        workflow = sample_workflow

        # Initial state
        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.approval_status == ApprovalStatus.PENDING

        # Validate DAG
        is_valid, errors = validate_workflow_dag(workflow)
        assert is_valid is True
        assert len(errors) == 0

        # Build execution phases
        phases = build_execution_phases(workflow)
        assert len(phases) == 2
        assert phases[0] == ["task_1"]
        assert phases[1] == ["task_2"]

        # Update workflow status
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()

        # Complete first task
        workflow.tasks["task_1"].status = TaskStatus.DONE
        workflow.tasks["task_1"].completed_at = datetime.now()
        workflow.tasks["task_1"].outputs = {"research_data": "Sample research findings"}

        # Complete second task
        workflow.tasks["task_2"].status = TaskStatus.DONE
        workflow.tasks["task_2"].completed_at = datetime.now()
        workflow.tasks["task_2"].outputs = {"report": "Final research report"}

        # Complete workflow
        workflow.status = WorkflowStatus.COMPLETED
        workflow.completed_at = datetime.now()

        # Verify final state
        assert workflow.status == WorkflowStatus.COMPLETED
        assert all(task.status == TaskStatus.DONE for task in workflow.tasks.values())
        assert workflow.completed_at is not None
