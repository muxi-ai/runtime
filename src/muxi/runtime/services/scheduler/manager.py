"""
MUXI Scheduler Job Manager - Unified Database Implementation

Complete implementation using the unified database infrastructure.
All methods converted to use SQLAlchemy ORM with cross-database support.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.datetime_utils import utc_now

from sqlalchemy import and_, func
from sqlalchemy.exc import SQLAlchemyError

from .. import observability
from ..db import DatabaseManager
from .models import ScheduledJob
from .validation import SchedulerInputValidator, validate_user_access
from .limits import get_limits_enforcer


class JobManager:
    """
    Database manager for scheduled jobs using unified database infrastructure.

    Provides CRUD operations and execution tracking for scheduled jobs
    with full cross-database compatibility.
    """

    def __init__(self, db_manager: DatabaseManager):
        """Initialize job manager with unified database manager."""
        self.db_manager = db_manager
        self._initialized = False

        observability.observe(
            event_type=observability.SystemEvents.SCHEDULER_MANAGER_INITIALIZED,
            level=observability.EventLevel.INFO,
            data={
                "database_type": self.db_manager.database_type,
                "connection_info": self.db_manager.get_connection_info(),
            },
            description=f"Job manager initialized with {self.db_manager.database_type} database",
        )

    async def initialize(self):
        """Initialize database schema using unified database manager."""
        if self._initialized:
            return

        try:
            from ..db import Base

            self.db_manager.create_tables(Base.metadata)
            self._initialized = True

            observability.observe(
                event_type=observability.SystemEvents.SCHEDULER_DATABASE_INITIALIZED,
                level=observability.EventLevel.INFO,
                data={"database_type": self.db_manager.database_type},
                description=f"Scheduler database schema initialized for {self.db_manager.database_type}",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "database_type": self.db_manager.database_type},
                description=f"Failed to initialize scheduler database: {e}",
            )
            raise

    async def create_job(
        self,
        user_id: str,
        formation_id: str,
        title: str,
        original_prompt: str,
        execution_prompt: str,
        cron_expression: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        is_recurring: bool = True,
        exclusion_rules: List[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new scheduled job (recurring or one-time).
        
        Args:
            user_id: User who created the job
            formation_id: Formation ID
            title: Job title
            original_prompt: Original user prompt
            execution_prompt: Transformed prompt for execution
            cron_expression: Cron expression for recurring jobs (required if is_recurring=True)
            scheduled_for: Specific datetime for one-time jobs (required if is_recurring=False)
            is_recurring: Whether this is a recurring or one-time job
            exclusion_rules: List of exclusion rules
            
        Returns:
            Job ID
            
        Raises:
            ValueError: If input validation fails or limits are exceeded
        """
        await self.initialize()
        
        # SECURITY: Comprehensive input validation
        SchedulerInputValidator.validate_job_creation(
            user_id=user_id,
            formation_id=formation_id,
            title=title,
            original_prompt=original_prompt,
            execution_prompt=execution_prompt,
            cron_expression=cron_expression,
            scheduled_for=scheduled_for,
            is_recurring=is_recurring
        )
        
        # SECURITY: Validate user access to formation
        validate_user_access(user_id, formation_id)
        
        # SECURITY: Check resource limits
        limits_enforcer = get_limits_enforcer()
        await limits_enforcer.check_job_creation_limits(self, user_id)
        await limits_enforcer.check_system_limits(self)
        
        job_id = f"sched_{uuid.uuid4().hex[:16]}"

        try:
            with self.db_manager.get_session() as session:
                job = ScheduledJob(
                    id=job_id,
                    user_id=user_id,
                    formation_id=formation_id,
                    title=title,
                    original_prompt=original_prompt,
                    execution_prompt=execution_prompt,
                    is_recurring=is_recurring,
                    cron_expression=cron_expression,
                    scheduled_for=scheduled_for,
                    exclusion_rules=exclusion_rules or [],
                )
                session.add(job)
                session.commit()

            job_type = "recurring" if is_recurring else "one_time"
            observability.observe(
                event_type=observability.ConversationEvents.SCHEDULED_JOB_CREATED,
                level=observability.EventLevel.INFO,
                data={
                    "job_id": job_id,
                    "user_id": user_id,
                    "job_type": job_type,
                    "database_type": self.db_manager.database_type,
                    "cron_expression": cron_expression,
                    "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
                    "exclusion_rules_count": len(exclusion_rules or []),
                },
                description=f"{job_type.title()} job created: {title}",
            )
            return job_id

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "create_job", "error": str(e), "job_id": job_id},
                description=f"Failed to create scheduled job: {e}",
            )
            raise

    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        """Get all active jobs for map/reduce processing."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                jobs = (
                    session.query(ScheduledJob)
                    .filter(ScheduledJob.status == "ACTIVE")
                    .order_by(ScheduledJob.created_at.asc())
                    .all()
                )

                return [job.to_dict() for job in jobs]

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_active_jobs", "error": str(e)},
                description=f"Failed to get active jobs: {e}",
            )
            raise

    async def get_user_jobs(
        self, user_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all jobs for a specific user."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                query = session.query(ScheduledJob).filter(ScheduledJob.user_id == user_id)

                if status:
                    query = query.filter(ScheduledJob.status == status)

                jobs = query.order_by(ScheduledJob.created_at.desc()).all()
                return [job.to_dict() for job in jobs]

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_user_jobs", "error": str(e), "user_id": user_id},
                description=f"Failed to get user jobs: {e}",
            )
            raise

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific job by ID."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                job = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
                return job.to_dict() if job else None

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_job", "error": str(e), "job_id": job_id},
                description=f"Failed to get job: {e}",
            )
            raise

    async def count_active_jobs(self) -> int:
        """Count total active jobs."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                count = (
                    session.query(func.count(ScheduledJob.id))
                    .filter(ScheduledJob.status == "ACTIVE")
                    .scalar()
                )
                return count or 0

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "count_active_jobs", "error": str(e)},
                description=f"Failed to count active jobs: {e}",
            )
            raise

    async def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                updated = (
                    session.query(ScheduledJob)
                    .filter(and_(ScheduledJob.id == job_id, ScheduledJob.status == "ACTIVE"))
                    .update({"status": "PAUSED"})
                )

                session.commit()
                success = updated > 0

            if success:
                observability.observe(
                    event_type=observability.ConversationEvents.SCHEDULED_JOB_PAUSED,
                    level=observability.EventLevel.INFO,
                    data={"job_id": job_id},
                    description=f"Job paused: {job_id}",
                )
            return success

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "pause_job", "error": str(e), "job_id": job_id},
                description=f"Failed to pause job: {e}",
            )
            raise

    async def resume_job(self, job_id: str) -> bool:
        """Resume a paused scheduled job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                updated = (
                    session.query(ScheduledJob)
                    .filter(and_(ScheduledJob.id == job_id, ScheduledJob.status == "PAUSED"))
                    .update({"status": "ACTIVE", "consecutive_failures": 0})
                )

                session.commit()
                success = updated > 0

            if success:
                observability.observe(
                    event_type=observability.ConversationEvents.SCHEDULED_JOB_RESUMED,
                    level=observability.EventLevel.INFO,
                    data={"job_id": job_id},
                    description=f"Job resumed: {job_id}",
                )
            return success

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "resume_job", "error": str(e), "job_id": job_id},
                description=f"Failed to resume job: {e}",
            )
            raise

    async def complete_onetime_job(self, job_id: str) -> bool:
        """
        Mark a one-time job as completed.
        
        Args:
            job_id: ID of the job to complete
            
        Returns:
            True if job was successfully marked as completed, False otherwise
        """
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                updated = (
                    session.query(ScheduledJob)
                    .filter(and_(
                        ScheduledJob.id == job_id, 
                        ScheduledJob.is_recurring == False,
                        ScheduledJob.status == "ACTIVE"
                    ))
                    .update({
                        "status": "COMPLETED", 
                        "updated_at": utc_now()
                    })
                )

                session.commit()
                success = updated > 0

            if success:
                observability.observe(
                    event_type=observability.ConversationEvents.ONETIME_JOB_MARKED_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={"job_id": job_id},
                    description=f"One-time job marked as completed: {job_id}",
                )
            else:
                observability.observe(
                    event_type=observability.ErrorEvents.ONETIME_JOB_COMPLETION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"job_id": job_id, "reason": "Job not found or not a one-time job"},
                    description=f"Failed to mark one-time job as completed: {job_id}",
                )
                
            return success

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "complete_onetime_job", "error": str(e), "job_id": job_id},
                description=f"Failed to complete one-time job: {e}",
            )
            raise

    async def delete_job(self, job_id: str) -> bool:
        """Delete a scheduled job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                deleted = session.query(ScheduledJob).filter(ScheduledJob.id == job_id).delete()

                session.commit()
                success = deleted > 0

            if success:
                observability.observe(
                    event_type=observability.ConversationEvents.SCHEDULED_JOB_DELETED,
                    level=observability.EventLevel.INFO,
                    data={"job_id": job_id},
                    description=f"Job deleted: {job_id}",
                )
            return success

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "delete_job", "error": str(e), "job_id": job_id},
                description=f"Failed to delete job: {e}",
            )
            raise

    async def mark_job_execution_start(self, job_id: str):
        """Mark the start of job execution."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                session.query(ScheduledJob).filter(ScheduledJob.id == job_id).update(
                    {
                        "last_run_at": utc_now(),
                        "last_run_status": None,
                        "last_run_failure_message": None,
                    }
                )
                session.commit()

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "mark_execution_start", "error": str(e), "job_id": job_id},
                description=f"Failed to mark execution start: {e}",
            )
            raise

    async def mark_job_execution_success(self, job_id: str, response: str = None):
        """Mark job execution as successful."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                session.query(ScheduledJob).filter(ScheduledJob.id == job_id).update(
                    {
                        "last_run_status": "success",
                        "last_run_failure_message": None,
                        "total_runs": ScheduledJob.total_runs + 1,
                        "consecutive_failures": 0,
                        "updated_at": utc_now(),
                    }
                )
                session.commit()

            observability.observe(
                event_type=observability.ConversationEvents.SCHEDULED_JOB_EXECUTION_TRACKED,
                level=observability.EventLevel.INFO,
                data={
                    "job_id": job_id,
                    "status": "success",
                    "response_length": len(response) if response else 0,
                },
                description=f"Job execution success tracked: {job_id}",
            )

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "mark_execution_success", "error": str(e), "job_id": job_id},
                description=f"Failed to mark execution success: {e}",
            )
            raise

    async def mark_job_execution_failure(self, job_id: str, error_message: str):
        """Mark job execution as failed."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                session.query(ScheduledJob).filter(ScheduledJob.id == job_id).update(
                    {
                        "last_run_status": "failed",
                        "last_run_failure_message": error_message,
                        "total_runs": ScheduledJob.total_runs + 1,
                        "total_failures": ScheduledJob.total_failures + 1,
                        "consecutive_failures": ScheduledJob.consecutive_failures + 1,
                        "updated_at": utc_now(),
                    }
                )
                session.commit()

            observability.observe(
                event_type=observability.ConversationEvents.SCHEDULED_JOB_EXECUTION_TRACKED,
                level=observability.EventLevel.ERROR,
                data={"job_id": job_id, "status": "failed", "error_message": error_message},
                description=f"Job execution failure tracked: {job_id}",
            )

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "mark_execution_failure", "error": str(e), "job_id": job_id},
                description=f"Failed to mark execution failure: {e}",
            )
            raise

    async def get_consecutive_failures(self, job_id: str) -> int:
        """Get consecutive failure count for a job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                job = (
                    session.query(ScheduledJob.consecutive_failures)
                    .filter(ScheduledJob.id == job_id)
                    .first()
                )
                return job.consecutive_failures if job else 0

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_consecutive_failures", "error": str(e), "job_id": job_id},
                description=f"Failed to get consecutive failures: {e}",
            )
            raise

    async def update_job_metadata(self, job_id: str, metadata: Dict[str, Any]) -> bool:
        """Update job metadata."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                updated = (
                    session.query(ScheduledJob)
                    .filter(ScheduledJob.id == job_id)
                    .update({"metadata": metadata, "updated_at": utc_now()})
                )

                session.commit()
                return updated > 0

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "update_metadata", "error": str(e), "job_id": job_id},
                description=f"Failed to update job metadata: {e}",
            )
            raise

    async def get_job_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get job statistics."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                query = session.query(
                    func.count(ScheduledJob.id).label("total_jobs"),
                    func.sum(ScheduledJob.total_runs).label("total_runs"),
                    func.sum(ScheduledJob.total_failures).label("total_failures"),
                )

                if user_id:
                    query = query.filter(ScheduledJob.user_id == user_id)

                result = query.first()

                # Get status counts
                status_query = session.query(
                    ScheduledJob.status, func.count(ScheduledJob.id).label("count")
                ).group_by(ScheduledJob.status)

                if user_id:
                    status_query = status_query.filter(ScheduledJob.user_id == user_id)

                status_counts = {status: count for status, count in status_query.all()}

                total_runs = result.total_runs or 0
                total_failures = result.total_failures or 0

                return {
                    "total_jobs": result.total_jobs or 0,
                    "active_jobs": status_counts.get("ACTIVE", 0),
                    "paused_jobs": status_counts.get("PAUSED", 0),
                    "total_runs": total_runs,
                    "total_failures": total_failures,
                    "success_rate": (total_runs - total_failures) / total_runs
                    if total_runs > 0
                    else 0,
                }

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_statistics", "error": str(e), "user_id": user_id},
                description=f"Failed to get job statistics: {e}",
            )
            raise
    
    async def get_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all jobs for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of job dictionaries
        """
        await self.initialize()
        
        try:
            with self.db_manager.get_session() as session:
                jobs = (
                    session.query(ScheduledJob)
                    .filter(ScheduledJob.user_id == user_id)
                    .order_by(ScheduledJob.created_at.desc())
                    .all()
                )
                
                return [job.to_dict() for job in jobs]
                
        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_user_jobs", "error": str(e), "user_id": user_id},
                description=f"Failed to get user jobs: {e}",
            )
            raise
