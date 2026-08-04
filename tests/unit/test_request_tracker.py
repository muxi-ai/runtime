"""Unit tests for RequestTracker TTL and cleanup."""

import asyncio
import time

import pytest

from muxi.runtime.formation.background.request_tracker import (
    DEFAULT_COMPLETED_TTL_SECONDS,
    RequestState,
    RequestStatus,
    RequestTracker,
)


@pytest.fixture
def tracker():
    return RequestTracker(completed_ttl=1.0)


@pytest.fixture
def make_state():
    def _make(request_id, status=RequestStatus.PROCESSING, **kwargs):
        return RequestState(
            id=request_id,
            status=status,
            start_time=time.time(),
            **kwargs,
        )

    return _make


@pytest.mark.asyncio
async def test_completed_requests_retained(tracker, make_state):
    """Completed requests remain in the tracker (not removed immediately)."""
    state = make_state("req_1")
    await tracker.track_request("req_1", state)
    await tracker.update_request("req_1", RequestStatus.COMPLETED, result="done")

    got = await tracker.get_request("req_1")
    assert got is not None
    assert got.status == RequestStatus.COMPLETED
    assert got.result == "done"
    assert got.end_time is not None


@pytest.mark.asyncio
async def test_failed_requests_retained(tracker, make_state):
    """Failed requests remain in the tracker."""
    state = make_state("req_2")
    await tracker.track_request("req_2", state)
    await tracker.update_request("req_2", RequestStatus.FAILED, error="boom")

    got = await tracker.get_request("req_2")
    assert got is not None
    assert got.status == RequestStatus.FAILED
    assert got.error == "boom"


@pytest.mark.asyncio
async def test_cleanup_expired_purges_old_terminal_requests(tracker, make_state):
    """cleanup_expired removes terminal requests past their TTL."""
    state = make_state("req_old")
    await tracker.track_request("req_old", state)
    await tracker.update_request("req_old", RequestStatus.COMPLETED, result="x")

    # Manually backdate end_time beyond the 1s TTL
    state.end_time = time.time() - 2.0

    purged = await tracker.cleanup_expired()
    assert purged == 1
    assert await tracker.get_request("req_old") is None


@pytest.mark.asyncio
async def test_cleanup_does_not_purge_active_requests(tracker, make_state):
    """Active (non-terminal) requests are never purged regardless of age."""
    state = make_state("req_active")
    await tracker.track_request("req_active", state)

    purged = await tracker.cleanup_expired()
    assert purged == 0
    assert await tracker.get_request("req_active") is not None


@pytest.mark.asyncio
async def test_cleanup_does_not_purge_recent_completed(tracker, make_state):
    """Completed requests within TTL are not purged."""
    state = make_state("req_fresh")
    await tracker.track_request("req_fresh", state)
    await tracker.update_request("req_fresh", RequestStatus.COMPLETED, result="y")

    purged = await tracker.cleanup_expired()
    assert purged == 0
    assert await tracker.get_request("req_fresh") is not None


@pytest.mark.asyncio
async def test_cleanup_loop_runs_periodically(tracker, make_state):
    """The background cleanup loop purges expired requests automatically."""
    state = make_state("req_loop")
    await tracker.track_request("req_loop", state)
    await tracker.update_request("req_loop", RequestStatus.COMPLETED, result="z")
    state.end_time = time.time() - 2.0

    tracker.start_cleanup_loop(interval=0.1)
    await asyncio.sleep(0.3)

    assert await tracker.get_request("req_loop") is None
    await tracker.stop_cleanup_loop()


@pytest.mark.asyncio
async def test_cancelled_requests_retained_then_cleaned(tracker, make_state):
    """Cancelled requests are retained and cleaned after TTL."""
    state = make_state("req_cancel")
    await tracker.track_request("req_cancel", state)
    await tracker.update_request("req_cancel", RequestStatus.CANCELLED)

    got = await tracker.get_request("req_cancel")
    assert got is not None
    assert got.status == RequestStatus.CANCELLED

    got.end_time = time.time() - 2.0
    purged = await tracker.cleanup_expired()
    assert purged == 1


@pytest.mark.asyncio
async def test_default_ttl():
    """Default TTL is 300 seconds."""
    tracker = RequestTracker()
    assert tracker.completed_ttl == DEFAULT_COMPLETED_TTL_SECONDS
    assert tracker.completed_ttl == 300


@pytest.mark.asyncio
async def test_mark_completed_if_active_transitions_processing(tracker, make_state):
    """An in-flight request is completed and stamped with an end_time."""
    await tracker.track_request("req_active_done", make_state("req_active_done"))

    assert await tracker.mark_completed_if_active("req_active_done", result="answer") is True

    got = await tracker.get_request("req_active_done")
    assert got.status == RequestStatus.COMPLETED
    assert got.result == "answer"
    assert got.end_time is not None


@pytest.mark.asyncio
async def test_mark_completed_if_active_keeps_terminal_status(tracker, make_state):
    """A request that already reached a terminal state is left untouched."""
    await tracker.track_request("req_cancelled", make_state("req_cancelled"))
    await tracker.update_request("req_cancelled", RequestStatus.CANCELLED)

    assert await tracker.mark_completed_if_active("req_cancelled", result="answer") is False

    got = await tracker.get_request("req_cancelled")
    assert got.status == RequestStatus.CANCELLED
    assert got.result is None


@pytest.mark.asyncio
async def test_mark_completed_if_active_unknown_request(tracker):
    """Completing an unknown request is a no-op."""
    assert await tracker.mark_completed_if_active("req_missing", result="answer") is False


@pytest.mark.asyncio
async def test_mark_completed_if_active_stops_stale_reaper(make_state):
    """A request completed this way is not reaped as stale."""
    tracker = RequestTracker(completed_ttl=60.0, stale_timeout=0.01)
    state = make_state("req_reap")
    await tracker.track_request("req_reap", state)
    await tracker.mark_completed_if_active("req_reap", result="answer")

    state.start_time = time.time() - 3600
    await tracker.cleanup_expired()

    got = await tracker.get_request("req_reap")
    assert got.status == RequestStatus.COMPLETED
    assert got.error is None


@pytest.mark.asyncio
async def test_result_stored_on_completed(tracker, make_state):
    """Result payload is stored and retrievable for completed requests."""
    state = make_state("req_result")
    await tracker.track_request("req_result", state)

    result_payload = {"content": "Here is the analysis", "metadata": {"tokens": 150}}
    await tracker.update_request("req_result", RequestStatus.COMPLETED, result=result_payload)

    got = await tracker.get_request("req_result")
    assert got.result == result_payload
    assert got.result["content"] == "Here is the analysis"
