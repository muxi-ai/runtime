"""
Batch processing for scheduler jobs to handle large-scale deployments.

This module provides efficient batch processing capabilities for the scheduler,
allowing it to handle thousands of jobs without loading them all into memory.
"""

from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime
import asyncio

from ...datatypes.schema import SchedulerServiceSchema
from .. import observability


class JobBatchProcessor:
    """
    Handles batch processing of scheduler jobs for improved scalability.

    Instead of loading all jobs into memory at once, this processor retrieves
    and processes jobs in configurable batches, significantly reducing memory
    usage and improving performance for large-scale deployments.
    """

    def __init__(self, job_manager, config: Optional[SchedulerServiceSchema] = None):
        """
        Initialize the batch processor.

        Args:
            job_manager: The JobManager instance for database operations
            config: Optional scheduler configuration
        """
        self.job_manager = job_manager
        self.config = config or SchedulerServiceSchema()

        # Batch size should be tuned based on available memory and job complexity
        # Handle both dict and object config
        if isinstance(self.config, dict):
            max_concurrent = self.config.get('max_concurrent_jobs', 10)
        else:
            max_concurrent = getattr(self.config, 'max_concurrent_jobs', 10)
        self.batch_size = min(100, max_concurrent * 10)

    async def get_active_jobs_count(self) -> int:
        """
        Get total count of active jobs without loading them.

        Returns:
            Total number of active jobs
        """
        return await self.job_manager.get_active_jobs_count()

    async def iterate_active_jobs_batched(self) -> AsyncIterator[List[Dict[str, Any]]]:
        """
        Iterate through active jobs in batches.

        Yields:
            Batches of active jobs
        """
        offset = 0

        while True:
            # Get next batch of jobs
            batch = await self.job_manager.get_active_jobs_batch(
                offset=offset, limit=self.batch_size
            )

            if not batch:
                break

            yield batch
            offset += self.batch_size

            # Small delay to prevent database overload
            await asyncio.sleep(0.01)

    async def process_due_jobs(
        self, current_time: datetime, is_job_due_func, check_exclusion_func
    ) -> List[Dict[str, Any]]:
        """
        Process all active jobs in batches to find due jobs.

        Args:
            current_time: Current time for due job evaluation
            is_job_due_func: Function to check if a job is due
            check_exclusion_func: Function to check exclusion rules

        Returns:
            List of jobs due for execution
        """
        due_jobs = []
        total_processed = 0

        async for batch in self.iterate_active_jobs_batched():
            batch_due_jobs = await self._process_batch(
                batch, current_time, is_job_due_func, check_exclusion_func
            )

            due_jobs.extend(batch_due_jobs)
            total_processed += len(batch)

            # Respect concurrent job limits
            if isinstance(self.config, dict):
                max_concurrent = self.config.get('max_concurrent_jobs', 10)
            else:
                max_concurrent = getattr(self.config, 'max_concurrent_jobs', 10)

            if len(due_jobs) >= max_concurrent:
                break

        if isinstance(self.config, dict):
            max_concurrent = self.config.get('max_concurrent_jobs', 10)
        else:
            max_concurrent = getattr(self.config, 'max_concurrent_jobs', 10)
        return due_jobs[:max_concurrent]

    async def _process_batch(
        self,
        batch: List[Dict[str, Any]],
        current_time: datetime,
        is_job_due_func,
        check_exclusion_func,
    ) -> List[Dict[str, Any]]:
        """
        Process a single batch of jobs.

        Args:
            batch: Batch of jobs to process
            current_time: Current time for evaluation
            is_job_due_func: Function to check if job is due
            check_exclusion_func: Function to check exclusion rules

        Returns:
            Jobs from this batch that are due
        """
        batch_due_jobs = []

        # Process jobs concurrently within batch for better performance
        async def check_job(job):
            try:
                if await is_job_due_func(job, current_time):
                    if not await check_exclusion_func(job, current_time):
                        return job
            except Exception as e:
                # Log error but don't fail entire batch
                job_id = job.get('id', 'unknown')
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "operation": "job_check",
                        "job_id": job_id,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                    description=f"Failed to check if job '{job_id}' is due",
                )
                print(f"Error checking job {job_id}: {str(e)}", flush=True)
            return None

        # Check all jobs in batch concurrently
        results = await asyncio.gather(*[check_job(job) for job in batch], return_exceptions=False)

        # Filter out None results
        batch_due_jobs = [job for job in results if job is not None]

        return batch_due_jobs

    async def cleanup_old_jobs(self, retention_days: int) -> int:
        """
        Clean up old completed jobs in batches.

        Args:
            retention_days: Number of days to retain completed jobs

        Returns:
            Number of jobs cleaned up
        """
        total_cleaned = 0
        offset = 0

        while True:
            # Get batch of old jobs
            batch_count = await self.job_manager.cleanup_old_jobs_batch(
                retention_days=retention_days, offset=offset, limit=self.batch_size
            )

            if batch_count == 0:
                break

            total_cleaned += batch_count

            # Small delay between batches
            await asyncio.sleep(0.1)

        return total_cleaned

    def get_batch_size(self) -> int:
        """Get current batch size configuration."""
        return self.batch_size

    def set_batch_size(self, size: int) -> None:
        """
        Update batch size.

        Args:
            size: New batch size (will be clamped to reasonable limits)
        """
        self.batch_size = max(10, min(500, size))
