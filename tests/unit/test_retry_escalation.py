"""Async retry escalation ("the honest loop") -- PRD: async-retry-escalation.

A terminal sync failure converts into a bounded background retry chain
instead of a bare error: the caller receives a fixed protocol message, the
tracker entry stays PROCESSING with an ``escalated`` marker, and each
background attempt replans (via the ReplanningCoordinator machinery) and
executes under the same request_id, ending in a result or an honest,
structured give-up report.

These tests pin: the escalation gate matrix (every never-escalate rule),
attempt accounting (the failed sync attempt counts), idle-hang detection,
the stuck short-circuit, the deadline-from-second-async-attempt clock,
terminal state mapping, webhook payload + HMAC signature correctness with
delivery-failure isolation, report retrieval through GET /v1/requests/{id},
the stale-reaper exemption, and event emissions. Everything is
deterministic -- no LLM anywhere.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_lib
import json
import time
from types import MethodType, SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest
from fastapi import FastAPI

from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.datatypes.task_status import TaskStatus
from muxi.runtime.datatypes.workflow import SubTask, Workflow, WorkflowStatus
from muxi.runtime.formation.background.request_tracker import (
    RequestState,
    RequestStatus,
    RequestTracker,
)
from muxi.runtime.formation.background.webhook_manager import WebhookManager
from muxi.runtime.formation.overlord.chat_orchestrator import (
    PENDING_INTERACTION_KEYS,
    ChatOrchestrator,
)
from muxi.runtime.formation.overlord.retry_escalation import (
    RetryAsyncConfig,
    RetryAsyncConfigError,
    RetryEscalationCoordinator,
)
from muxi.runtime.formation.server.routes.client.requests import router
from muxi.runtime.formation.workflow.replanning import ReplanningError
from muxi.runtime.services import observability

CLIENT_KEY = "client-key-for-tests"
USER = "user1"
REQ = "req_escalation_test"


# ----------------------------------------------------------------------
# Fixtures / helpers
# ----------------------------------------------------------------------


def make_failed_workflow(error: str = "connection refused", description: str = "call the tool"):
    task = SubTask(
        id="task_1",
        description=description,
        required_capabilities=["general"],
        status=TaskStatus.FAILED,
        error_message=error,
    )
    return Workflow(
        id="wrk_failed_1",
        user_request="do the thing",
        tasks={"task_1": task},
        status=WorkflowStatus.FAILED,
    )


def make_plan(workflow_id: str = "wrk_replan_1", description: str = "different approach"):
    task = SubTask(
        id="task_1",
        description=description,
        required_capabilities=["general"],
    )
    return Workflow(
        id=workflow_id,
        user_request="do the thing",
        tasks={"task_1": task},
    )


HANG = "hang"  # FakeReplanner sentinel: planning stalls forever


class FakeReplanner:
    """Deterministic stand-in for the chain's ReplanningCoordinator."""

    def __init__(self, outcomes: List[Any]):
        # Each outcome is a Workflow (returned), an Exception (raised), or
        # the HANG sentinel (awaits forever -- a stalled decomposer).
        self.outcomes = list(outcomes)
        self.calls: List[Workflow] = []

    async def generate_replan(self, workflow, context=None):
        self.calls.append(workflow)
        outcome = self.outcomes.pop(0)
        if outcome is HANG:
            await asyncio.Event().wait()  # never resolves
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeWebhookManager:
    def __init__(self, succeed: bool = True, raise_error: bool = False):
        self.succeed = succeed
        self.raise_error = raise_error
        self.calls: List[Dict[str, Any]] = []

    async def deliver_signed_payload(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_error:
            raise RuntimeError("webhook transport exploded")
        return self.succeed


def make_overlord(**overrides) -> SimpleNamespace:
    overlord = SimpleNamespace(
        request_tracker=RequestTracker(),
        active_agent_tracker=SimpleNamespace(overlord_shutting_down=False),
        task_decomposer=object(),
        workflow_config=None,
        notification_router=None,
        captains_log=None,
        webhook_manager=FakeWebhookManager(),
        client_api_key=CLIENT_KEY,
        formation_id="test-formation",
        is_multi_user=False,
    )
    overlord._create_tracked_task = lambda coro, name=None: asyncio.create_task(coro, name=name)
    overlord.get_workflow_status = lambda workflow_id: None

    async def _execute_workflow(**kwargs):  # default: attempts fail
        return MuxiResponse(
            role="assistant",
            content="workflow failed",
            metadata={"workflow_status": "failed", "error": "still broken"},
        )

    overlord._execute_workflow = _execute_workflow
    for key, value in overrides.items():
        setattr(overlord, key, value)
    return overlord


async def track_processing(
    overlord, request_id: str = REQ, webhook_url: Optional[str] = None
) -> RequestState:
    state = RequestState(
        id=request_id,
        status=RequestStatus.PROCESSING,
        start_time=time.time(),
        original_message="do the thing",
        user_id=USER,
        session_id="sess_1",
        webhook_url=webhook_url,
    )
    await overlord.request_tracker.track_request(request_id, state)
    return state


def make_coordinator(
    overlord, replanner: Optional[FakeReplanner] = None, **config_kwargs
) -> RetryEscalationCoordinator:
    coordinator = RetryEscalationCoordinator(overlord, RetryAsyncConfig(**config_kwargs))
    if replanner is not None:
        coordinator._make_replanner = lambda: replanner
    return coordinator


async def wait_for_chain(coordinator: RetryEscalationCoordinator, request_id: str = REQ):
    chain = coordinator._chains.get(request_id)
    if chain is not None and chain.task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(chain.task), timeout=10.0)
        except asyncio.CancelledError:
            pass


# ----------------------------------------------------------------------
# Configuration parsing (PRD section 8)
# ----------------------------------------------------------------------


def test_config_defaults():
    config = RetryAsyncConfig.from_formation_data(None)
    assert config.enabled is True
    assert config.max_attempts == 2
    assert config.attempt_idle_timeout_seconds == 900.0
    assert config.deadline_seconds is None


def test_config_parses_durations():
    config = RetryAsyncConfig.from_formation_data(
        {"enabled": True, "max_attempts": 3, "attempt_idle_timeout": "30s", "deadline": "2h"}
    )
    assert config.attempt_idle_timeout_seconds == 30.0
    assert config.deadline_seconds == 7200.0


@pytest.mark.parametrize(
    "data",
    [
        {"attempt_idle_timeout": "soon"},
        {"attempt_idle_timeout": -5},
        {"deadline": "0s"},
        {"enabled": "yes"},
        {"unknown_knob": 1},
        {"attempt_idle_timeout": True},
    ],
)
def test_config_rejects_malformed_values(data):
    with pytest.raises(RetryAsyncConfigError):
        RetryAsyncConfig.from_formation_data(data)


def test_config_rejects_out_of_range_max_attempts():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RetryAsyncConfig.from_formation_data({"max_attempts": 0})


# ----------------------------------------------------------------------
# Escalation gate matrix (PRD section 5)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_allows_retryable_failure():
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text="connection refused")
    assert should, reason


@pytest.mark.asyncio
async def test_gate_blocks_when_disabled():
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord, enabled=False)
    should, reason = await coordinator.should_escalate(REQ, error_text="connection refused")
    assert not should
    assert "enabled" in reason


@pytest.mark.asyncio
async def test_gate_blocks_without_request_id():
    coordinator = make_coordinator(make_overlord())
    should, _ = await coordinator.should_escalate(None, error_text="boom")
    assert not should


@pytest.mark.asyncio
async def test_gate_blocks_during_shutdown():
    overlord = make_overlord(active_agent_tracker=SimpleNamespace(overlord_shutting_down=True))
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text="boom")
    assert not should
    assert "shutting down" in reason


@pytest.mark.asyncio
async def test_gate_blocks_recursive_escalation():
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    coordinator._chains[REQ] = SimpleNamespace()  # chain already running
    should, reason = await coordinator.should_escalate(REQ, error_text="boom")
    assert not should
    assert "already" in reason


@pytest.mark.asyncio
async def test_gate_blocks_user_cancellation_flag():
    overlord = make_overlord()
    await track_processing(overlord)
    await overlord.request_tracker.mark_cancelled(REQ)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text="boom")
    assert not should
    assert "cancelled" in reason


@pytest.mark.asyncio
async def test_gate_blocks_cancelled_status():
    overlord = make_overlord()
    await track_processing(overlord)
    await overlord.request_tracker.update_request(REQ, RequestStatus.CANCELLED)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text="boom")
    assert not should
    assert "cancelled" in reason


@pytest.mark.asyncio
async def test_gate_blocks_cancelled_metadata():
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(
        REQ, error_text="boom", metadata={"cancelled": True}
    )
    assert not should
    assert "cancelled" in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("key", PENDING_INTERACTION_KEYS)
async def test_gate_blocks_every_pending_interaction_key(key):
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text="boom", metadata={key: True})
    assert not should
    assert "pending interaction" in reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_text",
    [
        "401 Unauthorized",
        "permission denied for this scope",
        "invalid api key provided",
        "credential missing for service",
    ],
)
async def test_gate_blocks_non_replannable_failures(error_text):
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text=error_text)
    assert not should
    assert "non_replannable" in reason


@pytest.mark.asyncio
async def test_gate_blocks_without_decomposer():
    overlord = make_overlord(task_decomposer=None)
    await track_processing(overlord)
    coordinator = make_coordinator(overlord)
    should, reason = await coordinator.should_escalate(REQ, error_text="boom")
    assert not should
    assert "decomposer" in reason


# ----------------------------------------------------------------------
# Escalation response + tracker marker
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_keeps_tracker_processing_with_marker():
    overlord = make_overlord()
    state = await track_processing(overlord)
    # First replan succeeds and its execution succeeds -> chain finishes,
    # but the assertions below run before the chain resolves.
    replanner = FakeReplanner([make_plan()])

    async def _succeed(**kwargs):
        await asyncio.sleep(0.2)
        return MuxiResponse(role="assistant", content="done", metadata={})

    overlord._execute_workflow = _succeed
    coordinator = make_coordinator(overlord, replanner=replanner)

    response = await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do the thing",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )

    assert response is not None
    assert response.metadata["escalated"] is True
    assert response.metadata["request_id"] == REQ
    # The protocol message is deterministic text, never persona-styled.
    assert response.content.startswith("This has failed.")
    assert REQ in response.content
    # Tracker: still PROCESSING, escalated marker set, chain task attached.
    assert state.status == RequestStatus.PROCESSING
    assert state.escalated is True
    assert state.task_ref is not None
    await wait_for_chain(coordinator)


@pytest.mark.asyncio
async def test_escalation_message_names_delivery_mode():
    # Polling (no webhook, no router)
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])
    coordinator = make_coordinator(overlord, replanner=replanner)
    response = await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    assert f"GET /v1/requests/{REQ}" in response.content
    await wait_for_chain(coordinator)

    # Webhook (request carried one)
    overlord2 = make_overlord()
    await track_processing(overlord2, request_id="req_2", webhook_url="http://sink/hook")
    coordinator2 = make_coordinator(overlord2, replanner=FakeReplanner([make_plan()]))
    response2 = await coordinator2.maybe_escalate(
        "req_2",
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    assert "webhook" in response2.content.lower()
    await wait_for_chain(coordinator2, "req_2")


@pytest.mark.asyncio
async def test_gate_returns_failure_untouched_when_blocked():
    overlord = make_overlord()
    await track_processing(overlord)
    coordinator = make_coordinator(overlord, enabled=False)
    response = await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
    )
    assert response is None
    state = await overlord.request_tracker.get_request(REQ)
    assert state.escalated is False


# ----------------------------------------------------------------------
# Attempt accounting (the failed sync attempt counts)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_exhausted_counts_sync_attempt():
    overlord = make_overlord()
    await track_processing(overlord)
    # max_attempts=2 async attempts; every attempt fails.
    replanner = FakeReplanner([make_plan("wrk_r1"), make_plan("wrk_r2", "third approach")])
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=2)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    report = state.result
    assert report["state"] == "budget_exhausted"
    # 1 sync + exactly max_attempts async attempts, numbered from 1.
    assert [a["attempt"] for a in report["attempts"]] == [1, 2, 3]
    assert [a["kind"] for a in report["attempts"]] == ["sync", "async", "async"]
    assert len(replanner.calls) == 2  # never a third async attempt
    # Structured report carries per-attempt reasons and the unblock hint.
    assert report["attempts"][0]["failure_reason"] == "connection refused"
    assert report["what_would_unblock"]


@pytest.mark.asyncio
async def test_attempt_success_ends_chain_achieved():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])

    async def _succeed(**kwargs):
        return MuxiResponse(role="assistant", content="here is your answer", metadata={})

    overlord._execute_workflow = _succeed
    coordinator = make_coordinator(overlord, replanner=replanner)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.COMPLETED
    assert state.result == "here is your answer"
    assert REQ not in coordinator._chains


# ----------------------------------------------------------------------
# Stuck short-circuit (similarity-rejected + unchanged failure signature)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stuck_short_circuit_leaves_budget_unspent():
    overlord = make_overlord()
    await track_processing(overlord)
    similar = ReplanningError(
        "Generated plan is too similar to the failed plan (similarity 0.90 >= 0.70)"
    )
    replanner = FakeReplanner([similar, similar])
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=5)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    report = state.result
    assert report["state"] == "stuck"
    # The first similarity rejection consumed one attempt; the second, with
    # an unchanged failure signature, short-circuited: 3 of 5 async
    # attempts deliberately unspent.
    assert len(report["attempts"]) == 2
    assert len(replanner.calls) == 2


@pytest.mark.asyncio
async def test_replanning_failure_consumes_attempt_but_chain_continues():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([ReplanningError("Replanning timed out after 30s"), make_plan()])

    async def _succeed(**kwargs):
        return MuxiResponse(role="assistant", content="recovered", metadata={})

    overlord._execute_workflow = _succeed
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=2)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.COMPLETED
    assert state.result == "recovered"


# ----------------------------------------------------------------------
# Planning is bounded too: a stalled decomposer cannot hang the chain
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stalled_replanner_counts_attempt_then_chain_recovers():
    """Planning runs under attempt_idle_timeout: a hung decomposer fails the
    attempt at the bound and normal accounting proceeds."""
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([HANG, make_plan()])

    async def _succeed(**kwargs):
        return MuxiResponse(role="assistant", content="recovered after stall", metadata={})

    overlord._execute_workflow = _succeed
    coordinator = make_coordinator(
        overlord, replanner=replanner, max_attempts=2, attempt_idle_timeout_seconds=0.15
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    chain = coordinator._chains[REQ]
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.COMPLETED
    assert state.result == "recovered after stall"
    # The stalled planning consumed one attempt with an honest reason and
    # carried the failure signature forward.
    stalled = chain.attempts[1]
    assert "replanning timed out" in stalled.failure_reason
    assert stalled.failure_signature == chain.attempts[0].failure_signature


@pytest.mark.asyncio
async def test_stalled_replanner_on_final_attempt_exhausts_budget():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([HANG])
    coordinator = make_coordinator(
        overlord, replanner=replanner, max_attempts=1, attempt_idle_timeout_seconds=0.15
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED  # never left hanging PROCESSING
    report = state.result
    assert report["state"] == "budget_exhausted"
    assert len(report["attempts"]) == 2
    assert "replanning timed out" in report["attempts"][1]["failure_reason"]


@pytest.mark.asyncio
async def test_deadline_expiring_mid_planning_ends_chain():
    """Once the deadline clock runs, replanning may not outlive it."""
    overlord = make_overlord()
    await track_processing(overlord)
    # Attempt 1 plans + executes fast and fails; attempt 2's planning hangs.
    replanner = FakeReplanner([make_plan("wrk_r1"), HANG])
    coordinator = make_coordinator(
        overlord,
        replanner=replanner,
        max_attempts=3,
        deadline_seconds=0.2,
        attempt_idle_timeout_seconds=3600,  # huge: the deadline must cut it
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    chain = coordinator._chains[REQ]
    await asyncio.wait_for(asyncio.shield(chain.task), timeout=10.0)

    assert chain.deadline_started_at is not None
    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    report = state.result
    assert report["state"] == "budget_exhausted"
    assert "deadline exceeded during replanning" in report["detail"]
    assert len(replanner.calls) == 2  # attempt 3 never planned


# ----------------------------------------------------------------------
# Terminal guarantee: no exit path leaves the entry PROCESSING+escalated
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chain_exception_ends_failed_never_processing():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])

    async def _explode(**kwargs):
        raise RuntimeError("executor blew up unexpectedly")

    overlord._execute_workflow = _explode
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=1)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    chain = coordinator._chains[REQ]
    await wait_for_chain(coordinator)

    assert chain.task.done()
    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED  # never PROCESSING after the task ends
    assert "executor blew up unexpectedly" in state.result["detail"]
    assert REQ not in coordinator._chains


@pytest.mark.asyncio
async def test_terminal_guard_covers_failing_terminal_handler():
    """Even a crash inside the terminal handler itself cannot leave the
    entry PROCESSING: the outermost finally-guard force-fails it."""
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=1)

    async def _broken_finish(chain, state, detail):
        raise RuntimeError("terminal handler itself is broken")

    coordinator._finish_failed = _broken_finish

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    chain = coordinator._chains.get(REQ)
    try:
        await asyncio.wait_for(asyncio.shield(chain.task), timeout=10.0)
    except RuntimeError:
        pass  # the handler's crash propagates out of the chain task

    assert chain.task.done()
    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    report = state.result
    assert "without recording a terminal state" in report["detail"]
    assert REQ not in coordinator._chains


# ----------------------------------------------------------------------
# Idle-hang detection (liveness, not duration)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idle_attempt_is_declared_hung_and_counted():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan("wrk_r1"), make_plan("wrk_r2", "other way")])

    async def _hang_forever(**kwargs):
        await asyncio.sleep(3600)  # emits no observability events

    overlord._execute_workflow = _hang_forever
    coordinator = make_coordinator(
        overlord, replanner=replanner, max_attempts=2, attempt_idle_timeout_seconds=0.15
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    report = state.result
    assert report["state"] == "budget_exhausted"
    hung_reasons = [a["failure_reason"] for a in report["attempts"][1:]]
    assert all("hung" in reason for reason in hung_reasons)


@pytest.mark.asyncio
async def test_active_attempt_is_not_hung_regardless_of_duration():
    """Liveness over duration: activity resets the idle clock (PRD sec 4)."""
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])

    async def _slow_but_alive(**kwargs):
        # Runs 6x the idle timeout while emitting observability events --
        # observe() stamps the activity watch even when emission itself is
        # disabled/filtered.
        for _ in range(12):
            await asyncio.sleep(0.05)
            observability.observe(
                event_type="response.retry.attempt",
                data={"heartbeat": True},
                description="attempt progress",
            )
        return MuxiResponse(role="assistant", content="slow success", metadata={})

    overlord._execute_workflow = _slow_but_alive
    coordinator = make_coordinator(
        overlord, replanner=replanner, max_attempts=1, attempt_idle_timeout_seconds=0.4
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.COMPLETED
    assert state.result == "slow success"


# ----------------------------------------------------------------------
# Deadline: clock starts when the SECOND async attempt begins
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deadline_spares_first_async_attempt():
    """Attempt 1 may exceed the deadline freely; the clock has not started."""
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])

    async def _slower_than_deadline(**kwargs):
        await asyncio.sleep(0.3)  # 3x the configured deadline
        return MuxiResponse(role="assistant", content="unhurried win", metadata={})

    overlord._execute_workflow = _slower_than_deadline
    coordinator = make_coordinator(
        overlord, replanner=replanner, max_attempts=2, deadline_seconds=0.1
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.COMPLETED
    assert state.result == "unhurried win"


@pytest.mark.asyncio
async def test_deadline_bounds_the_chain_tail():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner(
        [make_plan("wrk_r1"), make_plan("wrk_r2", "other way"), make_plan("wrk_r3", "yet another")]
    )
    attempt_counter = {"n": 0}

    async def _fail_then_stall(**kwargs):
        attempt_counter["n"] += 1
        if attempt_counter["n"] == 1:
            return MuxiResponse(
                role="assistant",
                content="failed",
                metadata={"workflow_status": "failed", "error": "still broken"},
            )
        await asyncio.sleep(3600)

    overlord._execute_workflow = _fail_then_stall
    coordinator = make_coordinator(
        overlord,
        replanner=replanner,
        max_attempts=3,
        deadline_seconds=0.2,
        attempt_idle_timeout_seconds=3600,
    )

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    chain = coordinator._chains[REQ]
    await wait_for_chain(coordinator)

    # The clock started when async attempt 2 began, and the stalled second
    # attempt was cut at the deadline -- not by the (huge) idle timeout.
    assert chain.deadline_started_at is not None
    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    assert state.result["state"] == "budget_exhausted"
    assert attempt_counter["n"] == 2  # attempt 3 never started


# ----------------------------------------------------------------------
# Terminal mapping: impossible (named blocker) and abandoned
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_blocker_ends_chain_impossible():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])
    blocker_workflow = make_failed_workflow(
        error="permission denied: formation lacks the Stripe refund scope"
    )

    async def _blocked(**kwargs):
        return MuxiResponse(
            role="assistant",
            content="failed",
            metadata={
                "workflow_status": "failed",
                "error": "permission denied: formation lacks the Stripe refund scope",
            },
        )

    overlord._execute_workflow = _blocked
    overlord.get_workflow_status = lambda workflow_id: blocker_workflow
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=5)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="refund the invoice",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED
    report = state.result
    assert report["state"] == "impossible"
    assert "Stripe refund scope" in report["detail"]
    assert "Stripe refund scope" in report["what_would_unblock"]
    assert len(replanner.calls) == 1  # budget deliberately unspent


@pytest.mark.asyncio
async def test_delete_mid_chain_ends_abandoned():
    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])
    started = asyncio.Event()

    async def _slow(**kwargs):
        started.set()
        await asyncio.sleep(3600)

    overlord._execute_workflow = _slow
    coordinator = make_coordinator(overlord, replanner=replanner)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)
    # DELETE /v1/requests/{id} semantics: cooperative flag on the tracker.
    marked = await overlord.request_tracker.mark_cancelled(REQ)
    assert marked  # PROCESSING is cancellable mid-chain (#314 semantics)
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.CANCELLED
    assert state.result["state"] == "abandoned"
    # No push delivery for abandoned -- the DELETE response was the ack.
    assert overlord.webhook_manager.calls == []


# ----------------------------------------------------------------------
# Webhook delivery: payload shape, HMAC signature, failure isolation
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_payload_shape_and_hmac_signature():
    overlord = make_overlord()
    await track_processing(overlord, webhook_url="http://sink.test/hook")

    # Use the real WebhookManager with a captured transport.
    captured: Dict[str, Any] = {}
    manager = WebhookManager(default_retries=0, signing_secret="admin-secret")

    async def _capture(self, *, url, method, headers, body, basic_auth, timeout):
        captured.update(url=url, headers=headers, body=body)
        return True, None

    manager._send_raw = MethodType(_capture, manager)
    overlord.webhook_manager = manager

    replanner = FakeReplanner([make_plan("wrk_r1")])
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=1)
    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    assert captured["url"] == "http://sink.test/hook"
    payload = json.loads(captured["body"])
    # PRD section 7 payload: {request_id, state, result | report, attempts, timestamp}
    assert payload["request_id"] == REQ
    assert payload["state"] == "budget_exhausted"
    assert payload["attempts"] == 2  # sync + 1 async
    assert "timestamp" in payload
    assert payload["report"]["attempts"][0]["kind"] == "sync"

    # Signature: HMAC-SHA256 with the formation's CLIENT key over
    # "{timestamp}.{canonical json}" -- verifiable by the receiver.
    signature_header = captured["headers"]["X-Muxi-Signature"]
    parts = dict(item.split("=", 1) for item in signature_header.split(","))
    message = f"{parts['t']}.".encode() + captured["body"].encode()
    expected = hmac_lib.new(CLIENT_KEY.encode(), message, hashlib.sha256).hexdigest()
    assert parts["v1"] == expected
    assert captured["headers"]["X-Muxi-Timestamp"] == parts["t"]


@pytest.mark.asyncio
async def test_webhook_delivery_failure_never_changes_chain_state():
    overlord = make_overlord(webhook_manager=FakeWebhookManager(raise_error=True))
    await track_processing(overlord, webhook_url="http://sink.test/hook")
    replanner = FakeReplanner([make_plan()])
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=1)

    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    state = await overlord.request_tracker.get_request(REQ)
    assert state.status == RequestStatus.FAILED  # terminal state untouched
    assert state.result["state"] == "budget_exhausted"


# ----------------------------------------------------------------------
# GET /v1/requests/{id}: the give-up report rides the tracker
# ----------------------------------------------------------------------


def _make_app(overlord) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.formation = SimpleNamespace(
        _overlord=overlord,
        _api_keys={"client": CLIENT_KEY, "admin": "admin-key-for-tests"},
    )
    return app


@pytest.mark.asyncio
async def test_requests_route_returns_report_for_escalated_failed():
    overlord = make_overlord()
    report = {
        "state": "budget_exhausted",
        "detail": "all attempts failed",
        "attempts": [{"attempt": 1, "kind": "sync", "plan_summary": "p", "failure_reason": "f"}],
        "what_would_unblock": "fix the endpoint",
    }
    state = RequestState(
        id=REQ,
        status=RequestStatus.FAILED,
        start_time=time.time(),
        user_id="0",
        result=report,
        error="async retry gave up (budget_exhausted): all attempts failed",
    )
    state.escalated = True
    state.end_time = time.time()
    await overlord.request_tracker.track_request(REQ, state)

    app = _make_app(overlord)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/requests/{REQ}",
            headers={"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-ID": USER},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["escalated"] is True
    assert data["report"] == report
    assert "result" not in data  # result stays a COMPLETED-only field


@pytest.mark.asyncio
async def test_requests_route_plain_failed_has_no_report():
    overlord = make_overlord()
    state = RequestState(
        id=REQ,
        status=RequestStatus.FAILED,
        start_time=time.time(),
        user_id="0",
        error="boom",
    )
    state.end_time = time.time()
    await overlord.request_tracker.track_request(REQ, state)

    app = _make_app(overlord)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/requests/{REQ}",
            headers={"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-ID": USER},
        )
    data = response.json()["data"]
    assert "report" not in data
    assert "escalated" not in data


# ----------------------------------------------------------------------
# Event emissions (PRD section 10)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chain_emits_escalated_attempt_and_terminal_events(monkeypatch):
    events: List[Tuple[str, Dict[str, Any]]] = []
    real_observe = observability.observe

    def _capture(event_type, level=None, data=None, description="", **kwargs):
        name = event_type.value if hasattr(event_type, "value") else str(event_type)
        events.append((name, data or {}))
        return real_observe(event_type, data=data, description=description)

    import muxi.runtime.formation.overlord.retry_escalation as escalation_module

    monkeypatch.setattr(escalation_module.observability, "observe", _capture)

    overlord = make_overlord()
    await track_processing(overlord)
    replanner = FakeReplanner([make_plan()])
    coordinator = make_coordinator(overlord, replanner=replanner, max_attempts=1)
    await coordinator.maybe_escalate(
        REQ,
        user_id=USER,
        session_id="sess_1",
        original_message="do it",
        error_text="connection refused",
        failed_workflow=make_failed_workflow(),
    )
    await wait_for_chain(coordinator)

    names = [name for name, _ in events]
    assert "response.retry.escalated" in names
    assert "response.retry.attempt" in names
    assert "response.retry.terminal" in names
    # Every retry event carries the request_id for end-to-end tracing.
    for name, data in events:
        if name.startswith("response.retry."):
            assert data["request_id"] == REQ
    terminal = next(data for name, data in events if name == "response.retry.terminal")
    assert terminal["state"] == "budget_exhausted"
    assert terminal["attempts"] == 2


# ----------------------------------------------------------------------
# Stale reaper: escalated chains are exempt while their task is alive
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reaper_spares_live_escalated_chain_but_reaps_dead_one():
    tracker = RequestTracker(stale_timeout=0.01)

    async def _alive():
        await asyncio.sleep(3600)

    live_task = asyncio.create_task(_alive())
    live = RequestState(
        id="req_live",
        status=RequestStatus.PROCESSING,
        start_time=time.time() - 100,
        task_ref=live_task,
    )
    live.escalated = True
    dead = RequestState(
        id="req_dead",
        status=RequestStatus.PROCESSING,
        start_time=time.time() - 100,
    )
    dead.escalated = True  # escalated but its chain task is gone (restart)
    plain = RequestState(
        id="req_plain",
        status=RequestStatus.PROCESSING,
        start_time=time.time() - 100,
    )
    await tracker.track_request("req_live", live)
    await tracker.track_request("req_dead", dead)
    await tracker.track_request("req_plain", plain)

    await tracker.cleanup_expired()

    assert (await tracker.get_request("req_live")).status == RequestStatus.PROCESSING
    assert (await tracker.get_request("req_dead")).status == RequestStatus.FAILED
    assert (await tracker.get_request("req_plain")).status == RequestStatus.FAILED
    live_task.cancel()


# ----------------------------------------------------------------------
# _mark_turn_terminal: escalated turns stay PROCESSING
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_turn_terminal_leaves_escalated_turn_processing():
    overlord = make_overlord()
    state = await track_processing(overlord)
    state.escalated = True
    orchestrator = ChatOrchestrator(overlord)

    escalation_response = MuxiResponse(
        role="assistant",
        content="This has failed. I'm going to retry...",
        metadata={"escalated": True, "request_id": REQ},
    )
    await orchestrator._mark_turn_terminal(REQ, escalation_response)

    refreshed = await overlord.request_tracker.get_request(REQ)
    assert refreshed.status == RequestStatus.PROCESSING  # chain owns the terminal


@pytest.mark.asyncio
async def test_mark_turn_terminal_still_completes_ordinary_turns():
    overlord = make_overlord()
    await track_processing(overlord)
    orchestrator = ChatOrchestrator(overlord)
    await orchestrator._mark_turn_terminal(
        REQ, MuxiResponse(role="assistant", content="all done", metadata={})
    )
    refreshed = await overlord.request_tracker.get_request(REQ)
    assert refreshed.status == RequestStatus.COMPLETED
