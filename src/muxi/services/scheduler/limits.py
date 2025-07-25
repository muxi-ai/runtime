"""
MUXI Scheduler Resource Limits

Enforces resource limits and rate limiting for scheduler operations
to prevent abuse and ensure system stability.

Security Features:
- Job count limits per user
- Execution time limits
- Concurrent execution limits
- Rate limiting for job creation
"""

import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from ...utils.datetime_utils import utc_now


@dataclass
class ResourceLimits:
    """Configuration for scheduler resource limits."""

    # Job limits
    max_jobs_per_user: int = 100
    max_concurrent_jobs_per_user: int = 5
    max_execution_time_seconds: int = 300  # 5 minutes

    # Rate limiting
    max_job_creations_per_hour: int = 20
    max_job_creations_per_day: int = 100

    # System limits
    max_total_active_jobs: int = 10000
    max_failed_executions_before_pause: int = 5


class RateLimiter:
    """Simple in-memory rate limiter for job creation."""

    def __init__(self):
        """Initialize rate limiter."""
        self._hourly_counts: Dict[str, List[datetime]] = {}
        self._daily_counts: Dict[str, List[datetime]] = {}
        self._cleanup_interval = 3600  # Cleanup every hour
        self._last_cleanup = time.time()

    def check_rate_limit(
        self,
        user_id: str,
        limits: ResourceLimits
    ) -> None:
        """
        Check if user has exceeded rate limits.

        Args:
            user_id: User identifier
            limits: Resource limits configuration

        Raises:
            ValueError: If rate limit exceeded
        """
        self._cleanup_old_entries()

        now = utc_now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        # Check hourly limit
        if user_id not in self._hourly_counts:
            self._hourly_counts[user_id] = []

        # Remove old entries
        self._hourly_counts[user_id] = [
            ts for ts in self._hourly_counts[user_id]
            if ts > hour_ago
        ]

        if len(self._hourly_counts[user_id]) >= limits.max_job_creations_per_hour:
            raise ValueError(
                f"Rate limit exceeded: maximum {limits.max_job_creations_per_hour} "
                f"job creations per hour"
            )

        # Check daily limit
        if user_id not in self._daily_counts:
            self._daily_counts[user_id] = []

        # Remove old entries
        self._daily_counts[user_id] = [
            ts for ts in self._daily_counts[user_id]
            if ts > day_ago
        ]

        if len(self._daily_counts[user_id]) >= limits.max_job_creations_per_day:
            raise ValueError(
                f"Rate limit exceeded: maximum {limits.max_job_creations_per_day} "
                f"job creations per day"
            )

        # Record this request
        self._hourly_counts[user_id].append(now)
        self._daily_counts[user_id].append(now)

    def _cleanup_old_entries(self) -> None:
        """Clean up old rate limiting entries to prevent memory leaks."""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return

        now = utc_now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        # Clean up hourly counts
        for user_id in list(self._hourly_counts.keys()):
            self._hourly_counts[user_id] = [
                ts for ts in self._hourly_counts[user_id]
                if ts > hour_ago
            ]
            if not self._hourly_counts[user_id]:
                del self._hourly_counts[user_id]

        # Clean up daily counts
        for user_id in list(self._daily_counts.keys()):
            self._daily_counts[user_id] = [
                ts for ts in self._daily_counts[user_id]
                if ts > day_ago
            ]
            if not self._daily_counts[user_id]:
                del self._daily_counts[user_id]

        self._last_cleanup = current_time


class SchedulerLimitsEnforcer:
    """Enforces resource limits for scheduler operations."""

    def __init__(self, limits: Optional[ResourceLimits] = None):
        """
        Initialize limits enforcer.

        Args:
            limits: Resource limits configuration
        """
        self.limits = limits or ResourceLimits()
        self.rate_limiter = RateLimiter()

    async def check_job_creation_limits(
        self,
        job_manager,
        user_id: str
    ) -> None:
        """
        Check if user can create a new job without exceeding limits.

        Args:
            job_manager: JobManager instance for database queries
            user_id: User identifier

        Raises:
            ValueError: If limits would be exceeded
        """
        # Check rate limits first (fast check)
        self.rate_limiter.check_rate_limit(user_id, self.limits)

        # Check job count limits (requires database query)
        user_jobs = await job_manager.get_user_jobs(user_id)
        active_jobs = [job for job in user_jobs if job['status'] == 'ACTIVE']

        if len(active_jobs) >= self.limits.max_jobs_per_user:
            raise ValueError(
                f"User has reached maximum job limit "
                f"({self.limits.max_jobs_per_user} active jobs)"
            )

        # Check concurrent execution limits
        running_jobs = [
            job for job in active_jobs
            if job.get('last_execution_status') == 'RUNNING'
        ]

        if len(running_jobs) >= self.limits.max_concurrent_jobs_per_user:
            raise ValueError(
                f"User has reached maximum concurrent execution limit "
                f"({self.limits.max_concurrent_jobs_per_user} running jobs)"
            )

    async def check_system_limits(self, job_manager) -> None:
        """
        Check system-wide limits.

        Args:
            job_manager: JobManager instance for database queries

        Raises:
            ValueError: If system limits would be exceeded
        """
        all_active_jobs = await job_manager.get_active_jobs()

        if len(all_active_jobs) >= self.limits.max_total_active_jobs:
            raise ValueError(
                f"System has reached maximum active job limit "
                f"({self.limits.max_total_active_jobs} jobs)"
            )

    def should_pause_job(self, job: Dict[str, Any]) -> bool:
        """
        Check if a job should be paused due to repeated failures.

        Args:
            job: Job dictionary from database

        Returns:
            True if job should be paused
        """
        consecutive_failures = job.get('consecutive_failures', 0)
        return consecutive_failures >= self.limits.max_failed_executions_before_pause

    def get_execution_timeout(self) -> int:
        """
        Get the maximum execution time for jobs.

        Returns:
            Timeout in seconds
        """
        return self.limits.max_execution_time_seconds


# Global instance for use throughout the scheduler
_global_limits_enforcer: Optional[SchedulerLimitsEnforcer] = None


def get_limits_enforcer() -> SchedulerLimitsEnforcer:
    """
    Get the global limits enforcer instance.

    Returns:
        SchedulerLimitsEnforcer instance
    """
    global _global_limits_enforcer
    if _global_limits_enforcer is None:
        _global_limits_enforcer = SchedulerLimitsEnforcer()
    return _global_limits_enforcer


def configure_limits(limits: ResourceLimits) -> None:
    """
    Configure global resource limits.

    Args:
        limits: New resource limits configuration
    """
    global _global_limits_enforcer
    _global_limits_enforcer = SchedulerLimitsEnforcer(limits)
