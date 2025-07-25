"""
MUXI Scheduler Performance Tests

Tests for performance, scalability, and reliability of the scheduler.
Ensures the scheduler can handle large numbers of jobs efficiently.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

from muxi.services.scheduler.service import SchedulerService
from muxi.services.scheduler.manager import JobManager
from muxi.services.scheduler.limits import ResourceLimits, configure_limits
from muxi.services.db import get_database_manager
from muxi.utils.datetime_utils import utc_now


class TestSchedulerPerformance:
    """Test scheduler performance and scalability."""

    @pytest.mark.asyncio
    async def test_job_discovery_performance(self):
        """Test that job discovery scales with job count."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Create a moderate number of jobs for performance testing
        num_jobs = 100
        job_ids = []

        # Measure job creation time
        creation_start = time.time()
        for i in range(num_jobs):
            job_id = await job_manager.create_job(
                user_id=f"user_{i % 10}",  # 10 different users
                formation_id="test_formation",
                title=f"Performance Test Job {i}",
                original_prompt="test",
                execution_prompt="test",
                cron_expression=f"0 {i % 24} * * *"  # Spread across hours
            )
            job_ids.append(job_id)

        creation_time = time.time() - creation_start
        print(f"Created {num_jobs} jobs in {creation_time:.2f} seconds")

        # Test job discovery performance
        discovery_start = time.time()
        active_jobs = await job_manager.get_active_jobs()
        discovery_time = time.time() - discovery_start

        print(f"Discovered {len(active_jobs)} jobs in {discovery_time:.3f} seconds")

        # Performance assertions
        assert len(active_jobs) == num_jobs
        assert discovery_time < 1.0  # Should complete in under 1 second
        assert creation_time < 10.0  # Job creation should be reasonable

    @pytest.mark.asyncio
    async def test_concurrent_job_creation(self):
        """Test concurrent job creation doesn't cause race conditions."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Configure higher limits for this test
        test_limits = ResourceLimits(
            max_jobs_per_user=200,
            max_job_creations_per_hour=200
        )
        configure_limits(test_limits)

        async def create_job(i):
            """Create a single job."""
            return await job_manager.create_job(
                user_id=f"user_{i}",
                formation_id="test_formation",
                title=f"Concurrent Job {i}",
                original_prompt="test",
                execution_prompt="test",
                cron_expression="0 9 * * *"
            )

        # Create jobs concurrently
        num_concurrent_jobs = 20
        start_time = time.time()

        tasks = [create_job(i) for i in range(num_concurrent_jobs)]
        job_ids = await asyncio.gather(*tasks)

        elapsed_time = time.time() - start_time
        print(f"Created {num_concurrent_jobs} jobs concurrently in {elapsed_time:.2f} seconds")

        # All should succeed with unique IDs
        assert len(set(job_ids)) == num_concurrent_jobs
        assert elapsed_time < 5.0  # Should complete reasonably quickly

        # Verify all jobs are in database
        all_jobs = await job_manager.get_active_jobs()
        assert len(all_jobs) == num_concurrent_jobs

    @pytest.mark.asyncio
    async def test_large_scale_job_management(self):
        """Test management of a large number of jobs."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Configure for large scale testing
        test_limits = ResourceLimits(
            max_jobs_per_user=1000,
            max_job_creations_per_hour=1000,
            max_total_active_jobs=5000
        )
        configure_limits(test_limits)

        # Create many jobs for different users
        num_users = 5
        jobs_per_user = 50
        total_jobs = num_users * jobs_per_user

        print(f"Creating {total_jobs} jobs for {num_users} users...")

        start_time = time.time()
        for user_i in range(num_users):
            user_id = f"scale_user_{user_i}"

            # Create jobs for this user
            user_start = time.time()
            for job_i in range(jobs_per_user):
                await job_manager.create_job(
                    user_id=user_id,
                    formation_id="scale_formation",
                    title=f"Scale Job {user_i}-{job_i}",
                    original_prompt="test",
                    execution_prompt="test",
                    cron_expression=f"0 {job_i % 24} * * *"
                )

            user_time = time.time() - user_start
            print(f"Created {jobs_per_user} jobs for {user_id} in {user_time:.2f}s")

        total_creation_time = time.time() - start_time
        print(f"Total creation time: {total_creation_time:.2f} seconds")

        # Test retrieval performance
        retrieval_start = time.time()
        all_jobs = await job_manager.get_active_jobs()
        retrieval_time = time.time() - retrieval_start

        print(f"Retrieved {len(all_jobs)} jobs in {retrieval_time:.3f} seconds")

        # Test user-specific retrieval
        user_retrieval_start = time.time()
        user_jobs = await job_manager.get_user_jobs("scale_user_0")
        user_retrieval_time = time.time() - user_retrieval_start

        print(f"Retrieved {len(user_jobs)} user jobs in {user_retrieval_time:.3f} seconds")

        # Performance assertions
        assert len(all_jobs) == total_jobs
        assert len(user_jobs) == jobs_per_user
        assert retrieval_time < 2.0  # Should retrieve quickly
        assert user_retrieval_time < 1.0  # User queries should be fast

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self):
        """Test that memory usage remains stable with many operations."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Configure for memory testing
        test_limits = ResourceLimits(
            max_jobs_per_user=500,
            max_job_creations_per_hour=500
        )
        configure_limits(test_limits)

        # Perform many operations
        num_iterations = 10
        for iteration in range(num_iterations):
            # Create some jobs
            for i in range(10):
                await job_manager.create_job(
                    user_id=f"mem_user_{iteration}",
                    formation_id="mem_formation",
                    title=f"Memory Test Job {iteration}-{i}",
                    original_prompt="test",
                    execution_prompt="test",
                    cron_expression=f"0 {i} * * *"
                )

            # Retrieve jobs
            await job_manager.get_active_jobs()
            await job_manager.get_user_jobs(f"mem_user_{iteration}")

            # Check memory periodically
            if iteration % 3 == 0:
                current_memory = process.memory_info().rss
                memory_increase = current_memory - initial_memory
                print(f"Iteration {iteration}: Memory increase: {memory_increase / 1024 / 1024:.1f} MB")

        final_memory = process.memory_info().rss
        total_memory_increase = final_memory - initial_memory
        print(f"Total memory increase: {total_memory_increase / 1024 / 1024:.1f} MB")

        # Memory should not grow excessively (allow some growth for data structures)
        assert total_memory_increase < 50 * 1024 * 1024  # Less than 50MB increase


class TestSchedulerReliability:
    """Test scheduler reliability and error handling."""

    @pytest.mark.asyncio
    async def test_database_error_recovery(self):
        """Test recovery from database errors."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Create a valid job first
        job_id = await job_manager.create_job(
            user_id="test_user",
            formation_id="test_formation",
            title="Test Job",
            original_prompt="test",
            execution_prompt="test",
            cron_expression="0 9 * * *"
        )

        # Simulate database corruption by trying invalid operations
        try:
            # This should handle the error gracefully
            invalid_job = await job_manager.get_job("nonexistent_job_id")
            assert invalid_job is None
        except Exception as e:
            # Should handle errors without crashing
            assert "not found" in str(e).lower() or "does not exist" in str(e).lower()

        # Scheduler should still work after error
        another_job_id = await job_manager.create_job(
            user_id="test_user",
            formation_id="test_formation",
            title="Recovery Test",
            original_prompt="test",
            execution_prompt="test",
            cron_expression="0 10 * * *"
        )
        assert another_job_id.startswith("sched_")

    @pytest.mark.asyncio
    async def test_invalid_input_handling(self):
        """Test handling of various invalid inputs."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        invalid_inputs = [
            # Invalid user ID
            {
                "user_id": "invalid@user",
                "formation_id": "test_formation",
                "title": "Test",
                "original_prompt": "test",
                "execution_prompt": "test",
                "cron_expression": "0 9 * * *"
            },
            # Invalid cron expression
            {
                "user_id": "test_user",
                "formation_id": "test_formation",
                "title": "Test",
                "original_prompt": "test",
                "execution_prompt": "test",
                "cron_expression": "invalid cron"
            },
            # Empty title
            {
                "user_id": "test_user",
                "formation_id": "test_formation",
                "title": "",
                "original_prompt": "test",
                "execution_prompt": "test",
                "cron_expression": "0 9 * * *"
            },
        ]

        for invalid_input in invalid_inputs:
            with pytest.raises((ValueError, Exception)):
                await job_manager.create_job(**invalid_input)

        # Verify scheduler still works after handling invalid inputs
        valid_job_id = await job_manager.create_job(
            user_id="test_user",
            formation_id="test_formation",
            title="Valid Job",
            original_prompt="test",
            execution_prompt="test",
            cron_expression="0 9 * * *"
        )
        assert valid_job_id.startswith("sched_")

    @pytest.mark.asyncio
    async def test_resource_limit_enforcement_reliability(self):
        """Test that resource limits are consistently enforced."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Set very strict limits
        test_limits = ResourceLimits(
            max_jobs_per_user=3,
            max_job_creations_per_hour=5
        )
        configure_limits(test_limits)

        # Create maximum allowed jobs
        for i in range(3):
            await job_manager.create_job(
                user_id="limit_test_user",
                formation_id="test_formation",
                title=f"Limit Test Job {i}",
                original_prompt="test",
                execution_prompt="test",
                cron_expression=f"0 {9+i} * * *"
            )

        # Multiple attempts to exceed limit should all fail
        for attempt in range(5):
            with pytest.raises(ValueError, match="maximum job limit"):
                await job_manager.create_job(
                    user_id="limit_test_user",
                    formation_id="test_formation",
                    title=f"Excess Job {attempt}",
                    original_prompt="test",
                    execution_prompt="test",
                    cron_expression="0 12 * * *"
                )

        # Verify the count is still correct
        user_jobs = await job_manager.get_user_jobs("limit_test_user")
        assert len([job for job in user_jobs if job['status'] == 'ACTIVE']) == 3


class TestSchedulerScalability:
    """Test scheduler scalability patterns."""

    @pytest.mark.asyncio
    async def test_multi_user_isolation(self):
        """Test that operations for different users don't interfere."""
        db_manager = get_database_manager(":memory:")
        job_manager = JobManager(db_manager)
        await job_manager.initialize()

        # Configure for multi-user testing
        test_limits = ResourceLimits(
            max_jobs_per_user=50,
            max_job_creations_per_hour=100
        )
        configure_limits(test_limits)

        async def create_user_jobs(user_id: str, num_jobs: int) -> List[str]:
            """Create jobs for a specific user."""
            job_ids = []
            for i in range(num_jobs):
                job_id = await job_manager.create_job(
                    user_id=user_id,
                    formation_id=f"formation_{user_id}",
                    title=f"Job {i} for {user_id}",
                    original_prompt="test",
                    execution_prompt="test",
                    cron_expression=f"0 {i % 24} * * *"
                )
                job_ids.append(job_id)
            return job_ids

        # Create jobs for multiple users concurrently
        users = [f"user_{i}" for i in range(5)]
        tasks = [create_user_jobs(user, 10) for user in users]

        start_time = time.time()
        all_user_jobs = await asyncio.gather(*tasks)
        elapsed_time = time.time() - start_time

        print(f"Created jobs for {len(users)} users in {elapsed_time:.2f} seconds")

        # Verify isolation: each user should have exactly their jobs
        for i, user in enumerate(users):
            user_jobs = await job_manager.get_user_jobs(user)
            assert len(user_jobs) == 10

            # All jobs should belong to this user
            for job in user_jobs:
                assert job['user_id'] == user
                assert job['formation_id'] == f"formation_{user}"

        # Total job count should be correct
        all_jobs = await job_manager.get_active_jobs()
        assert len(all_jobs) == 50  # 5 users * 10 jobs each


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
