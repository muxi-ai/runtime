"""
Tests for request-tracker continuity across a dynamic-mode inline
credential collection ("collect") interaction.

Background
----------
PR #315 stopped ordinary chat turns from being left in PROCESSING, but
deliberately excluded turns that end awaiting a further user response
(clarification questions, workflow approvals, credential requests): those
have not finished, so their entry stays PROCESSING and the *follow-up*
turn — which reuses the same ``request_id`` — closes it.

Reusing the request_id is what makes that work, and it depends on the
turn storing pending-clarification state carrying ``request_id``:
``ChatOrchestrator.chat`` reads that state and reuses the id instead of
generating a new one.

The dynamic-credential ``collect`` branch stored no such state. Only the
sibling ``redirect`` branch did. So a collect turn parked its entry in
PROCESSING and the user's token arrived under a brand new request_id:
the original was never closed by anyone and the stale request reaper
rewrote it to FAILED ("Request timed out"), even though the interaction
had continued and completed under the new id.

These tests pin:

* the collect turn stores continuation state carrying its request_id and
  leaves the tracker entry PROCESSING
* the follow-up turn reuses that request_id, and completing the collect
  loop transitions the *original* entry to COMPLETED
* the stale reaper no longer rewrites the interaction to FAILED
* a still-open collect loop (invalid token → retry) keeps the entry
  PROCESSING and keeps the continuation state, while a cancelled loop
  closes both
"""

import time
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.formation.background.request_tracker import RequestStatus, RequestTracker
from muxi.runtime.formation.credentials.handler import CredentialHandler
from muxi.runtime.formation.overlord.chat_orchestrator import (
    PENDING_INTERACTION_KEYS,
    ChatOrchestrator,
    EnhancedMessage,
)
from muxi.runtime.formation.overlord.overlord import (
    CREDENTIAL_COLLECT_PENDING_TYPE,
    Overlord,
)

REQUEST_ID = "req_collect_original"
USER_ID = "0"
SESSION_ID = "sess_collect_test"
SERVICE = "github"
ASK_MESSAGE = "list my private repos"
TOKEN_MESSAGE = "ghp_abc123"
CONTINUATION_ANSWER = "You have 3 private repos."
PENDING_NAMESPACE = "pending_clarifications"


class _FakeKV:
    """Dict-backed stand-in for the buffer-memory KV store.

    Lets the overlord's real ``_get/_set/_delete_pending_clarification*``
    helpers run, so these tests exercise the actual continuation-state
    plumbing rather than a mock of it.
    """

    def __init__(self) -> None:
        self.store: Dict[str, Dict[str, Any]] = {}

    async def kv_get(self, key: str, namespace: str) -> Optional[Dict[str, Any]]:
        return self.store.get(f"{namespace}:{key}")

    async def kv_set(self, key: str, value: Any, ttl: Any, namespace: str) -> None:
        self.store[f"{namespace}:{key}"] = value

    async def kv_delete(self, key: str, namespace: str) -> None:
        self.store.pop(f"{namespace}:{key}", None)


def _make_overlord(tracker: RequestTracker, kv: _FakeKV) -> Overlord:
    """Build a bare ``Overlord`` wired down to the pieces this path touches.

    ``Overlord.__init__`` needs a full formation engine and live services,
    so the instance is built with ``__new__`` and only the collaborators
    ``_process_sync_chat`` reaches on the credential path are attached.
    """
    overlord = Overlord.__new__(Overlord)

    overlord.request_tracker = tracker
    overlord.buffer_memory = kv
    overlord.pending_clarification_namespace = PENDING_NAMESPACE
    overlord.formation_id = "test-formation"
    overlord.is_multi_user = False
    overlord.agents = {}
    overlord.buffer_memory_manager = None
    overlord.long_term_memory = None
    overlord.db_manager = None
    overlord.mcp_service = None

    # Dynamic credential mode with an inline-capable service: the exact
    # configuration that makes handle_credential_request return "collect".
    overlord.formation_config = {"user_credentials": {"mode": "dynamic"}}
    overlord._capability_models = {}  # no LLM -> handler uses its static prompt
    overlord._model_cache = {}

    # Clarification analysis is not what these tests are about: keep the
    # turn on the credential branch and out of the clarification system.
    overlord.clarification = MagicMock()
    overlord._resolve_ui_response_hint = AsyncMock(return_value=None)
    overlord._apply_permission_gate = AsyncMock(return_value=None)
    overlord._ensure_sop_system = MagicMock(return_value=False)
    overlord._should_skip_clarification = AsyncMock(return_value=False)
    overlord.credential_resolver = MagicMock()

    def _create_tracked_task(coro, name: Optional[str] = None):
        coro.close()
        return None

    overlord._create_tracked_task = MagicMock(side_effect=_create_tracked_task)

    overlord.credential_handler = _make_credential_handler(overlord)
    return overlord


def _make_credential_handler(overlord: Overlord) -> CredentialHandler:
    """The real handler, with only its LLM/IO leaves stubbed.

    ``_pending`` bookkeeping stays real: it is the signal the overlord
    reads to decide whether the collect loop is still open, so mocking it
    away would mock away the thing under test.
    """
    handler = CredentialHandler(overlord)

    handler.detect_credential_need = AsyncMock(
        return_value={
            "type": "CREDENTIAL_REQUEST",
            "service": SERVICE,
            "service_id": f"{SERVICE}-mcp",
            "accept_inline": True,
            "auth_type": "bearer",
        }
    )
    handler._is_cancellation = AsyncMock(return_value=False)
    handler._is_help_request = AsyncMock(return_value=False)
    handler._extract_credential_from_text = AsyncMock(return_value=TOKEN_MESSAGE)
    handler.validate_credential = AsyncMock(return_value=True)
    handler._generate_success_message = AsyncMock(return_value="Saved your GitHub token.")
    handler._generate_cancellation_message = AsyncMock(return_value="No problem, cancelled.")
    handler._generate_validation_failure_message = AsyncMock(
        return_value="That token didn't work — mind trying again?"
    )

    overlord.credential_resolver.check_duplicate = AsyncMock(return_value=False)
    overlord.credential_resolver.store_credential = AsyncMock(return_value="stored")
    overlord.credential_resolver.update_credential_name_with_discovery = AsyncMock()

    return handler


def _make_orchestrator(overlord: Overlord) -> ChatOrchestrator:
    """An orchestrator driving the real ``Overlord._process_sync_chat``."""
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    orch.overlord = overlord

    overlord.streaming = False
    overlord.auto_extract_user_info = False
    overlord.async_webhook_url = None
    overlord.async_threshold_seconds = 30
    overlord.observability_manager = MagicMock()

    return orch


async def _run_turn(
    orch: ChatOrchestrator,
    message: str,
    request_id: Optional[str] = None,
) -> MuxiResponse:
    """Drive ``chat()`` through the plain (non-streaming) sync path.

    ``request_id`` is passed only for the opening turn. The follow-up turn
    omits it, exactly as a fresh inbound request does — which is what makes
    the request_id reuse observable.
    """
    enhanced = f"=== CURRENT REQUEST ===\n{message}"
    orch._enhance_message_with_context = AsyncMock(
        return_value=EnhancedMessage(original=message, enhanced=enhanced)
    )
    orch._build_clean_chat_context = AsyncMock(return_value={"current_user_message": message})

    return await orch.chat(
        message=message,
        user_id=USER_ID,
        session_id=SESSION_ID,
        request_id=request_id,
        stream=False,
    )


async def _pending_state(kv: _FakeKV) -> Optional[Dict[str, Any]]:
    return kv.store.get(f"{PENDING_NAMESPACE}:{SESSION_ID}")


def _stub_replay(overlord: Overlord) -> Dict[str, Any]:
    """Short-circuit the replay of the original request, capturing its kwargs.

    Once the credential is stored, the collect branch re-enters
    ``_process_sync_chat`` to finally run the request the user asked for.
    That re-entry is the entire rest of the overlord (workflow analysis,
    agent routing, synthesis); these tests only care about the id it runs
    under, so it is answered here. Re-entrancy is the signal: the outer
    call is the turn itself, any nested call is the replay.
    """
    real = overlord._process_sync_chat
    captured: Dict[str, Any] = {}
    depth = {"n": 0}

    async def _process(**kwargs: Any) -> MuxiResponse:
        depth["n"] += 1
        try:
            if depth["n"] > 1:
                captured.update(kwargs)
                return MuxiResponse(role="assistant", content=CONTINUATION_ANSWER)
            return await real(**kwargs)
        finally:
            depth["n"] -= 1

    overlord._process_sync_chat = _process
    return captured


def _pending_interaction_metadata(response: MuxiResponse) -> Dict[str, Any]:
    """The subset of response metadata ``_mark_turn_terminal`` reads.

    ``chat()`` stamps ``session_id`` onto every response, so "no pending
    interaction" is the absence of these keys, not an empty metadata dict.
    """
    metadata = response.metadata or {}
    return {k: v for k, v in metadata.items() if k in PENDING_INTERACTION_KEYS}


@pytest.fixture
def tracker() -> RequestTracker:
    # Short stale timeout so the reaper can be exercised without waiting 600s.
    return RequestTracker(completed_ttl=60.0, stale_timeout=0.01)


@pytest.fixture
def kv() -> _FakeKV:
    return _FakeKV()


@pytest.fixture
def overlord(tracker: RequestTracker, kv: _FakeKV) -> Overlord:
    return _make_overlord(tracker, kv)


@pytest.fixture
def orch(overlord: Overlord) -> ChatOrchestrator:
    return _make_orchestrator(overlord)


async def _ask_for_credential(orch: ChatOrchestrator) -> MuxiResponse:
    """Opening turn: the request needs a credential, so the turn parks."""
    return await _run_turn(orch, ASK_MESSAGE, request_id=REQUEST_ID)


@pytest.mark.asyncio
async def test_collect_turn_parks_request_and_stores_continuation_state(
    orch: ChatOrchestrator, tracker: RequestTracker, kv: _FakeKV
) -> None:
    """The collect turn leaves the entry PROCESSING and records its request_id."""
    response = await _ask_for_credential(orch)

    assert response.metadata["credential_mode"] == "collect"

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.PROCESSING

    # Continuation state is what carries the id to the follow-up turn.
    # Without it (the bug) nothing here was stored at all.
    pending = await _pending_state(kv)
    assert pending is not None
    assert pending["request_id"] == REQUEST_ID
    assert pending["type"] == CREDENTIAL_COLLECT_PENDING_TYPE
    assert pending["service"] == SERVICE


@pytest.mark.asyncio
async def test_credential_follow_up_completes_the_original_request(
    orch: ChatOrchestrator, overlord: Overlord, tracker: RequestTracker, kv: _FakeKV
) -> None:
    """The follow-up runs under the original id and closes that entry."""
    await _ask_for_credential(orch)

    replayed = _stub_replay(overlord)

    response = await _run_turn(orch, TOKEN_MESSAGE)

    # The replayed original request ran under the ORIGINAL request_id.
    assert replayed["request_id"] == REQUEST_ID
    assert CONTINUATION_ANSWER in response.content

    # Nothing signals "still awaiting the user", so the turn is terminal.
    assert _pending_interaction_metadata(response) == {}

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.COMPLETED
    assert state.end_time is not None

    # A finished interaction leaves no continuation state behind, so an
    # unrelated later turn does not inherit this request_id.
    assert await _pending_state(kv) is None


@pytest.mark.asyncio
async def test_stale_reaper_leaves_completed_collect_interaction_alone(
    orch: ChatOrchestrator, overlord: Overlord, tracker: RequestTracker, kv: _FakeKV
) -> None:
    """The reaper no longer rewrites the finished interaction to FAILED."""
    await _ask_for_credential(orch)
    _stub_replay(overlord)

    await _run_turn(orch, TOKEN_MESSAGE)

    # Backdate well past the stale timeout. Before the fix the original
    # entry was still PROCESSING here and got flipped to FAILED.
    state = await tracker.get_request(REQUEST_ID)
    state.start_time = time.time() - 3600

    await tracker.cleanup_expired()

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.COMPLETED
    assert state.error is None


@pytest.mark.asyncio
async def test_invalid_credential_keeps_the_interaction_open(
    orch: ChatOrchestrator, overlord: Overlord, tracker: RequestTracker, kv: _FakeKV
) -> None:
    """A retry turn is still awaiting the user: entry and state both stay."""
    await _ask_for_credential(orch)

    overlord.credential_handler.validate_credential = AsyncMock(return_value=False)

    response = await _run_turn(orch, "not-a-real-token")

    assert response.metadata["credential_mode"] == "collect"

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.PROCESSING

    # Still the same interaction, so the id keeps being carried forward.
    pending = await _pending_state(kv)
    assert pending["request_id"] == REQUEST_ID


@pytest.mark.asyncio
async def test_cancelled_collect_closes_the_request(
    orch: ChatOrchestrator, overlord: Overlord, tracker: RequestTracker, kv: _FakeKV
) -> None:
    """Cancelling the prompt ends the interaction: COMPLETED, state cleared."""
    await _ask_for_credential(orch)

    overlord.credential_handler._is_cancellation = AsyncMock(return_value=True)

    response = await _run_turn(orch, "never mind")

    assert _pending_interaction_metadata(response) == {}

    state = await tracker.get_request(REQUEST_ID)
    assert state.status == RequestStatus.COMPLETED
    assert await _pending_state(kv) is None
