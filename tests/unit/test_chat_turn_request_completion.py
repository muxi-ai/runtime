"""
Tests for the terminal request-tracker transition of ordinary chat turns.

Background
----------
Every chat turn registers itself in the ``RequestTracker`` as PROCESSING.
Only the overlord fast path and the async background path ever wrote
COMPLETED back, so an ordinary sync or streaming turn stayed "processing"
after it had already answered:

* ``GET /v1/requests/{request_id}`` reported "processing" forever, and its
  result-return branch never fired (status was not COMPLETED and result
  was None).
* 600s later the stale request reaper rewrote the finished turn to FAILED
  with "Request timed out (stale request reaper)", so successful turns were
  recorded as failures.

These tests pin:

* a completed sync turn reports COMPLETED with its content as the result
* a completed streaming turn does the same once the stream reaches its
  terminal event (and is not raced into CANCELLED by the disconnect path)
* the stale reaper leaves both alone
* the completed entry still honours the tracker's completed-entry TTL
* async hand-offs and cooperatively cancelled turns are not mislabelled
"""

import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.formation.background.request_tracker import (
    RequestState,
    RequestStatus,
    RequestTracker,
)
from muxi.runtime.formation.overlord.chat_orchestrator import (
    ChatOrchestrator,
    EnhancedMessage,
)
from muxi.runtime.services import streaming
from muxi.runtime.services.streaming import streaming_manager

REQUEST_ID = "req_completion_test"
USER_ID = "0"
SESSION_ID = "sess_completion_test"
STREAM_ANSWER = "Revenue grew 12%."


def _processing_state() -> RequestState:
    """The initial tracker state the orchestrator registers for a chat turn."""
    return RequestState(
        id=REQUEST_ID,
        status=RequestStatus.PROCESSING,
        start_time=time.time(),
        user_id=USER_ID,
        session_id=SESSION_ID,
    )


def _make_orchestrator(tracker: RequestTracker) -> ChatOrchestrator:
    """Build an orchestrator whose overlord is stubbed down to the tracker."""
    orch = ChatOrchestrator.__new__(ChatOrchestrator)

    overlord = MagicMock()
    overlord.request_tracker = tracker
    overlord.formation_id = "test-formation"
    overlord.is_multi_user = False
    overlord.streaming = False
    overlord.agents = {}
    # No database / persistent memory -> user resolution and background user
    # info extraction are skipped entirely.
    overlord.db_manager = None
    overlord.long_term_memory = None
    overlord.buffer_memory_manager = None
    overlord.auto_extract_user_info = False
    overlord.async_webhook_url = None
    overlord.async_threshold_seconds = 30
    overlord.mcp_service = None
    overlord._get_pending_clarification = AsyncMock(return_value=None)

    def _create_tracked_task(coro, name: Optional[str] = None):
        # Fire-and-forget storage tasks are irrelevant here; close the
        # coroutine so it never warns about never being awaited.
        coro.close()
        return None

    overlord._create_tracked_task = MagicMock(side_effect=_create_tracked_task)

    orch.overlord = overlord
    return orch


def _stub_context_enrichment(orch: ChatOrchestrator, message: str) -> None:
    """Skip the memory-backed enrichment hops the turn does not exercise."""
    enhanced = f"=== CURRENT REQUEST ===\n{message}"
    orch._enhance_message_with_context = AsyncMock(
        return_value=EnhancedMessage(original=message, enhanced=enhanced)
    )
    orch._build_clean_chat_context = AsyncMock(return_value={"current_user_message": message})


async def _run_sync_turn(
    orch: ChatOrchestrator,
    result: Any,
    message: str = "What is the weather in Tel Aviv?",
) -> Any:
    """Drive ``chat()`` through the plain (non-streaming) sync path."""
    _stub_context_enrichment(orch, message)
    orch._process_sync_chat = AsyncMock(return_value=result)

    return await orch.chat(
        message=message,
        user_id=USER_ID,
        session_id=SESSION_ID,
        request_id=REQUEST_ID,
        stream=False,
    )


async def _drain_stream(orch: ChatOrchestrator) -> List[Dict[str, Any]]:
    """Consume the streaming generator to exhaustion, the way a client does."""
    message = "Summarize the quarterly report."
    events: List[Dict[str, Any]] = []
    generator = orch._create_stream_generator(
        enhanced_message=f"=== CURRENT REQUEST ===\n{message}",
        original_message=message,
        agent_name=None,
        user_id=USER_ID,
        session_id=SESSION_ID,
        request_id=REQUEST_ID,
        use_async=None,
        webhook_url=None,
    )
    async for event in generator:
        events.append(event)
    return events


def _start_streaming_turn(orch: ChatOrchestrator, tracker: RequestTracker) -> None:
    """Register the turn and stand in for the streaming producer."""

    async def _emit_and_answer(**kwargs):
        # Mirrors overlord._process_sync_chat, which emits its own terminal
        # "completed" event before returning.
        streaming_manager.emit_event(REQUEST_ID, "content", STREAM_ANSWER)
        streaming_manager.emit_event(REQUEST_ID, "completed", STREAM_ANSWER)
        return MuxiResponse(role="assistant", content=STREAM_ANSWER)

    orch._process_sync_chat = AsyncMock(side_effect=_emit_and_answer)


@pytest.fixture
def tracker() -> RequestTracker:
    # Short stale timeout so the reaper can be exercised without waiting 600s.
    return RequestTracker(completed_ttl=1.0, stale_timeout=0.01)


@pytest.fixture
def streaming_turn(tracker):
    """A request registered as PROCESSING with streaming enabled."""
    streaming.enable_streaming(REQUEST_ID, USER_ID, SESSION_ID)
    yield
    streaming.disable_streaming(REQUEST_ID)


async def test_sync_chat_turn_marks_request_completed(tracker):
    """A finished sync turn reports COMPLETED with its content as the result."""
    orch = _make_orchestrator(tracker)

    await _run_sync_turn(orch, MuxiResponse(role="assistant", content="It is 29C and sunny."))

    state = await tracker.get_request(REQUEST_ID)
    assert state is not None
    assert state.status == RequestStatus.COMPLETED
    assert state.result == "It is 29C and sunny."
    assert state.end_time is not None


async def test_stale_reaper_leaves_completed_sync_turn_alone(tracker):
    """The stale reaper no longer rewrites a finished sync turn to FAILED."""
    orch = _make_orchestrator(tracker)

    await _run_sync_turn(orch, MuxiResponse(role="assistant", content="Done."))

    # Backdate well past the stale timeout -- before the fix, a turn still
    # sitting in PROCESSING was flipped to FAILED at this point.
    state = await tracker.get_request(REQUEST_ID)
    state.start_time = time.time() - 3600

    await tracker.cleanup_expired()

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.COMPLETED
    assert state.error is None


async def test_completed_sync_turn_respects_completed_ttl(tracker):
    """The completed entry is purged once the completed-entry TTL elapses."""
    orch = _make_orchestrator(tracker)

    await _run_sync_turn(orch, MuxiResponse(role="assistant", content="Done."))

    state = await tracker.get_request(REQUEST_ID)
    state.end_time = time.time() - (tracker.completed_ttl + 1.0)

    purged = await tracker.cleanup_expired()

    assert purged == 1
    assert await tracker.get_request(REQUEST_ID) is None


async def test_async_handoff_is_not_marked_completed(tracker):
    """A turn handed off to the background path keeps its PROCESSING status."""
    orch = _make_orchestrator(tracker)

    await _run_sync_turn(
        orch,
        {"status": "processing", "request_id": REQUEST_ID, "workflow_id": "wf_1"},
    )

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.PROCESSING


async def test_cancelled_turn_is_not_marked_completed(tracker):
    """A cooperatively cancelled turn is recorded CANCELLED, not COMPLETED."""
    orch = _make_orchestrator(tracker)

    await _run_sync_turn(
        orch,
        MuxiResponse(
            role="assistant",
            content="",
            metadata={"cancelled": True, "request_id": REQUEST_ID},
        ),
    )

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.CANCELLED


@pytest.mark.parametrize(
    "metadata",
    [
        # Clarification question (overlord clarification system)
        {"clarification": True, "mode": "ambiguous"},
        # Workflow plan awaiting approval
        {"workflow_id": "wf_1", "approval_required": True, "requires_user_response": True},
        # Missing-credential redirect (overlord.py:9642). The default
        # "redirect" mode sets clarification_requested to False, so the
        # guard has to catch it on the sibling clarification_type key.
        {
            "clarification_requested": False,
            "clarification_type": "missing_credential",
            "credential_mode": "redirect",
            "service": "github",
        },
        # Agent-initiated clarification (overlord.py:11823) -- carries neither
        # "clarification" nor "clarification_type"
        {"requires_clarification": True, "clarification_source": "agent_request"},
        # Agent response flagged as needing more information
        {"needs_clarification": True, "clarification_type": "information_request"},
        # Direct credential request (overlord.py:8654), which used to return
        # a response with no metadata at all and so could not be recognised
        {
            "clarification_type": "credential",
            "credential_mode": "redirect",
            "service": "github",
        },
    ],
    ids=[
        "clarification",
        "approval",
        "credential_redirect",
        "agent_request",
        "agent_needs_info",
        "credential_request",
    ],
)
async def test_interactive_turn_is_not_marked_completed(tracker, metadata):
    """A turn awaiting a further user response is not a completed turn.

    These turns store pending interaction state and reuse the same
    request_id on the follow-up turn, so reporting the question as a
    final result would be wrong.
    """
    orch = _make_orchestrator(tracker)

    await _run_sync_turn(
        orch,
        MuxiResponse(role="assistant", content="Which repository?", metadata=metadata),
    )

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.PROCESSING
    assert state.result is None


async def test_streaming_chat_turn_marks_request_completed(tracker, streaming_turn):
    """A finished streaming turn reports COMPLETED once the stream terminates."""
    orch = _make_orchestrator(tracker)
    await tracker.track_request(REQUEST_ID, _processing_state())
    _start_streaming_turn(orch, tracker)

    events = await _drain_stream(orch)

    assert "completed" in [event["type"] for event in events]

    state = await tracker.get_request(REQUEST_ID)
    assert state is not None
    assert state.status == RequestStatus.COMPLETED
    assert state.result == STREAM_ANSWER
    assert state.end_time is not None


async def test_stale_reaper_leaves_completed_streaming_turn_alone(tracker, streaming_turn):
    """The stale reaper no longer rewrites a finished streaming turn to FAILED."""
    orch = _make_orchestrator(tracker)
    await tracker.track_request(REQUEST_ID, _processing_state())
    _start_streaming_turn(orch, tracker)

    await _drain_stream(orch)

    state = await tracker.get_request(REQUEST_ID)
    state.start_time = time.time() - 3600

    await tracker.cleanup_expired()

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.COMPLETED
    assert state.error is None
