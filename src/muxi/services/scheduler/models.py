"""
MUXI Scheduler SQLAlchemy Models

Database models for the scheduler service using the unified database infrastructure.
Supports both PostgreSQL and SQLite through SQLAlchemy ORM.

Models:
- ScheduledJob: Main table for storing scheduled tasks with execution tracking
"""

import json
from ...utils.datetime_utils import utc_now_naive
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from ..db import Base, AsyncModelMixin
from ...datatypes.json_type import JSONType


class ScheduledJobAudit(Base, AsyncModelMixin):
    """
    Audit trail for scheduled job lifecycle events.

    Tracks when jobs are created, updated, paused, resumed, deleted, or replaced.
    Does not track execution logs - those are handled by observability.
    """

    __tablename__ = "scheduled_job_audit"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Job and user identification
    job_id = Column(String(255), ForeignKey("scheduled_jobs.id"), nullable=False, index=True)
    # Store external_user_id directly as string (not a foreign key)
    user_id = Column(String(255), nullable=False, index=True)  # external_user_id from request

    # Audit information
    action = Column(
        String(50), nullable=False
    )  # created, updated, paused, resumed, deleted, replaced
    timestamp = Column(DateTime, nullable=False, default=utc_now_naive, index=True)
    changes = Column(Text, nullable=True)  # JSON string of what changed
    reason = Column(Text, nullable=True)  # Optional reason for the action

    # Indexes for efficient querying
    __table_args__ = (
        Index("idx_job_audit_job_id", "job_id"),
        Index("idx_job_audit_user_id", "user_id"),
        Index("idx_job_audit_timestamp", "timestamp"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """
        Return a dictionary representation of the audit entry, parsing the `changes` field as JSON if possible.

        Returns:
            dict: Dictionary containing audit entry fields, with `changes`
            parsed as a dictionary if valid JSON, otherwise as a string.
        """
        result = {
            "id": self.id,
            "job_id": self.job_id,
            "user_id": self.user_id,
            "action": self.action,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "reason": self.reason,
        }

        # Parse changes if it's a JSON string
        if self.changes:
            try:
                result["changes"] = json.loads(self.changes)
            except json.JSONDecodeError:
                result["changes"] = self.changes

        return result


class ScheduledJob(Base, AsyncModelMixin):
    """
    Scheduled job model for storing both recurring and one-time AI tasks.

    Supports two job types:
    - Recurring jobs: Use cron expressions for repeated execution
    - One-time jobs: Execute at a specific datetime then complete

    Uses map/reduce pattern for job selection without next_run_at calculations.
    Supports dynamic exclusion rules and comprehensive execution tracking.
    """

    __tablename__ = "scheduled_jobs"

    # Primary key and identification
    id = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Job content
    title = Column(String(500), nullable=False)
    original_prompt = Column(Text, nullable=False)
    execution_prompt = Column(Text, nullable=False)

    # Scheduling configuration
    is_recurring = Column(Boolean, nullable=False, default=True, index=True)
    cron_expression = Column(String(255), nullable=True, index=True)  # NULL for one-time jobs
    scheduled_for = Column(
        DateTime, nullable=True, index=True
    )  # Specific datetime for one-time jobs
    exclusion_rules = Column(JSONType, default=list)

    # Status management
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=utc_now_naive)
    updated_at = Column(DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    # Execution tracking
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String(20), nullable=True)  # 'success' or 'failed'
    last_run_failure_message = Column(Text, nullable=True)

    # Statistics
    total_runs = Column(Integer, nullable=False, default=0)
    total_failures = Column(Integer, nullable=False, default=0)
    consecutive_failures = Column(Integer, nullable=False, default=0)

    # Job metadata for extensibility
    job_metadata = Column(JSONType, default=dict)

    # Indexes for performance
    __table_args__ = (
        Index("idx_scheduled_jobs_user_status", "user_id", "status"),
        Index("idx_scheduled_jobs_active_cron", "status", "cron_expression"),
        Index("idx_scheduled_jobs_last_run", "last_run_at"),
        # New indexes for one-time job support
        Index("idx_scheduled_jobs_onetime_due", "is_recurring", "scheduled_for", "status"),
        Index("idx_scheduled_jobs_type_status", "is_recurring", "status"),
        Index("idx_scheduled_jobs_recurring_active", "is_recurring", "status", "cron_expression"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "original_prompt": self.original_prompt,
            "execution_prompt": self.execution_prompt,
            # Job type and scheduling
            "is_recurring": self.is_recurring,
            "cron_expression": self.cron_expression,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "exclusion_rules": self.exclusion_rules or [],
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_status": self.last_run_status,
            "last_run_failure_message": self.last_run_failure_message,
            "total_runs": self.total_runs,
            "total_failures": self.total_failures,
            "consecutive_failures": self.consecutive_failures,
            "job_metadata": self.job_metadata or {},
        }

    def __repr__(self):
        return f"<ScheduledJob(id='{self.id}', title='{self.title}', status='{self.status}')>"
