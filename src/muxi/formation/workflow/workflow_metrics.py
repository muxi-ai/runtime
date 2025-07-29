"""
Workflow Metrics Module

This module provides metrics tracking for workflow execution,
including success rates, execution times, and user-specific metrics.
"""

from typing import Dict, Any
import threading


class WorkflowMetrics:
    """
    Tracks and manages workflow execution metrics.

    This class provides thread-safe metrics collection for workflow
    execution, including counts, success rates, execution times,
    and per-user statistics.

    Attributes:
        total_workflows: Total number of workflows created
        completed_workflows: Number of successfully completed workflows
        failed_workflows: Number of failed workflows
        cancelled_workflows: Number of cancelled workflows
        total_execution_time: Cumulative execution time in seconds
        workflow_count_by_user: Workflow count per user
        _lock: Thread lock for concurrent access
    """

    def __init__(self):
        """Initialize metrics with zero values."""
        self.total_workflows: int = 0
        self.completed_workflows: int = 0
        self.failed_workflows: int = 0
        self.cancelled_workflows: int = 0
        self.total_execution_time: float = 0.0
        self.workflow_count_by_user: Dict[str, int] = {}

        # Thread safety
        self._lock = threading.Lock()

    def increment_total_workflows(self) -> None:
        """Increment the total workflow count."""
        with self._lock:
            self.total_workflows += 1

    def increment_completed_workflows(self) -> None:
        """Increment the completed workflow count."""
        with self._lock:
            self.completed_workflows += 1

    def increment_failed_workflows(self) -> None:
        """Increment the failed workflow count."""
        with self._lock:
            self.failed_workflows += 1

    def increment_cancelled_workflows(self) -> None:
        """Increment the cancelled workflow count."""
        with self._lock:
            self.cancelled_workflows += 1

    def add_execution_time(self, execution_time: float) -> None:
        """
        Add execution time to the total.

        Args:
            execution_time: Execution time in seconds to add
        """
        with self._lock:
            self.total_execution_time += execution_time

    def increment_user_workflows(self, user_id: str) -> None:
        """
        Increment workflow count for a specific user.

        Args:
            user_id: The user ID to increment count for
        """
        with self._lock:
            if user_id not in self.workflow_count_by_user:
                self.workflow_count_by_user[user_id] = 0
            self.workflow_count_by_user[user_id] += 1

    def get_success_rate(self) -> float:
        """
        Calculate the workflow success rate.

        Returns:
            Success rate as a percentage (0-100)
        """
        with self._lock:
            if self.total_workflows == 0:
                return 0.0

            # Success rate = completed / (completed + failed)
            # Cancelled workflows are not counted in success rate
            total_finished = self.completed_workflows + self.failed_workflows
            if total_finished == 0:
                return 0.0

            return (self.completed_workflows / total_finished) * 100.0

    def get_average_execution_time(self) -> float:
        """
        Calculate the average workflow execution time.

        Returns:
            Average execution time in seconds
        """
        with self._lock:
            completed_or_failed = self.completed_workflows + self.failed_workflows
            if completed_or_failed == 0:
                return 0.0

            return self.total_execution_time / completed_or_failed

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all metrics.

        Returns:
            Dictionary containing all metric values
        """
        with self._lock:
            return {
                "total_workflows": self.total_workflows,
                "completed_workflows": self.completed_workflows,
                "failed_workflows": self.failed_workflows,
                "cancelled_workflows": self.cancelled_workflows,
                "success_rate": round(self.get_success_rate(), 2),
                "average_execution_time_seconds": round(self.get_average_execution_time(), 2),
                "workflow_count_by_user": dict(self.workflow_count_by_user),
            }

    def reset(self) -> None:
        """Reset all metrics to initial values."""
        with self._lock:
            self.total_workflows = 0
            self.completed_workflows = 0
            self.failed_workflows = 0
            self.cancelled_workflows = 0
            self.total_execution_time = 0.0
            self.workflow_count_by_user.clear()

    def merge(self, other: 'WorkflowMetrics') -> None:
        """
        Merge metrics from another WorkflowMetrics instance.

        This is useful for aggregating metrics from multiple sources.

        This method avoids potential deadlocks by copying data from the
        other instance outside of any locks, then updating self atomically.

        Args:
            other: Another WorkflowMetrics instance to merge from
        """
        # First, copy data from the other instance while holding only its lock
        with other._lock:
            other_total_workflows = other.total_workflows
            other_completed_workflows = other.completed_workflows
            other_failed_workflows = other.failed_workflows
            other_cancelled_workflows = other.cancelled_workflows
            other_total_execution_time = other.total_execution_time
            other_workflow_count_by_user = other.workflow_count_by_user.copy()

        # Now update self with the copied data while holding only self's lock
        with self._lock:
            self.total_workflows += other_total_workflows
            self.completed_workflows += other_completed_workflows
            self.failed_workflows += other_failed_workflows
            self.cancelled_workflows += other_cancelled_workflows
            self.total_execution_time += other_total_execution_time

            # Merge user counts
            for user_id, count in other_workflow_count_by_user.items():
                if user_id in self.workflow_count_by_user:
                    self.workflow_count_by_user[user_id] += count
                else:
                    self.workflow_count_by_user[user_id] = count

    def get_user_metrics(self, user_id: str) -> Dict[str, Any]:
        """
        Get metrics for a specific user.

        Args:
            user_id: The user ID to get metrics for

        Returns:
            Dictionary containing user-specific metrics
        """
        with self._lock:
            workflow_count = self.workflow_count_by_user.get(user_id, 0)

            return {
                "user_id": user_id,
                "workflow_count": workflow_count,
                "percentage_of_total": (
                    round((workflow_count / self.total_workflows) * 100, 2)
                    if self.total_workflows > 0
                    else 0.0
                ),
            }

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status based on metrics.

        Returns:
            Dictionary containing health indicators
        """
        with self._lock:
            success_rate = self.get_success_rate()
            avg_execution_time = self.get_average_execution_time()

            # Define health thresholds
            health_status = "healthy"
            issues = []

            if success_rate < 80:
                health_status = "degraded"
                issues.append(f"Low success rate: {success_rate:.1f}%")

            if success_rate < 50:
                health_status = "unhealthy"

            if avg_execution_time > 300:  # 5 minutes
                if health_status == "healthy":
                    health_status = "degraded"
                issues.append(f"High average execution time: {avg_execution_time:.1f}s")

            failure_rate = (
                (self.failed_workflows / self.total_workflows * 100)
                if self.total_workflows > 0
                else 0
            )

            if failure_rate > 20:
                if health_status == "healthy":
                    health_status = "degraded"
                issues.append(f"High failure rate: {failure_rate:.1f}%")

            return {
                "status": health_status,
                "success_rate": round(success_rate, 2),
                "average_execution_time": round(avg_execution_time, 2),
                "failure_rate": round(failure_rate, 2),
                "issues": issues,
            }
