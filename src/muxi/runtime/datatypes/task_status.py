"""
Unified Task Status Enumeration

Provides a consolidated TaskStatus enum that serves both parallel workflow
and sequential workflow systems in the MUXI Runtime.

This module resolves the duplicate TaskStatus definitions that previously
existed in parallel.py and workflow.py by providing a single source of truth
for all task execution states.
"""

from enum import Enum


class TaskStatus(Enum):
    """
    Unified task execution status for all MUXI workflow systems.

    This enum consolidates task states from both parallel and sequential
    workflow execution models to provide consistency across the runtime.

    States are organized by execution lifecycle:
    - Initial: PENDING
    - Active: READY, IN_PROGRESS, RUNNING
    - Terminal: COMPLETED, DONE, FAILED, CANCELLED, SKIPPED
    - Special: DEFERRED, REVIEW
    """

    # Initial state - task is created but not yet ready
    PENDING = "pending"

    # Parallel workflow states
    READY = "ready"  # Dependencies satisfied, ready to start
    RUNNING = "running"  # Currently executing (parallel context)
    SKIPPED = "skipped"  # Task was skipped due to conditions

    # Sequential workflow states
    IN_PROGRESS = "in_progress"  # Currently executing (sequential context)
    DEFERRED = "deferred"  # Task postponed for later execution
    REVIEW = "review"  # Task awaiting human review/approval

    # Terminal states (shared across both systems)
    COMPLETED = "completed"  # Successfully finished (parallel term)
    DONE = "done"  # Successfully finished (sequential term)
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Explicitly cancelled

    @classmethod
    def is_terminal_state(cls, status: "TaskStatus") -> bool:
        """
        Check if a status represents a terminal (final) state.

        Args:
            status: TaskStatus to check

        Returns:
            True if the status is terminal (task won't change state again)
        """
        terminal_states = {cls.COMPLETED, cls.DONE, cls.FAILED, cls.CANCELLED, cls.SKIPPED}
        return status in terminal_states

    @classmethod
    def is_active_state(cls, status: "TaskStatus") -> bool:
        """
        Check if a status represents an active execution state.

        Args:
            status: TaskStatus to check

        Returns:
            True if the task is currently being executed
        """
        active_states = {cls.RUNNING, cls.IN_PROGRESS}
        return status in active_states

    @classmethod
    def is_ready_state(cls, status: "TaskStatus") -> bool:
        """
        Check if a status represents readiness for execution.

        Args:
            status: TaskStatus to check

        Returns:
            True if the task is ready to be executed
        """
        ready_states = {cls.READY, cls.PENDING}  # In some contexts, pending tasks can be started
        return status in ready_states

    @classmethod
    def is_success_state(cls, status: "TaskStatus") -> bool:
        """
        Check if a status represents successful completion.

        Args:
            status: TaskStatus to check

        Returns:
            True if the task completed successfully
        """
        success_states = {cls.COMPLETED, cls.DONE}
        return status in success_states
