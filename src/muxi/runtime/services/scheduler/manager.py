"""
MUXI Scheduler Job Manager - Unified Database Implementation

Complete implementation using the unified database infrastructure.
All methods converted to use SQLAlchemy ORM with cross-database support.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ...utils.datetime_utils import utc_now
from ...utils.id_generator import generate_nanoid

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from .. import observability
from ..db import DatabaseManager
from ..llm import LLM
from .models import ScheduledJob, ScheduledJobAudit
from .validation import SchedulerInputValidator
from .limits import get_limits_enforcer
from ..memory.long_term import User  # Import User model for formation isolation


class JobManager:
    """
    Database manager for scheduled jobs using unified database infrastructure.

    Provides CRUD operations and execution tracking for scheduled jobs
    with full cross-database compatibility.
    """

    def __init__(self, db_manager: DatabaseManager, formation_id: str = None):
        """Initialize job manager with unified database manager."""
        self.db_manager = db_manager
        self._initialized = False
        self.formation_id = formation_id or "default-formation"

        pass  # REMOVED: init-phase observe() call

    def _resolve_user_id_sync(self, external_user_id: str) -> int:
        """
        Resolve external user identifier to internal user ID.

        For scheduler, we always resolve synchronously since jobs are managed outside request context.
        This uses the user_identifiers table for multi-identity support.

        Returns:
            int: Internal user ID for database operations
        """
        with self.db_manager.get_session() as session:
            from ...services.memory.long_term import UserIdentifier

            # Query user_identifiers table to find user
            result = session.execute(
                select(UserIdentifier.user_id).where(
                    UserIdentifier.identifier == external_user_id,
                    UserIdentifier.formation_id == self.formation_id,
                )
            )
            user_id = result.scalar_one_or_none()

            if user_id:
                return user_id

            # User doesn't exist - create new user + identifier
            from ...utils.id_generator import get_default_nanoid
            from sqlalchemy.exc import IntegrityError

            new_user = User(
                public_id=get_default_nanoid()(),
                formation_id=self.formation_id,
            )

            try:
                session.add(new_user)
                session.flush()

                # Create identifier
                new_identifier = UserIdentifier(
                    user_id=new_user.id,
                    identifier=external_user_id,
                    formation_id=self.formation_id,
                )
                session.add(new_identifier)
                session.commit()

                return new_user.id
            except IntegrityError:
                # Handle concurrent creation - retry lookup
                session.rollback()
                result = session.execute(
                    select(UserIdentifier.user_id).where(
                        UserIdentifier.identifier == external_user_id,
                        UserIdentifier.formation_id == self.formation_id,
                    )
                )
                user_id = result.scalar_one_or_none()
                if user_id:
                    return user_id
                raise ValueError(
                    f"Failed to resolve user after concurrent creation: {external_user_id}"
                )

    # DEPRECATED: Old method removed - use _resolve_user_id_sync() instead
    # This method queried external_user_id column which no longer exists.
    # See _resolve_user_id_sync() for the new multi-identity approach.

    async def initialize(self):
        """Initialize scheduler service. Tables are now created centrally during formation init."""
        if self._initialized:
            return

        # Tables are now created centrally in formation initialization
        # Just mark as initialized
        self._initialized = True

        pass  # REMOVED: init-phase observe() call

    async def create_job(
        self,
        user_id: str,
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
            user_id: External user ID who created the job
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
            formation_id=self.formation_id,  # Use formation_id from manager
            title=title,
            original_prompt=original_prompt,
            execution_prompt=execution_prompt,
            cron_expression=cron_expression,
            scheduled_for=scheduled_for,
            is_recurring=is_recurring,
        )

        # SECURITY: Check resource limits
        limits_enforcer = get_limits_enforcer()
        await limits_enforcer.check_job_creation_limits(self, user_id)
        await limits_enforcer.check_system_limits(self)

        job_id = f"job_{generate_nanoid(size=16)}"

        try:
            # Resolve user identifier to internal user ID (multi-identity support)
            internal_user_id = self._resolve_user_id_sync(user_id)

            with self.db_manager.get_session() as session:
                job = ScheduledJob(
                    id=job_id,
                    user_id=internal_user_id,  # Use internal user ID
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
            # Audit the creation
            await self._audit_job_action(
                job_id=job_id,
                user_id=user_id,
                action="created",
                changes={
                    "title": title,
                    "prompt": original_prompt,
                    "type": job_type,
                    "schedule": cron_expression
                    or (scheduled_for.isoformat() if scheduled_for else None),
                },
            )

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
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(
                        ScheduledJob.status == "ACTIVE",
                        User.formation_id == self.formation_id,
                    )
                    .order_by(ScheduledJob.created_at.asc())
                    .all()
                )

                # Build result with external_user_id from User table
                result = []
                for job in jobs:
                    job_dict = job.to_dict()
                    result.append(job_dict)

                return result

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
            # Resolve user identifier to internal user ID (multi-identity support)
            internal_user_id = self._resolve_user_id_sync(user_id)

            with self.db_manager.get_session() as session:
                query = session.query(ScheduledJob).filter(
                    ScheduledJob.user_id == internal_user_id,
                )

                if status:
                    query = query.filter(ScheduledJob.status == status)

                jobs = query.order_by(ScheduledJob.created_at.desc()).all()

                # Build result
                result = [job.to_dict() for job in jobs]
                return result

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_user_jobs", "error": str(e), "user_id": user_id},
                description=f"Failed to get user jobs: {e}",
            )
            raise

    async def get_all_jobs(
        self,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        is_recurring: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get all jobs with optional filters."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                query = (
                    session.query(ScheduledJob)
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(User.formation_id == self.formation_id)
                )

                if status:
                    query = query.filter(ScheduledJob.status == status)

                if user_id:
                    # Resolve user identifier to internal user ID
                    internal_user_id = self._resolve_user_id_sync(user_id)
                    query = query.filter(ScheduledJob.user_id == internal_user_id)

                if is_recurring is not None:
                    query = query.filter(ScheduledJob.is_recurring == is_recurring)

                query = query.order_by(ScheduledJob.created_at.desc())

                if offset:
                    query = query.offset(offset)

                if limit:
                    query = query.limit(limit)

                jobs = query.all()

                # Build result with external_user_id from User table
                result = []
                for job in jobs:
                    job_dict = job.to_dict()
                    result.append(job_dict)

                return result

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "get_all_jobs",
                    "error": str(e),
                    "filters": {
                        "status": status,
                        "user_id": user_id,
                        "is_recurring": is_recurring,
                    },
                },
                description=f"Failed to get all jobs: {e}",
            )
            raise

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific job by ID."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                job = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
                    .first()
                )
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
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(
                        ScheduledJob.status == "ACTIVE",
                        User.formation_id == self.formation_id,
                    )
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

    async def pause_job(self, job_id: str, user_id: str, reason: Optional[str] = None) -> bool:
        """Pause a scheduled job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(
                        ScheduledJob.id == job_id,
                        ScheduledJob.status == "ACTIVE",
                        User.formation_id == self.formation_id,
                    )
                    .first()
                )

                if job:
                    job.status = "PAUSED"
                    session.commit()
                    success = True
                else:
                    success = False

            if success:
                # Audit the pause action
                await self._audit_job_action(
                    job_id=job_id, user_id=user_id, action="paused", reason=reason
                )

                observability.observe(
                    event_type=observability.ConversationEvents.SCHEDULED_JOB_EXECUTION_TRACKED,
                    level=observability.EventLevel.INFO,
                    data={
                        "job_id": job_id,
                        "action": "paused",
                        "user_id": user_id,
                        "status": "paused",
                    },
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

    async def resume_job(self, job_id: str, user_id: str) -> bool:
        """Resume a paused scheduled job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(
                        ScheduledJob.id == job_id,
                        ScheduledJob.status == "PAUSED",
                        User.formation_id == self.formation_id,
                    )
                    .first()
                )

                if job:
                    job.status = "ACTIVE"
                    job.consecutive_failures = 0
                    session.commit()
                    success = True
                else:
                    success = False

            if success:
                # Audit the resume action
                await self._audit_job_action(job_id=job_id, user_id=user_id, action="resumed")

                observability.observe(
                    event_type=observability.ConversationEvents.SCHEDULED_JOB_EXECUTION_TRACKED,
                    level=observability.EventLevel.INFO,
                    data={
                        "job_id": job_id,
                        "action": "resumed",
                        "user_id": user_id,
                        "status": "resumed",
                    },
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
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(
                        ScheduledJob.id == job_id,
                        ScheduledJob.is_recurring.is_(False),
                        ScheduledJob.status == "ACTIVE",
                        User.formation_id == self.formation_id,
                    )
                    .first()
                )

                if job:
                    job.status = "COMPLETED"
                    job.updated_at = utc_now()
                    session.commit()
                    success = True
                else:
                    success = False

            if success:
                observability.observe(
                    event_type=observability.ConversationEvents.ONETIME_JOB_MARKED_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={"job_id": job_id},
                    description=f"One-time job marked as completed: {job_id}",
                )
            else:
                observability.observe(
                    event_type=observability.ErrorEvents.RESOURCE_NOT_FOUND,
                    level=observability.EventLevel.WARNING,
                    data={"job_id": job_id, "reason": "Job not found or not a one-time job"},
                    description=f"One-time job not found or already completed: {job_id}",
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

    async def delete_job(self, job_id: str, user_id: str, reason: Optional[str] = None) -> bool:
        """Delete a scheduled job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
                    .first()
                )

                if job:
                    session.delete(job)
                    session.commit()
                    success = True
                else:
                    success = False

            if success:
                # Audit the deletion
                await self._audit_job_action(
                    job_id=job_id, user_id=user_id, action="deleted", reason=reason
                )

                observability.observe(
                    event_type=observability.ConversationEvents.SCHEDULED_JOB_EXECUTION_TRACKED,
                    level=observability.EventLevel.INFO,
                    data={"job_id": job_id, "action": "deleted", "user_id": user_id},
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
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
                    .first()
                )

                if job:
                    job.last_run_at = utc_now()
                    job.last_run_status = None
                    job.last_run_failure_message = None
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
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
                    .first()
                )

                if job:
                    job.last_run_status = "success"
                    job.last_run_failure_message = None
                    job.total_runs += 1
                    job.consecutive_failures = 0
                    job.updated_at = utc_now()
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
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
                    .first()
                )

                if job:
                    job.last_run_status = "failed"
                    job.last_run_failure_message = error_message[
                        :1000
                    ]  # Truncate to prevent overflow
                    job.total_runs += 1
                    job.total_failures += 1
                    job.consecutive_failures += 1
                    job.updated_at = utc_now()
                session.commit()

            observability.observe(
                event_type=observability.ConversationEvents.SCHEDULED_JOB_EXECUTION_TRACKED,
                level=observability.EventLevel.ERROR,
                data={
                    "job_id": job_id,
                    "status": "failed",
                    "error_message": error_message,
                },
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
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
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
                # First check if job exists and belongs to formation
                job = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.id == job_id,
                    )
                    .first()
                )

                if job:
                    job.job_metadata = metadata
                    job.updated_at = utc_now()
                    session.commit()
                    return True
                else:
                    return False

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
                    "success_rate": (
                        (total_runs - total_failures) / total_runs if total_runs > 0 else 0
                    ),
                }

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_statistics", "error": str(e), "user_id": user_id},
                description=f"Failed to get job statistics: {e}",
            )
            raise

    async def _audit_job_action(
        self,
        job_id: str,
        user_id: str,
        action: str,
        changes: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Record job lifecycle action in audit trail."""
        try:
            with self.db_manager.get_session() as session:
                audit_entry = ScheduledJobAudit(
                    job_id=job_id,
                    user_id=user_id,
                    action=action,
                    changes=json.dumps(changes) if changes else None,
                    reason=reason,
                )
                session.add(audit_entry)
                session.commit()

        except SQLAlchemyError as e:
            # Log but don't fail the main operation
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "operation": "audit_job_action",
                    "error": str(e),
                    "job_id": job_id,
                    "action": action,
                },
                description=f"Failed to audit job action: {e}",
            )

    async def get_job_audit_trail(self, job_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for a specific job."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                audit_entries = (
                    session.query(ScheduledJobAudit)
                    .filter(ScheduledJobAudit.job_id == job_id)
                    .order_by(ScheduledJobAudit.timestamp.desc())
                    .all()
                )

                return [entry.to_dict() for entry in audit_entries]

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_job_audit_trail", "error": str(e), "job_id": job_id},
                description=f"Failed to get job audit trail: {e}",
            )
            raise

    async def get_user_audit_trail(
        self, user_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get audit trail for all jobs belonging to a specific user."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                query = (
                    session.query(ScheduledJobAudit)
                    .filter(ScheduledJobAudit.user_id == user_id)
                    .order_by(ScheduledJobAudit.timestamp.desc())
                )

                if limit:
                    query = query.limit(limit)

                audit_entries = query.all()
                return [entry.to_dict() for entry in audit_entries]

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={"operation": "get_user_audit_trail", "error": str(e), "user_id": user_id},
                description=f"Failed to get user audit trail: {e}",
            )
            raise

    async def get_recent_audit_trail(
        self, limit: int = 100, user_id: Optional[str] = None, action: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent audit trail entries with optional filters."""
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                query = session.query(ScheduledJobAudit)

                if user_id:
                    query = query.filter(ScheduledJobAudit.user_id == user_id)

                if action:
                    query = query.filter(ScheduledJobAudit.action == action)

                audit_entries = (
                    query.order_by(ScheduledJobAudit.timestamp.desc()).limit(limit).all()
                )

                return [entry.to_dict() for entry in audit_entries]

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "get_recent_audit_trail",
                    "error": str(e),
                    "filters": {"user_id": user_id, "action": action},
                },
                description=f"Failed to get recent audit trail: {e}",
            )
            raise

    # Batch processing methods for performance optimization

    async def get_active_jobs_count(self) -> int:
        """
        Get total count of active jobs without loading them.

        Returns:
            Total number of active jobs
        """
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
                data={"operation": "get_active_jobs_count", "error": str(e)},
                description=f"Failed to count active jobs: {e}",
            )
            raise

    async def get_active_jobs_batch(self, offset: int, limit: int) -> List[Dict[str, Any]]:
        """
        Get a batch of active jobs for processing.

        Args:
            offset: Number of jobs to skip
            limit: Maximum number of jobs to return

        Returns:
            List of job dictionaries
        """
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                # Join with User table to get external_user_id
                jobs = (
                    session.query(ScheduledJob)
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(ScheduledJob.status == "ACTIVE")
                    .order_by(ScheduledJob.created_at)
                    .offset(offset)
                    .limit(limit)
                    .all()
                )

                # Build result with external_user_id from User table
                result = []
                for job in jobs:
                    job_dict = job.to_dict()
                    result.append(job_dict)

                return result

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "get_active_jobs_batch",
                    "error": str(e),
                    "offset": offset,
                    "limit": limit,
                },
                description=f"Failed to get active jobs batch: {e}",
            )
            raise

    async def cleanup_old_jobs_batch(self, retention_days: int, offset: int, limit: int) -> int:
        """
        Clean up old completed jobs in batches.

        Args:
            retention_days: Number of days to retain completed jobs
            offset: Number of jobs to skip
            limit: Maximum number of jobs to process

        Returns:
            Number of jobs deleted
        """
        await self.initialize()

        try:
            with self.db_manager.get_session() as session:
                cutoff_date = utc_now() - timedelta(days=retention_days)

                # Get old completed jobs
                old_jobs = (
                    session.query(ScheduledJob)
                    .join(User, ScheduledJob.user_id == User.id)
                    .filter(
                        ScheduledJob.status.in_(["COMPLETED", "FAILED"]),
                        ScheduledJob.last_run_at < cutoff_date,
                        User.formation_id == self.formation_id,
                    )
                    .offset(offset)
                    .limit(limit)
                    .all()
                )

                # Delete jobs
                deleted_count = 0
                for job in old_jobs:
                    session.delete(job)
                    deleted_count += 1

                session.commit()

                if deleted_count > 0:
                    observability.observe(
                        event_type=observability.SystemEvents.SCHEDULER_CLEANUP_BATCH,
                        level=observability.EventLevel.INFO,
                        data={
                            "deleted_count": deleted_count,
                            "retention_days": retention_days,
                            "batch_offset": offset,
                        },
                        description=f"Cleaned up {deleted_count} old jobs in batch",
                    )

                return deleted_count

        except SQLAlchemyError as e:
            observability.observe(
                event_type=observability.ErrorEvents.DATABASE_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "cleanup_old_jobs_batch",
                    "error": str(e),
                    "retention_days": retention_days,
                },
                description=f"Failed to cleanup old jobs: {e}",
            )
            raise

    async def update_or_replace_job(
        self,
        job_id: str,
        user_id: str,
        new_prompt: Optional[str] = None,
        new_title: Optional[str] = None,
        new_schedule: Optional[str] = None,
        **kwargs,
    ) -> Tuple[str, str]:
        """
        Update a job or replace it if the prompt changed significantly.

        Returns:
            Tuple of (job_id, action) where action is 'updated' or 'replaced'
        """
        await self.initialize()

        if new_prompt:
            # Get the current job
            current_job = await self.get_job(job_id)
            if not current_job:
                raise ValueError(f"Job {job_id} not found")

            # Check if this is a significant change
            if await self._is_significant_prompt_change(current_job["original_prompt"], new_prompt):
                # This is a different task - replace the job
                # 1. Create new job with same schedule but new prompt
                new_job_id = await self.create_job(
                    user_id=user_id,
                    title=new_title or f"Updated: {current_job['title']}",
                    original_prompt=new_prompt,
                    execution_prompt=new_prompt,  # Will be rewritten by the rewriter
                    cron_expression=new_schedule or current_job.get("cron_expression"),
                    scheduled_for=(
                        current_job.get("scheduled_for")
                        if not current_job["is_recurring"]
                        else None
                    ),
                    is_recurring=current_job["is_recurring"],
                    exclusion_rules=current_job.get("exclusion_rules", []),
                )

                # 2. Delete the old job
                await self.delete_job(job_id, user_id, reason="Replaced by new task")

                # 3. Audit the replacement
                await self._audit_job_action(
                    job_id,
                    user_id,
                    "replaced",
                    changes={"replaced_by": new_job_id, "reason": "significant_prompt_change"},
                    reason=f"Task changed from '{current_job['original_prompt']}' to '{new_prompt}'",
                )

                return (new_job_id, "replaced")

        # Otherwise, do a normal update
        # Resolve user identifier to internal user ID (multi-identity support)
        internal_user_id = self._resolve_user_id_sync(user_id)

        with self.db_manager.get_session() as session:

            job = (
                session.query(ScheduledJob)
                .filter(
                    ScheduledJob.id == job_id,
                )
                .first()
            )
            if not job:
                raise ValueError(f"Job {job_id} not found")

            # Validate user ownership
            if job.user_id != internal_user_id:
                raise ValueError(f"User {user_id} does not have permission to update job {job_id}")

            # Build update dict
            update_fields = {}
            changes = {}

            if new_title:
                SchedulerInputValidator.validate_title(new_title)
                update_fields["title"] = new_title
                changes["title"] = {"old": job.title, "new": new_title}

            if new_prompt:
                SchedulerInputValidator.validate_prompt(new_prompt, "new_prompt")
                update_fields["original_prompt"] = new_prompt
                update_fields["execution_prompt"] = new_prompt
                changes["prompt"] = {
                    "old": job.original_prompt[:50] + "...",
                    "new": new_prompt[:50] + "...",
                }

            if new_schedule:
                if job.is_recurring:
                    SchedulerInputValidator.validate_cron_expression(new_schedule)
                    update_fields["cron_expression"] = new_schedule
                    changes["schedule"] = {"old": job.cron_expression, "new": new_schedule}
                else:
                    # Parse datetime for one-time jobs
                    from dateutil import parser as date_parser
                    from pytz import UTC

                    scheduled_datetime = date_parser.parse(new_schedule)
                    if scheduled_datetime.tzinfo is None:
                        scheduled_datetime = scheduled_datetime.replace(tzinfo=UTC)
                    if scheduled_datetime <= utc_now():
                        raise ValueError("Scheduled time must be in the future")
                    update_fields["scheduled_for"] = scheduled_datetime
                    changes["schedule"] = {
                        "old": job.scheduled_for.isoformat() if job.scheduled_for else None,
                        "new": scheduled_datetime.isoformat(),
                    }

            # Handle additional kwargs
            if "exclusion_rules" in kwargs:
                update_fields["exclusion_rules"] = kwargs["exclusion_rules"]
                changes["exclusion_rules"] = "updated"

            if not update_fields:
                return (job_id, "unchanged")

            # Apply updates
            update_fields["updated_at"] = utc_now()
            for field, value in update_fields.items():
                setattr(job, field, value)
            session.commit()

            # Audit the update
            await self._audit_job_action(
                job_id=job_id,
                user_id=user_id,
                action="updated",
                changes=changes,
                reason=f"Job updated with {len(changes)} changes",
            )

            observability.observe(
                event_type=observability.ConversationEvents.SCHEDULED_JOB_UPDATED,
                level=observability.EventLevel.INFO,
                data={
                    "job_id": job_id,
                    "user_id": user_id,
                    "changes": changes,
                    "fields_updated": list(update_fields.keys()),
                },
                description=f"Job {job_id} updated successfully",
            )

            return (job_id, "updated")

    async def _is_significant_prompt_change(self, old_prompt: str, new_prompt: str) -> bool:
        """
        Determine if a prompt change represents a fundamentally different task.
        Uses LLM to understand semantic similarity across languages.

        Examples of significant changes:
        - "check my email" -> "send me a text"
        - "generate a report" -> "backup my files"
        - "每天检查邮件" -> "每天发送报告" (Chinese: check email -> send report)

        Examples of minor changes:
        - "check my email" -> "check my emails"
        - "send daily report" -> "send a daily report"
        - "check email" -> "verificar correo" (English -> Spanish, same task)
        """
        # Quick exact match check
        if old_prompt.strip().lower() == new_prompt.strip().lower():
            return False

        # Use LLM for semantic comparison
        try:
            llm_service = self.db_manager._services.get("llm")
            if not llm_service:
                observability.observe(
                    event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                    level=observability.EventLevel.WARNING,
                    data={"service": "llm", "fallback": "consider_all_changes_significant"},
                    description="LLM service not available for prompt comparison",
                )
                return True  # Fallback: consider all changes significant

            llm = LLM(service=llm_service)

            from ...formation.prompts.loader import PromptLoader

            prompt = PromptLoader.get(
                "scheduler_task_comparison.md", old_prompt=old_prompt, new_prompt=new_prompt
            ).strip()

            response = await llm.generate_json(prompt)
            result = response.get("different_task", True)

            observability.observe(
                event_type=observability.SystemEvents.SCHEDULER_PROMPT_COMPARISON,
                level=observability.EventLevel.DEBUG,
                data={
                    "old_prompt": old_prompt[:50] + "..." if len(old_prompt) > 50 else old_prompt,
                    "new_prompt": new_prompt[:50] + "..." if len(new_prompt) > 50 else new_prompt,
                    "different_task": result,
                    "reason": response.get("reason", ""),
                },
                description="Prompt change comparison completed",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "old_prompt": old_prompt[:50] + "..." if len(old_prompt) > 50 else old_prompt,
                    "new_prompt": new_prompt[:50] + "..." if len(new_prompt) > 50 else new_prompt,
                },
                description=f"Failed to compare prompts using LLM: {str(e)}",
            )
            # Fallback: consider all changes significant if LLM fails
            return True
