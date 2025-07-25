"""
MUXI Task Status Tests

Tests for the unified TaskStatus enumeration and its helper methods.
Ensures proper functionality and backward compatibility.
"""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

try:
    from muxi.datatypes.task_status import TaskStatus

    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    print(f"Warning: Could not import TaskStatus modules: {e}")
    print("Skipping task status tests")


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import TaskStatus modules")
class TestUnifiedTaskStatus:
    """Test the unified TaskStatus enumeration."""

    def test_all_required_states_present(self):
        """Test that all required states from both systems are present."""
        # Original parallel states
        assert hasattr(TaskStatus, "PENDING")
        assert hasattr(TaskStatus, "READY")
        assert hasattr(TaskStatus, "RUNNING")
        assert hasattr(TaskStatus, "COMPLETED")
        assert hasattr(TaskStatus, "FAILED")
        assert hasattr(TaskStatus, "SKIPPED")

        # Original workflow states
        assert hasattr(TaskStatus, "PENDING")  # Shared
        assert hasattr(TaskStatus, "IN_PROGRESS")
        assert hasattr(TaskStatus, "DONE")
        assert hasattr(TaskStatus, "FAILED")  # Shared
        assert hasattr(TaskStatus, "CANCELLED")
        assert hasattr(TaskStatus, "DEFERRED")
        assert hasattr(TaskStatus, "REVIEW")

    def test_state_values(self):
        """Test that state values are correct."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.READY.value == "ready"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.DEFERRED.value == "deferred"
        assert TaskStatus.REVIEW.value == "review"

    def test_is_terminal_state(self):
        """Test the is_terminal_state helper method."""
        # Terminal states
        assert TaskStatus.is_terminal_state(TaskStatus.COMPLETED) == True
        assert TaskStatus.is_terminal_state(TaskStatus.DONE) == True
        assert TaskStatus.is_terminal_state(TaskStatus.FAILED) == True
        assert TaskStatus.is_terminal_state(TaskStatus.CANCELLED) == True
        assert TaskStatus.is_terminal_state(TaskStatus.SKIPPED) == True

        # Non-terminal states
        assert TaskStatus.is_terminal_state(TaskStatus.PENDING) == False
        assert TaskStatus.is_terminal_state(TaskStatus.READY) == False
        assert TaskStatus.is_terminal_state(TaskStatus.RUNNING) == False
        assert TaskStatus.is_terminal_state(TaskStatus.IN_PROGRESS) == False
        assert TaskStatus.is_terminal_state(TaskStatus.DEFERRED) == False
        assert TaskStatus.is_terminal_state(TaskStatus.REVIEW) == False

    def test_is_active_state(self):
        """Test the is_active_state helper method."""
        # Active states
        assert TaskStatus.is_active_state(TaskStatus.RUNNING) == True
        assert TaskStatus.is_active_state(TaskStatus.IN_PROGRESS) == True

        # Non-active states
        assert TaskStatus.is_active_state(TaskStatus.PENDING) == False
        assert TaskStatus.is_active_state(TaskStatus.READY) == False
        assert TaskStatus.is_active_state(TaskStatus.COMPLETED) == False
        assert TaskStatus.is_active_state(TaskStatus.DONE) == False
        assert TaskStatus.is_active_state(TaskStatus.FAILED) == False
        assert TaskStatus.is_active_state(TaskStatus.CANCELLED) == False
        assert TaskStatus.is_active_state(TaskStatus.SKIPPED) == False
        assert TaskStatus.is_active_state(TaskStatus.DEFERRED) == False
        assert TaskStatus.is_active_state(TaskStatus.REVIEW) == False

    def test_is_ready_state(self):
        """Test the is_ready_state helper method."""
        # Ready states
        assert TaskStatus.is_ready_state(TaskStatus.READY) == True
        assert TaskStatus.is_ready_state(TaskStatus.PENDING) == True

        # Non-ready states
        assert TaskStatus.is_ready_state(TaskStatus.RUNNING) == False
        assert TaskStatus.is_ready_state(TaskStatus.IN_PROGRESS) == False
        assert TaskStatus.is_ready_state(TaskStatus.COMPLETED) == False
        assert TaskStatus.is_ready_state(TaskStatus.DONE) == False
        assert TaskStatus.is_ready_state(TaskStatus.FAILED) == False
        assert TaskStatus.is_ready_state(TaskStatus.CANCELLED) == False
        assert TaskStatus.is_ready_state(TaskStatus.SKIPPED) == False
        assert TaskStatus.is_ready_state(TaskStatus.DEFERRED) == False
        assert TaskStatus.is_ready_state(TaskStatus.REVIEW) == False

    def test_is_success_state(self):
        """Test the is_success_state helper method."""
        # Success states
        assert TaskStatus.is_success_state(TaskStatus.COMPLETED) == True
        assert TaskStatus.is_success_state(TaskStatus.DONE) == True

        # Non-success states
        assert TaskStatus.is_success_state(TaskStatus.PENDING) == False
        assert TaskStatus.is_success_state(TaskStatus.READY) == False
        assert TaskStatus.is_success_state(TaskStatus.RUNNING) == False
        assert TaskStatus.is_success_state(TaskStatus.IN_PROGRESS) == False
        assert TaskStatus.is_success_state(TaskStatus.FAILED) == False
        assert TaskStatus.is_success_state(TaskStatus.CANCELLED) == False
        assert TaskStatus.is_success_state(TaskStatus.SKIPPED) == False
        assert TaskStatus.is_success_state(TaskStatus.DEFERRED) == False
        assert TaskStatus.is_success_state(TaskStatus.REVIEW) == False


@pytest.mark.skipif(not IMPORTS_AVAILABLE, reason="Could not import TaskStatus modules")
class TestTaskStatusIntegration:
    """Test integration with existing datatype classes."""

    def test_parallel_task_node_integration(self):
        """Test TaskStatus works with parallel TaskNode."""
        from muxi.datatypes.parallel import TaskNode

        task = TaskNode(
            task_id="test_task", description="Test task", required_capabilities=["test"]
        )

        # Default status should be PENDING
        assert task.status == TaskStatus.PENDING

        # Should be able to set parallel-specific states
        task.status = TaskStatus.READY
        assert task.status == TaskStatus.READY

        task.status = TaskStatus.RUNNING
        assert task.status == TaskStatus.RUNNING

        task.status = TaskStatus.COMPLETED
        assert task.status == TaskStatus.COMPLETED

        task.status = TaskStatus.SKIPPED
        assert task.status == TaskStatus.SKIPPED

    def test_workflow_sub_task_integration(self):
        """Test TaskStatus works with workflow SubTask."""
        from muxi.datatypes.workflow import SubTask

        task = SubTask(id="test_task", description="Test task", required_capabilities=["test"])

        # Default status should be PENDING
        assert task.status == TaskStatus.PENDING

        # Should be able to set workflow-specific states
        task.status = TaskStatus.IN_PROGRESS
        assert task.status == TaskStatus.IN_PROGRESS

        task.status = TaskStatus.DONE
        assert task.status == TaskStatus.DONE

        task.status = TaskStatus.CANCELLED
        assert task.status == TaskStatus.CANCELLED

        task.status = TaskStatus.DEFERRED
        assert task.status == TaskStatus.DEFERRED

        task.status = TaskStatus.REVIEW
        assert task.status == TaskStatus.REVIEW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
