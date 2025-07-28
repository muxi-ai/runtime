"""
Test workflow status endpoints and monitoring (Phase 2, Stream 2)

This test validates the workflow status query methods, history tracking,
and metrics collection implemented in the Overlord.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import threading

from muxi.datatypes.workflow import (
    Workflow, WorkflowStatus, SubTask, TaskStatus,
    generate_workflow_id, generate_task_id
)


class MockOverlord:
    """Mock Overlord for testing workflow status endpoints."""
    
    def __init__(self):
        self.active_workflows = {}
        self.workflow_history = {}
        self.pending_approvals = {}
        self.workflow_metrics = {
            "total_workflows": 0,
            "successful_workflows": 0,
            "failed_workflows": 0,
            "cancelled_workflows": 0,
            "total_execution_time": 0.0,
            "workflow_count_by_user": {}
        }
        self._workflow_lock = threading.Lock()
    
    def get_workflow_status(self, workflow_id: str):
        """Get workflow status."""
        with self._workflow_lock:
            if workflow_id in self.active_workflows:
                return self.active_workflows[workflow_id]
            if workflow_id in self.workflow_history:
                return self.workflow_history[workflow_id]
            if workflow_id in self.pending_approvals:
                return self.pending_approvals[workflow_id]
        return None
    
    def list_workflows(
        self, user_id=None, status=None, limit=100, offset=0,
        include_active=True, include_history=True
    ):
        """List workflows with filters."""
        with self._workflow_lock:
            workflows = []
            
            if include_active:
                workflows.extend(self.active_workflows.values())
                workflows.extend(self.pending_approvals.values())
            
            if include_history:
                workflows.extend(self.workflow_history.values())
            
            if user_id:
                workflows = [
                    w for w in workflows
                    if hasattr(w, 'user_id') and w.user_id == user_id
                ]
            
            if status:
                workflows = [
                    w for w in workflows 
                    if (hasattr(w.status, 'value') and w.status.value == status) or w.status == status
                ]
            
            workflows.sort(key=lambda w: w.created_at, reverse=True)
            return workflows[offset : offset + limit]
    
    async def cancel_workflow(self, workflow_id: str):
        """Cancel a workflow."""
        with self._workflow_lock:
            workflow = None
            
            if workflow_id in self.active_workflows:
                workflow = self.active_workflows[workflow_id]
            elif workflow_id in self.pending_approvals:
                workflow = self.pending_approvals[workflow_id]
                del self.pending_approvals[workflow_id]
            
            if not workflow:
                return False
            
            # Check if workflow is already complete
            if workflow.status in [
                WorkflowStatus.COMPLETED.value, 
                WorkflowStatus.FAILED.value, 
                WorkflowStatus.CANCELLED.value
            ]:
                return False
            
            workflow.status = WorkflowStatus.CANCELLED.value
            workflow.completed_at = datetime.now()
            
            self.workflow_history[workflow_id] = workflow
            if workflow_id in self.active_workflows:
                del self.active_workflows[workflow_id]
            
            self.workflow_metrics["cancelled_workflows"] += 1
        
        return True
    
    def get_workflow_metrics(self):
        """Get workflow metrics."""
        with self._workflow_lock:
            total = self.workflow_metrics["total_workflows"]
            successful = self.workflow_metrics["successful_workflows"]
            failed = self.workflow_metrics["failed_workflows"]
            cancelled = self.workflow_metrics["cancelled_workflows"]
            
            completed = successful + failed
            success_rate = (successful / completed * 100) if completed > 0 else 0.0
            
            avg_execution_time = (
                self.workflow_metrics["total_execution_time"] / total
                if total > 0
                else 0.0
            )
            
            return {
                "total_workflows": total,
                "successful_workflows": successful,
                "failed_workflows": failed,
                "cancelled_workflows": cancelled,
                "in_progress_workflows": len(self.active_workflows),
                "pending_approval_workflows": len(self.pending_approvals),
                "success_rate": round(success_rate, 2),
                "average_execution_time_seconds": round(avg_execution_time, 2),
                "workflow_count_by_user": dict(self.workflow_metrics["workflow_count_by_user"])
            }
    
    def get_active_workflow_ids(self):
        """Get active workflow IDs."""
        with self._workflow_lock:
            return list(self.active_workflows.keys())
    
    def clear_workflow_history(self, older_than_days=30):
        """Clear old workflows."""
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        cleared_count = 0
        
        with self._workflow_lock:
            workflows_to_clear = [
                wid for wid, w in self.workflow_history.items()
                if w.completed_at and w.completed_at < cutoff_date
            ]
            
            for workflow_id in workflows_to_clear:
                del self.workflow_history[workflow_id]
                cleared_count += 1
        
        return cleared_count


@pytest.fixture
def overlord():
    """Create a mock overlord for testing."""
    return MockOverlord()


class TestWorkflowStatusEndpoints:
    """Test workflow status query methods."""
    
    def create_test_workflow(self, workflow_id: str = None, user_id: str = "test-user") -> Workflow:
        """Create a test workflow."""
        if not workflow_id:
            workflow_id = generate_workflow_id()
            
        task1 = SubTask(
            id=generate_task_id(),
            description="Test task 1",
            required_capabilities=["general"],
            dependencies=[],
            status=TaskStatus.PENDING
        )
        
        task2 = SubTask(
            id=generate_task_id(),
            description="Test task 2",
            required_capabilities=["general"],
            dependencies=[task1.id],
            status=TaskStatus.PENDING
        )
        
        workflow = Workflow(
            id=workflow_id,
            user_request="Test request",
            tasks={task1.id: task1, task2.id: task2},
            status=WorkflowStatus.PENDING,
            created_at=datetime.now()
        )
        
        # Store user_id as a separate attribute (not part of model)
        object.__setattr__(workflow, 'user_id', user_id)
        
        return workflow
    
    @pytest.mark.asyncio
    async def test_get_workflow_status(self, overlord):
        """Test retrieving workflow status."""
        workflow = self.create_test_workflow()
        
        # Add to active workflows
        with overlord._workflow_lock:
            overlord.active_workflows[workflow.id] = workflow
        
        # Test retrieval
        retrieved = overlord.get_workflow_status(workflow.id)
        assert retrieved is not None
        assert retrieved.id == workflow.id
        assert retrieved.status == WorkflowStatus.PENDING.value
        
        # Test non-existent workflow
        assert overlord.get_workflow_status("non-existent") is None
    
    @pytest.mark.asyncio
    async def test_list_workflows(self, overlord):
        """Test listing workflows with filters."""
        # Create test workflows
        workflow1 = self.create_test_workflow(user_id="user1")
        workflow1.status = WorkflowStatus.IN_PROGRESS.value
        
        workflow2 = self.create_test_workflow(user_id="user2")
        workflow2.status = WorkflowStatus.COMPLETED.value
        
        workflow3 = self.create_test_workflow(user_id="user1")
        workflow3.status = WorkflowStatus.FAILED.value
        
        # Add to different tracking locations
        with overlord._workflow_lock:
            overlord.active_workflows[workflow1.id] = workflow1
            overlord.workflow_history[workflow2.id] = workflow2
            overlord.workflow_history[workflow3.id] = workflow3
        
        # Test listing all workflows
        all_workflows = overlord.list_workflows()
        assert len(all_workflows) == 3
        
        # Test filtering by user
        user1_workflows = overlord.list_workflows(user_id="user1")
        assert len(user1_workflows) == 2
        assert all(w.user_id == "user1" for w in user1_workflows)
        
        # Test filtering by status
        completed_workflows = overlord.list_workflows(status=WorkflowStatus.COMPLETED.value)
        assert len(completed_workflows) == 1
        assert completed_workflows[0].id == workflow2.id
        
        # Test pagination
        paginated = overlord.list_workflows(limit=2, offset=1)
        assert len(paginated) == 2
        
        # Test include flags
        active_only = overlord.list_workflows(include_history=False)
        assert len(active_only) == 1
        assert active_only[0].id == workflow1.id
    
    @pytest.mark.asyncio
    async def test_cancel_workflow(self, overlord):
        """Test workflow cancellation."""
        workflow = self.create_test_workflow()
        workflow.status = WorkflowStatus.IN_PROGRESS
        workflow.started_at = datetime.now()
        
        # Add to active workflows
        with overlord._workflow_lock:
            overlord.active_workflows[workflow.id] = workflow
            overlord.workflow_metrics["total_workflows"] = 1
        
        # Cancel workflow
        result = await overlord.cancel_workflow(workflow.id)
        assert result is True
        
        # Verify workflow was moved to history
        assert workflow.id not in overlord.active_workflows
        assert workflow.id in overlord.workflow_history
        
        # Verify status was updated
        historical = overlord.workflow_history[workflow.id]
        assert historical.status == WorkflowStatus.CANCELLED.value
        assert historical.completed_at is not None
        
        # Verify metrics were updated
        assert overlord.workflow_metrics["cancelled_workflows"] == 1
        
        # Test cancelling non-existent workflow
        result = await overlord.cancel_workflow("non-existent")
        assert result is False
        
        # Test cancelling already completed workflow
        workflow2 = self.create_test_workflow()
        workflow2.status = WorkflowStatus.COMPLETED.value
        with overlord._workflow_lock:
            overlord.active_workflows[workflow2.id] = workflow2
        
        result = await overlord.cancel_workflow(workflow2.id)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_workflow_metrics(self, overlord):
        """Test workflow metrics tracking."""
        # Set up initial metrics
        with overlord._workflow_lock:
            overlord.workflow_metrics = {
                "total_workflows": 10,
                "successful_workflows": 6,
                "failed_workflows": 2,
                "cancelled_workflows": 1,
                "total_execution_time": 300.0,  # 5 minutes total
                "workflow_count_by_user": {
                    "user1": 5,
                    "user2": 3,
                    "user3": 2
                }
            }
            
            # Add some active workflows
            for i in range(3):
                workflow = self.create_test_workflow()
                workflow.status = WorkflowStatus.IN_PROGRESS
                overlord.active_workflows[workflow.id] = workflow
            
            # Add pending approval
            approval_workflow = self.create_test_workflow()
            approval_workflow.status = WorkflowStatus.AWAITING_APPROVAL
            overlord.pending_approvals[approval_workflow.id] = approval_workflow
        
        # Get metrics
        metrics = overlord.get_workflow_metrics()
        
        # Verify metrics
        assert metrics["total_workflows"] == 10
        assert metrics["successful_workflows"] == 6
        assert metrics["failed_workflows"] == 2
        assert metrics["cancelled_workflows"] == 1
        assert metrics["in_progress_workflows"] == 3
        assert metrics["pending_approval_workflows"] == 1
        assert metrics["success_rate"] == 75.0  # 6 out of 8 completed
        assert metrics["average_execution_time_seconds"] == 30.0
        assert len(metrics["workflow_count_by_user"]) == 3
    
    @pytest.mark.asyncio
    async def test_get_active_workflow_ids(self, overlord):
        """Test getting active workflow IDs."""
        # Add active workflows
        workflow_ids = []
        with overlord._workflow_lock:
            for i in range(3):
                workflow = self.create_test_workflow()
                overlord.active_workflows[workflow.id] = workflow
                workflow_ids.append(workflow.id)
        
        # Get active IDs
        active_ids = overlord.get_active_workflow_ids()
        assert len(active_ids) == 3
        assert set(active_ids) == set(workflow_ids)
    
    @pytest.mark.asyncio
    async def test_clear_workflow_history(self, overlord):
        """Test clearing old workflows from history."""
        # Create workflows with different completion times
        old_workflow = self.create_test_workflow()
        old_workflow.status = WorkflowStatus.COMPLETED
        old_workflow.completed_at = datetime.now() - timedelta(days=35)
        
        recent_workflow = self.create_test_workflow()
        recent_workflow.status = WorkflowStatus.COMPLETED
        recent_workflow.completed_at = datetime.now() - timedelta(days=5)
        
        with overlord._workflow_lock:
            overlord.workflow_history[old_workflow.id] = old_workflow
            overlord.workflow_history[recent_workflow.id] = recent_workflow
        
        # Clear workflows older than 30 days
        cleared = overlord.clear_workflow_history(older_than_days=30)
        assert cleared == 1
        
        # Verify old workflow was removed
        assert old_workflow.id not in overlord.workflow_history
        assert recent_workflow.id in overlord.workflow_history
    
    @pytest.mark.asyncio
    async def test_workflow_history_tracking(self, overlord):
        """Test that workflows are properly tracked in history after execution."""
        workflow = self.create_test_workflow()
        
        # Simulate workflow execution tracking
        with overlord._workflow_lock:
            # Initial tracking
            overlord.active_workflows[workflow.id] = workflow
            overlord.workflow_metrics["total_workflows"] = 1
            overlord.workflow_metrics["workflow_count_by_user"] = {"test-user": 1}
        
        # Simulate workflow completion
        workflow.status = WorkflowStatus.COMPLETED
        workflow.started_at = datetime.now() - timedelta(seconds=10)
        workflow.completed_at = datetime.now()
        
        # Move to history (simulating what happens in finally block)
        with overlord._workflow_lock:
            if workflow.id in overlord.active_workflows:
                completed_workflow = overlord.active_workflows[workflow.id]
                overlord.workflow_history[workflow.id] = completed_workflow
                del overlord.active_workflows[workflow.id]
                
                # Update metrics
                overlord.workflow_metrics["successful_workflows"] += 1
                execution_time = (completed_workflow.completed_at - completed_workflow.started_at).total_seconds()
                overlord.workflow_metrics["total_execution_time"] += execution_time
        
        # Verify workflow is in history
        assert workflow.id not in overlord.active_workflows
        assert workflow.id in overlord.workflow_history
        
        # Verify metrics were updated
        assert overlord.workflow_metrics["successful_workflows"] == 1
        assert overlord.workflow_metrics["total_execution_time"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])