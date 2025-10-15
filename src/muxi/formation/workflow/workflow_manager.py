"""
Workflow Manager Module

This module provides centralized workflow state and lifecycle management,
extracting these responsibilities from the Overlord class for better
separation of concerns.

The WorkflowManager tracks active workflows, maintains workflow history,
manages pending approvals, and collects workflow metrics.
"""

import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List

from ...datatypes.workflow import Workflow, WorkflowStatus
from ...services import observability
from .workflow_metrics import WorkflowMetrics


class WorkflowManager:
    """
    Manages workflow state and lifecycle across the system.

    This class provides centralized tracking and management of workflows,
    including active workflows, history, pending approvals, and metrics.
    It ensures thread-safe access to workflow data and maintains proper
    state transitions.

    Attributes:
        active_workflows: Currently executing workflows
        workflow_history: All completed workflows
        pending_approvals: Workflows awaiting user approval
        workflow_metrics: Metrics tracking system
        _lock: Thread lock for concurrent access
    """

    def __init__(self):
        """Initialize the workflow manager with empty tracking structures."""
        # Workflow tracking
        self.active_workflows: Dict[str, Workflow] = {}
        self.workflow_history: Dict[str, Workflow] = {}
        self.pending_approvals: Dict[str, Workflow] = {}

        # Metrics tracking
        self.workflow_metrics = WorkflowMetrics()

        # Thread safety
        self._lock = threading.Lock()

        # REMOVE - line 51 (user: feels pointless)

    def track_workflow(self, workflow: Workflow, user_id: Optional[str] = None) -> None:
        """
        Begin tracking a new workflow.

        Adds the workflow to active workflows and updates metrics.

        Args:
            workflow: The workflow to track
            user_id: Optional user ID for user-specific metrics
        """
        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,
            level=observability.EventLevel.INFO,
            data={"event": "track_workflow_entry", "workflow_id": workflow.id},
            description="WorkflowManager.track_workflow - Entry"
        )

        with self._lock:
            workflow_id = workflow.id

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={"event": "track_workflow_lock", "workflow_id": workflow_id},
                description="WorkflowManager.track_workflow - Inside lock"
            )

            self.active_workflows[workflow_id] = workflow

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={"event": "track_workflow_stored", "workflow_id": workflow_id},
                description="WorkflowManager.track_workflow - Workflow stored in active_workflows"
            )

            # Update metrics
            self.workflow_metrics.increment_total_workflows()
            if user_id:
                self.workflow_metrics.increment_user_workflows(str(user_id))

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "event": "workflow_tracked",
                    "workflow_id": workflow_id,
                    "user_id": user_id,
                    "status": workflow.status.value if hasattr(workflow.status, 'value') else str(workflow.status)
                },
                description="Workflow tracked"
            )

    def get_active_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """
        Retrieve an active workflow by ID.

        Args:
            workflow_id: The workflow ID to look up

        Returns:
            The workflow if found in active workflows, None otherwise
        """
        with self._lock:
            return self.active_workflows.get(workflow_id)

    def complete_workflow(self, workflow_id: str, workflow: Workflow) -> None:
        """
        Mark a workflow as complete and move it to history.

        Updates the workflow's completion time, moves it from active to history,
        and updates relevant metrics based on the final status.

        Args:
            workflow_id: The workflow ID
            workflow: The completed workflow object
        """
        with self._lock:
            # Ensure workflow exists in active workflows
            if workflow_id not in self.active_workflows:
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "event": "workflow_complete_not_active",
                        "workflow_id": workflow_id
                    },
                    description="Workflow complete called on non-active workflow"
                )
                return

            # Move to history
            self.workflow_history[workflow_id] = workflow
            del self.active_workflows[workflow_id]

            # Update metrics based on status
            if workflow.status == WorkflowStatus.COMPLETED:
                self.workflow_metrics.increment_completed_workflows()
            elif workflow.status == WorkflowStatus.FAILED:
                self.workflow_metrics.increment_failed_workflows()
            elif workflow.status == WorkflowStatus.CANCELLED:
                self.workflow_metrics.increment_cancelled_workflows()

            # Track execution time
            execution_time = None
            if workflow.started_at and workflow.completed_at:
                execution_time = (workflow.completed_at - workflow.started_at).total_seconds()
                self.workflow_metrics.add_execution_time(execution_time)

            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "event": "workflow_completed",
                    "workflow_id": workflow_id,
                    "status": workflow.status,
                    "execution_time": execution_time
                },
                description="Workflow completed"
            )

    def get_workflow_history(self, workflow_id: str) -> Optional[Workflow]:
        """
        Retrieve a workflow from history by ID.

        Args:
            workflow_id: The workflow ID to look up

        Returns:
            The workflow if found in history, None otherwise
        """
        with self._lock:
            return self.workflow_history.get(workflow_id)

    def update_metrics(self, workflow_id: str, metrics: Dict[str, Any]) -> None:
        """
        Update metrics for a specific workflow.

        This method allows external components to provide additional
        metrics data for a workflow.

        Args:
            workflow_id: The workflow ID
            metrics: Dictionary of metric updates
        """
        with self._lock:
            # Update workflow-specific metrics
            if "execution_time" in metrics:
                self.workflow_metrics.add_execution_time(metrics["execution_time"])

            if "user_id" in metrics:
                self.workflow_metrics.increment_user_workflows(str(metrics["user_id"]))

            # Log the update
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "event": "workflow_metrics_updated",
                    "workflow_id": workflow_id,
                    "metrics": metrics
                },
                description="Workflow metrics updated"
            )

    def add_pending_approval(self, workflow: Workflow) -> None:
        """
        Add a workflow to pending approvals.

        Args:
            workflow: The workflow awaiting approval
        """
        with self._lock:
            workflow_id = workflow.id
            self.pending_approvals[workflow_id] = workflow

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "event": "workflow_pending_approval",
                    "workflow_id": workflow_id
                },
                description="Workflow pending approval"
            )

    def get_pending_approval(self, workflow_id: str) -> Optional[Workflow]:
        """
        Retrieve a workflow from pending approvals.

        Args:
            workflow_id: The workflow ID to look up

        Returns:
            The workflow if found in pending approvals, None otherwise
        """
        with self._lock:
            return self.pending_approvals.get(workflow_id)

    def remove_pending_approval(self, workflow_id: str) -> None:
        """
        Remove a workflow from pending approvals.

        Args:
            workflow_id: The workflow ID to remove
        """
        with self._lock:
            if workflow_id in self.pending_approvals:
                del self.pending_approvals[workflow_id]

                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "event": "workflow_approval_removed",
                        "workflow_id": workflow_id
                    },
                    description="Workflow approval removed"
                )

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """
        Get a workflow by ID from any source (active, history, or pending).

        Args:
            workflow_id: The workflow ID to look up

        Returns:
            The workflow if found, None otherwise
        """
        with self._lock:
            # Check active workflows first
            if workflow_id in self.active_workflows:
                return self.active_workflows[workflow_id]

            # Check workflow history
            if workflow_id in self.workflow_history:
                return self.workflow_history[workflow_id]

            # Check pending approvals
            if workflow_id in self.pending_approvals:
                return self.pending_approvals[workflow_id]

            return None

    def get_workflows(
        self,
        include_active: bool = True,
        include_history: bool = True,
        include_pending: bool = True,
        user_id: Optional[str] = None,
        status: Optional[WorkflowStatus] = None,
        limit: int = 100
    ) -> List[Workflow]:
        """
        Get workflows matching specified criteria.

        Args:
            include_active: Include active workflows
            include_history: Include historical workflows
            include_pending: Include pending approval workflows
            user_id: Filter by user ID (if tracked in workflow metadata)
            status: Filter by workflow status
            limit: Maximum number of workflows to return

        Returns:
            List of matching workflows
        """
        with self._lock:
            workflows = []

            # Collect workflows from requested sources
            if include_active:
                workflows.extend(self.active_workflows.values())

            if include_pending:
                workflows.extend(self.pending_approvals.values())

            if include_history:
                workflows.extend(self.workflow_history.values())

            # Apply filters
            if status:
                workflows = [w for w in workflows if w.status == status]

            # Note: user_id filtering is not implemented as workflows are internal
            # implementation details not exposed via API. This parameter exists
            # for potential future use but currently has no effect.
            if user_id:
                pass  # No-op: workflows don't track user_id

            # Sort by creation time (newest first)
            workflows.sort(key=lambda w: w.created_at, reverse=True)

            # Apply limit
            return workflows[:limit]

    def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel a workflow and move it to history.

        Args:
            workflow_id: The workflow ID to cancel

        Returns:
            True if cancelled successfully, False if not found
        """
        with self._lock:
            workflow = None

            # Check if workflow is active
            if workflow_id in self.active_workflows:
                workflow = self.active_workflows[workflow_id]
            elif workflow_id in self.pending_approvals:
                workflow = self.pending_approvals[workflow_id]
                # Remove from pending approvals
                del self.pending_approvals[workflow_id]

            if not workflow:
                return False

            # Update workflow status
            workflow.status = WorkflowStatus.CANCELLED
            workflow.completed_at = datetime.now()

            # Move to history
            self.workflow_history[workflow_id] = workflow
            if workflow_id in self.active_workflows:
                del self.active_workflows[workflow_id]

            # Update metrics
            self.workflow_metrics.increment_cancelled_workflows()

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.WARNING,
                data={
                    "event": "workflow_cancelled",
                    "workflow_id": workflow_id
                },
                description="Workflow cancelled"
            )

            return True

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated workflow metrics.

        Returns:
            Dictionary containing workflow metrics
        """
        with self._lock:
            metrics = self.workflow_metrics.get_summary()

            # Add current counts
            metrics.update({
                "in_progress_workflows": len(self.active_workflows),
                "pending_approval_workflows": len(self.pending_approvals),
            })

            return metrics

    def get_active_workflow_ids(self) -> List[str]:
        """
        Get list of active workflow IDs.

        Returns:
            List of workflow IDs currently active
        """
        with self._lock:
            return list(self.active_workflows.keys())

    def clear_workflow_history(self, older_than_days: int = 30) -> int:
        """
        Clear old workflows from history.

        Args:
            older_than_days: Clear workflows completed more than this many days ago

        Returns:
            Number of workflows cleared
        """
        with self._lock:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            cleared_count = 0

            # Find workflows to clear
            workflows_to_clear = [
                wid
                for wid, w in self.workflow_history.items()
                if w.completed_at and w.completed_at < cutoff_date
            ]

            for workflow_id in workflows_to_clear:
                del self.workflow_history[workflow_id]
                cleared_count += 1

            if cleared_count > 0:
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "event": "workflow_history_cleared",
                        "cleared_count": cleared_count,
                        "older_than_days": older_than_days
                    },
                    description="Workflow history cleared"
                )

            return cleared_count

    def update_workflow_status(self, workflow_id: str, workflow: Workflow) -> None:
        """
        Update a workflow's status in active workflows.

        This is used when workflow executors update workflow state during execution.

        Args:
            workflow_id: The workflow ID
            workflow: The updated workflow object
        """
        with self._lock:
            if workflow_id in self.active_workflows:
                self.active_workflows[workflow_id] = workflow

                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "event": "workflow_status_updated",
                        "workflow_id": workflow_id,
                        "status": workflow.status,
                        "progress": workflow.progress_percent
                    },
                    description="Workflow status updated"
                )
