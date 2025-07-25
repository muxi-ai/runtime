"""
Performance tests for scheduler service improvements.

This module tests the performance optimizations implemented for the scheduler,
including batch processing, caching, and circuit breaker functionality.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

from src.muxi.services.scheduler.service import SchedulerService
from src.muxi.services.scheduler.batch_processor import JobBatchProcessor
from src.muxi.services.scheduler.cache import SchedulerCache
from src.muxi.services.scheduler.circuit_breaker import LLMCircuitBreaker, CircuitBreakerError


class TestSchedulerPerformance:
    """Test suite for scheduler performance improvements."""

    @pytest.mark.asyncio
    async def test_batch_processing_scales(self):
        """Test that batch processing handles large job counts efficiently."""
        # Mock job manager with 10,000 jobs
        mock_job_manager = Mock()
        mock_job_manager.get_active_jobs_count = AsyncMock(return_value=10000)

        # Mock batch returns
        async def mock_batch(offset, limit):
            if offset >= 10000:
                return []
            return [
                {"id": f"job_{i}", "cron_expression": "0 * * * *"}
                for i in range(offset, min(offset + limit, 10000))
            ]

        mock_job_manager.get_active_jobs_batch = AsyncMock(side_effect=mock_batch)

        # Create batch processor
        processor = JobBatchProcessor(mock_job_manager)
        processor.batch_size = 100

        # Process all jobs
        start_time = time.time()
        total_jobs = 0

        async for batch in processor.iterate_active_jobs_batched():
            total_jobs += len(batch)
            # Simulate some processing
            await asyncio.sleep(0.001)

        processing_time = time.time() - start_time

        # Verify all jobs were processed
        assert total_jobs == 10000

        # Verify batch processing was used
        assert mock_job_manager.get_active_jobs_batch.call_count == 100

        # Should complete in reasonable time
        assert processing_time < 5.0  # Should be much faster than loading all at once

    @pytest.mark.asyncio
    async def test_cache_reduces_llm_calls(self):
        """Test that caching significantly reduces LLM calls."""
        cache = SchedulerCache(cache_ttl=300)

        # Test job type caching
        schedule_texts = [
            "remind me every day at 9am",
            "send report every friday",
            "remind me every day at 9am",  # Duplicate
            "check status daily",
            "send report every friday",  # Duplicate
        ]

        llm_calls = 0

        for text in schedule_texts:
            cached = cache.get_cached_job_type(text)
            if not cached:
                # Simulate LLM call
                llm_calls += 1
                job_type = "recurring"  # Mock result
                cache.cache_job_type(text, job_type)

        # Should only call LLM for unique texts
        assert llm_calls == 3

        # Verify cache stats
        stats = cache.get_cache_stats()
        assert stats["hits"] == 2  # Two cache hits
        assert stats["misses"] == 3  # Three cache misses
        assert stats["hit_rate"] == 0.4  # 40% hit rate

    def test_circuit_breaker_prevents_cascading_failures(self):
        """Test that circuit breaker prevents cascading LLM failures."""
        breaker = LLMCircuitBreaker(failure_threshold=3, timeout=1.0)  # Short timeout for testing

        async def failing_llm_call():
            raise Exception("LLM service unavailable")

        # Test that circuit opens after threshold
        for i in range(3):
            with pytest.raises(Exception):
                asyncio.run(breaker.call(failing_llm_call))

        # Circuit should now be open
        assert breaker.get_state() == "open"

        # Further calls should be rejected immediately
        with pytest.raises(CircuitBreakerError):
            asyncio.run(breaker.call(failing_llm_call))

        # Verify stats
        stats = breaker.get_stats()
        assert stats["failed_calls"] == 3
        assert stats["rejected_calls"] == 1

    @pytest.mark.asyncio
    async def test_performance_monitoring(self):
        """Test performance monitoring capabilities."""
        # Create scheduler with mocked components
        mock_overlord = Mock()
        mock_overlord._configured_services = {}
        mock_overlord.formation_config = {
            "scheduler": {"enabled": True, "check_interval_minutes": 1}
        }

        with patch("muxi.services.scheduler.service.get_database_manager"):
            scheduler = SchedulerService(mock_overlord)

            # Simulate some activity
            scheduler._performance_stats["cycles_completed"] = 100
            scheduler._performance_stats["jobs_processed"] = 500

            # Mock cache stats
            scheduler.cache = Mock()
            scheduler.cache.get_cache_stats = Mock(
                return_value={"hits": 350, "misses": 150, "hit_rate": 0.7}
            )

            # Mock circuit breaker stats
            scheduler.llm_circuit_breaker = Mock()
            scheduler.llm_circuit_breaker.get_stats = Mock(
                return_value={"state": "closed", "successful_calls": 150, "failed_calls": 0}
            )

            # Mock job manager
            scheduler.job_manager = Mock()
            scheduler.job_manager.count_active_jobs = AsyncMock(return_value=250)

            # Get performance stats
            stats = await scheduler.get_performance_stats()

            # Verify comprehensive metrics
            assert stats["scheduler_stats"]["cycles_completed"] == 100
            assert stats["scheduler_stats"]["jobs_processed"] == 500
            assert stats["scheduler_stats"]["active_jobs"] == 250

            assert stats["cache_stats"]["hit_rate"] == 0.7
            assert stats["performance_improvements"]["llm_calls_saved"] == 350
            assert stats["performance_improvements"]["memory_efficient"] is True

            assert stats["circuit_breaker_stats"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_cleanup_performance(self):
        """Test batch cleanup performance."""
        mock_job_manager = Mock()

        # Mock cleanup returns
        async def mock_cleanup(retention_days, offset, limit):
            if offset >= 1000:
                return 0
            return min(100, 1000 - offset)  # Simulate 1000 old jobs

        mock_job_manager.cleanup_old_jobs_batch = AsyncMock(side_effect=mock_cleanup)

        processor = JobBatchProcessor(mock_job_manager)
        processor.batch_size = 100

        # Perform cleanup
        start_time = time.time()
        total_cleaned = await processor.cleanup_old_jobs(retention_days=30)
        cleanup_time = time.time() - start_time

        # Verify cleanup completed
        assert total_cleaned == 1000

        # Should be done in batches
        assert mock_job_manager.cleanup_old_jobs_batch.call_count == 10

        # Should complete quickly
        assert cleanup_time < 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
