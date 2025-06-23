"""
MUXI Scheduler SQLAlchemy Models

Database models for the scheduler service using the unified database infrastructure.
Supports both PostgreSQL and SQLite through SQLAlchemy ORM.

Models:
- ScheduledJob: Main table for storing scheduled tasks with execution tracking
"""

import json
from ...utils.datetime_utils import utc_now
from typing import Any, Dict

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.types import TEXT, TypeDecorator

from ..db import Base


class JSONType(TypeDecorator):
    """Custom JSON type that works with both PostgreSQL and SQLite."""

    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            # Already a Python object (e.g., from PostgreSQL JSONB)
            return value
        return json.loads(value)


class ScheduledJob(Base):
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
    user_id = Column(String(255), nullable=False, index=True)
    formation_id = Column(String(255), nullable=False, index=True)

    # Job content
    title = Column(String(500), nullable=False)
    original_prompt = Column(Text, nullable=False)
    execution_prompt = Column(Text, nullable=False)

    # Scheduling configuration
    is_recurring = Column(Boolean, nullable=False, default=True, index=True)
    cron_expression = Column(String(255), nullable=True, index=True)  # NULL for one-time jobs
    scheduled_for = Column(DateTime, nullable=True, index=True)  # Specific datetime for one-time jobs
    exclusion_rules = Column(JSONType, default=list)

    # Status management
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

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
            "formation_id": self.formation_id,
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
