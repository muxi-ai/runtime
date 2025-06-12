"""
Comprehensive tests for RequestTracker component.

Tests cover request state management, thread safety, status updates,
cleanup operations, and error handling scenarios.
"""

import asyncio
import pytest
import time

from src.muxi.runtime.overlord.async_patterns.request_tracker import (
    RequestTracker,
    RequestState,
    RequestStatus
)


class TestRequestTracker:
    """Test suite for RequestTracker functionality."""

    @pytest.fixture
    def tracker(self):
        """Create a fresh RequestTracker instance for each test."""
        return RequestTracker()

    @pytest.fixture
    def sample_request_state(self):
        """Create a sample RequestState for testing."""
        return RequestState(
            id="req_test_123",
            status=RequestStatus.PROCESSING,
            start_time=time.time(),
            user_id="user_456",
            webhook_url="https://example.com/webhook"
        )

    @pytest.mark.asyncio
    async def test_track_request_basic(self, tracker, sample_request_state):
        """Test basic request tracking functionality."""
        # Track a new request
        await tracker.track_request(sample_request_state.id, sample_request_state)

        # Retrieve the request
        retrieved = await tracker.get_request(sample_request_state.id)

        assert retrieved is not None
        assert retrieved.id == sample_request_state.id
        assert retrieved.status == RequestStatus.PROCESSING
        assert retrieved.user_id == "user_456"
        assert retrieved.webhook_url == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_track_duplicate_request_raises_error(self, tracker, sample_request_state):
        """Test that tracking a duplicate request raises an error."""
        # Track initial request
        await tracker.track_request(sample_request_state.id, sample_request_state)

        # Attempt to track duplicate should raise ValueError
        with pytest.raises(ValueError, match="Request .* is already being tracked"):
            await tracker.track_request(sample_request_state.id, sample_request_state)

    @pytest.mark.asyncio
    async def test_update_request_status(self, tracker, sample_request_state):
        """Test updating request status and result."""
        # Track initial request
        await tracker.track_request(sample_request_state.id, sample_request_state)

        # Update to completed
        test_result = "Analysis complete: 42 insights discovered"
        await tracker.update_request(
            sample_request_state.id,
            RequestStatus.COMPLETED,
            result=test_result
        )

        # Verify update
        updated = await tracker.get_request(sample_request_state.id)
        assert updated.status == RequestStatus.COMPLETED
        assert updated.result == test_result
        assert updated.end_time is not None
        assert updated.processing_time is not None
        assert updated.processing_time > 0

    @pytest.mark.asyncio
    async def test_update_request_with_error(self, tracker, sample_request_state):
        """Test updating request with error status."""
        # Track initial request
        await tracker.track_request(sample_request_state.id, sample_request_state)

        # Update with error
        error_message = "Failed to connect to external API"
        await tracker.update_request(
            sample_request_state.id,
            RequestStatus.FAILED,
            error=error_message
        )

        # Verify error update
        updated = await tracker.get_request(sample_request_state.id)
        assert updated.status == RequestStatus.FAILED
        assert updated.error == error_message
        assert updated.end_time is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_request_raises_error(self, tracker):
        """Test that updating a non-existent request raises an error."""
        with pytest.raises(ValueError, match="Request .* not found"):
            await tracker.update_request(
                "nonexistent_req",
                RequestStatus.COMPLETED,
                result="Should fail"
            )

    @pytest.mark.asyncio
    async def test_get_nonexistent_request_returns_none(self, tracker):
        """Test that getting a non-existent request returns None."""
        result = await tracker.get_request("nonexistent_req")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_requests_empty(self, tracker):
        """Test listing requests when tracker is empty."""
        requests = await tracker.list_requests()
        assert requests == []

    @pytest.mark.asyncio
    async def test_list_requests_with_data(self, tracker):
        """Test listing requests with multiple tracked requests."""
        # Create multiple requests
        states = []
        for i in range(3):
            state = RequestState(
                id=f"req_test_{i}",
                status=RequestStatus.PROCESSING,
                start_time=time.time(),
                user_id=f"user_{i}"
            )
            states.append(state)
            await tracker.track_request(state.id, state)

        # List all requests
        requests = await tracker.list_requests()
        assert len(requests) == 3

        # Verify all requests are present
        request_ids = [req.id for req in requests]
        for state in states:
            assert state.id in request_ids

    @pytest.mark.asyncio
    async def test_list_requests_by_status(self, tracker):
        """Test filtering requests by status."""
        # Create requests with different statuses
        processing_state = RequestState(
            id="req_processing",
            status=RequestStatus.PROCESSING,
            start_time=time.time(),
            user_id="user_1"
        )
        completed_state = RequestState(
            id="req_completed",
            status=RequestStatus.COMPLETED,
            start_time=time.time() - 100,
            end_time=time.time() - 50,
            user_id="user_2",
            result="Done"
        )

        await tracker.track_request(processing_state.id, processing_state)
        await tracker.track_request(completed_state.id, completed_state)

        # Filter by processing status
        processing_requests = await tracker.list_requests(status=RequestStatus.PROCESSING)
        assert len(processing_requests) == 1
        assert processing_requests[0].id == "req_processing"

        # Filter by completed status
        completed_requests = await tracker.list_requests(status=RequestStatus.COMPLETED)
        assert len(completed_requests) == 1
        assert completed_requests[0].id == "req_completed"

    @pytest.mark.asyncio
    async def test_cleanup_completed_requests(self, tracker):
        """Test cleanup of old completed requests."""
        current_time = time.time()

        # Create old completed request (older than max age)
        old_state = RequestState(
            id="req_old",
            status=RequestStatus.COMPLETED,
            start_time=current_time - 7200,  # 2 hours ago
            end_time=current_time - 7100,   # Completed 1h 58m ago
            user_id="user_old",
            result="Old result"
        )

        # Create recent completed request (within max age)
        recent_state = RequestState(
            id="req_recent",
            status=RequestStatus.COMPLETED,
            start_time=current_time - 1800,  # 30 minutes ago
            end_time=current_time - 1700,   # Completed 28m ago
            user_id="user_recent",
            result="Recent result"
        )

        # Create still processing request
        processing_state = RequestState(
            id="req_processing",
            status=RequestStatus.PROCESSING,
            start_time=current_time - 3600,  # 1 hour ago
            user_id="user_processing"
        )

        await tracker.track_request(old_state.id, old_state)
        await tracker.track_request(recent_state.id, recent_state)
        await tracker.track_request(processing_state.id, processing_state)

        # Cleanup requests older than 1 hour (3600 seconds)
        cleaned_count = await tracker.cleanup_completed_requests(max_age_seconds=3600)

        # Should have cleaned up 1 request (the old completed one)
        assert cleaned_count == 1

        # Verify the old request is gone
        assert await tracker.get_request("req_old") is None

        # Verify recent and processing requests remain
        assert await tracker.get_request("req_recent") is not None
        assert await tracker.get_request("req_processing") is not None

    @pytest.mark.asyncio
    async def test_cleanup_no_requests_to_clean(self, tracker):
        """Test cleanup when no requests meet the age criteria."""
        current_time = time.time()

        # Create recent completed request
        recent_state = RequestState(
            id="req_recent",
            status=RequestStatus.COMPLETED,
            start_time=current_time - 100,
            end_time=current_time - 50,
            user_id="user_recent",
            result="Recent result"
        )

        await tracker.track_request(recent_state.id, recent_state)

        # Cleanup with very small max age - should not clean anything
        cleaned_count = await tracker.cleanup_completed_requests(max_age_seconds=10)

        assert cleaned_count == 0
        assert await tracker.get_request("req_recent") is not None

    @pytest.mark.asyncio
    async def test_thread_safety_concurrent_operations(self, tracker):
        """Test thread safety with concurrent operations."""

        async def track_and_update_request(request_id: str, delay: float = 0):
            """Helper to track and update a request with optional delay."""
            if delay > 0:
                await asyncio.sleep(delay)

            state = RequestState(
                id=request_id,
                status=RequestStatus.PROCESSING,
                start_time=time.time(),
                user_id=f"user_{request_id}"
            )

            await tracker.track_request(request_id, state)

            # Small delay to simulate processing
            await asyncio.sleep(0.01)

            await tracker.update_request(
                request_id,
                RequestStatus.COMPLETED,
                result=f"Result for {request_id}"
            )

        # Run multiple concurrent operations
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                track_and_update_request(f"concurrent_req_{i}", delay=i * 0.005)
            )
            tasks.append(task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        # Verify all requests were tracked and updated correctly
        for i in range(10):
            request_id = f"concurrent_req_{i}"
            state = await tracker.get_request(request_id)

            assert state is not None
            assert state.status == RequestStatus.COMPLETED
            assert state.result == f"Result for {request_id}"
            assert state.end_time is not None

    @pytest.mark.asyncio
    async def test_concurrent_cleanup_operations(self, tracker):
        """Test concurrent cleanup operations don't interfere."""
        current_time = time.time()

        # Create multiple old completed requests
        for i in range(5):
            old_state = RequestState(
                id=f"req_old_{i}",
                status=RequestStatus.COMPLETED,
                start_time=current_time - 7200,
                end_time=current_time - 7100,
                user_id=f"user_old_{i}",
                result=f"Old result {i}"
            )
            await tracker.track_request(old_state.id, old_state)

        # Run multiple concurrent cleanup operations
        cleanup_tasks = []
        for _ in range(3):
            task = asyncio.create_task(
                tracker.cleanup_completed_requests(max_age_seconds=3600)
            )
            cleanup_tasks.append(task)

        # Wait for all cleanup tasks
        results = await asyncio.gather(*cleanup_tasks)

        # Total cleaned should be 5 (might be distributed across the cleanups)
        total_cleaned = sum(results)
        assert total_cleaned == 5

        # Verify all old requests are gone
        for i in range(5):
            assert await tracker.get_request(f"req_old_{i}") is None

    def test_request_state_processing_time_calculation(self):
        """Test processing time calculation in RequestState."""
        start_time = time.time()
        end_time = start_time + 125.5  # 2 minutes 5.5 seconds

        state = RequestState(
            id="req_timing_test",
            status=RequestStatus.COMPLETED,
            start_time=start_time,
            end_time=end_time,
            user_id="user_timing"
        )

        assert abs(state.processing_time - 125.5) < 0.01

    def test_request_state_processing_time_none_when_incomplete(self):
        """Test that processing time is None when request is not complete."""
        state = RequestState(
            id="req_incomplete",
            status=RequestStatus.PROCESSING,
            start_time=time.time(),
            user_id="user_incomplete"
        )

        assert state.processing_time is None

    @pytest.mark.asyncio
    async def test_tracker_memory_management(self, tracker):
        """Test that the tracker properly manages memory with many requests."""
        # Track many requests
        request_ids = []
        for i in range(100):
            request_id = f"req_memory_test_{i}"
            state = RequestState(
                id=request_id,
                status=RequestStatus.PROCESSING,
                start_time=time.time(),
                user_id=f"user_{i}"
            )
            await tracker.track_request(request_id, state)
            request_ids.append(request_id)

        # Verify all are tracked
        all_requests = await tracker.list_requests()
        assert len(all_requests) == 100

        # Complete half of them
        for i in range(50):
            await tracker.update_request(
                request_ids[i],
                RequestStatus.COMPLETED,
                result=f"Result {i}"
            )

        # Cleanup completed requests
        cleaned = await tracker.cleanup_completed_requests(max_age_seconds=0)
        assert cleaned == 50

        # Verify only processing requests remain
        remaining_requests = await tracker.list_requests()
        assert len(remaining_requests) == 50

        # Verify they're all processing
        for req in remaining_requests:
            assert req.status == RequestStatus.PROCESSING
