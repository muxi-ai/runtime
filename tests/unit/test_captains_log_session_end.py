"""Unit tests for the Captain's Log session-end digest trigger.

Covers config parsing (default / override / disable), (user, session)
activity stamping at turn intake, the idle sweep (each idle session ends
exactly once, ``session.ended`` is emitted, the user's pending turns are
digested through the same pipeline the daily tick uses), no-double-digest
with the daily tick in either order, failure isolation (requeue on digest
failure, no model keeps turns queued), and the sweep-task lifecycle.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.log import service as service_module
from muxi.runtime.services.memory.log.service import (
    DEFAULT_SESSION_IDLE_MINUTES,
    SESSION_ACTIVITY_CACHE_SIZE,
    CaptainsLogService,
)

FORMATION_ID = "session-end-test-formation"

DIGEST_RESPONSE = (
    "{"
    '"summary": "The user planned the Bluebird launch.",'
    '"decisions": ["Ship on Friday"],'
    '"projects": ["Bluebird"],'
    '"context": "Launch planning.",'
    '"lessons": [],'
    '"entities": [],'
    '"relationships": []'
    "}"
)


class FakeModel:
    def __init__(self, response=DIGEST_RESPONSE):
        self.response = response
        self.calls = 0
        self.prompts = []

    async def generate_text(self, prompt, caching=True):
        self.calls += 1
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/log.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def service(db_manager):
    # 1 minute idle threshold; tests drive the sweep with an explicit
    # ``now`` so nothing sleeps.
    return CaptainsLogService(db_manager, FORMATION_ID, config={"session_idle_minutes": 1})


@pytest.fixture
def events(monkeypatch):
    """Capture observability events emitted by the log service module."""
    captured = []

    def fake_observe(event_type=None, **kwargs):
        captured.append((event_type, kwargs.get("data") or {}))

    monkeypatch.setattr(service_module.observability, "observe", fake_observe)
    return captured


def idle_now(service: CaptainsLogService) -> float:
    """A clock value past the service's idle threshold."""
    return time.time() + service.session_idle_seconds + 1


class TestConfig:
    def test_default_threshold(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID)
        assert service.session_idle_seconds == DEFAULT_SESSION_IDLE_MINUTES * 60.0

    def test_threshold_override(self, service):
        assert service.session_idle_seconds == 60.0

    @pytest.mark.parametrize("value", [0, False])
    def test_disabled_via_zero_or_false(self, db_manager, value):
        service = CaptainsLogService(
            db_manager, FORMATION_ID, config={"session_idle_minutes": value}
        )
        assert service.session_idle_seconds == 0.0


class TestActivityStamping:
    def test_queue_turn_stamps_user_session(self, service):
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        assert ("u1", "s1") in service._session_activity

    def test_missing_session_uses_default_key(self, service):
        service.queue_turn("hello", "hi", user_id="u1")
        assert ("u1", "default") in service._session_activity

    def test_disabled_trigger_does_not_stamp(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"session_idle_minutes": 0})
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        assert not service._session_activity

    def test_disabled_service_does_not_stamp(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        assert not service._session_activity

    def test_activity_cache_lru_capped(self, service):
        for index in range(SESSION_ACTIVITY_CACHE_SIZE + 10):
            service._record_session_activity("u1", f"s{index}")
        assert len(service._session_activity) == SESSION_ACTIVITY_CACHE_SIZE
        assert ("u1", "s0") not in service._session_activity


class TestIdleSweep:
    async def test_idle_session_digested_exactly_once(self, service):
        model = FakeModel()
        service.queue_turn("Plan the Bluebird launch", "Noted", user_id="u1", session_id="s1")

        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals["sessions"] == 1
        assert totals["entries"] == 1
        assert model.calls == 1
        assert not service._pending_turns.get("u1")
        assert ("u1", "s1") not in service._session_activity
        assert len(await service.storage.list_entries("u1")) == 1

        # A second sweep finds nothing: the session ended exactly once.
        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals == {"sessions": 0, "entries": 0, "sources": 0, "lessons": 0}
        assert model.calls == 1

    async def test_active_session_not_swept(self, service):
        model = FakeModel()
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        totals = await service.sweep_idle_sessions(model, now=time.time())
        assert totals["sessions"] == 0
        assert model.calls == 0
        assert len(service._pending_turns["u1"]) == 1

    async def test_no_double_digest_after_daily_tick(self, service):
        model = FakeModel()
        service.queue_turn("Plan the launch", "Noted", user_id="u1", session_id="s1")

        # Daily tick fires first and drains the pending turns.
        assert (await service.run_periodic_summarization(model))["entries"] == 1
        assert model.calls == 1

        # The idle sweep still ends the session but has nothing to digest.
        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals["sessions"] == 1
        assert totals["entries"] == 0
        assert model.calls == 1

    async def test_daily_tick_after_sweep_digests_nothing(self, service):
        model = FakeModel()
        service.queue_turn("Plan the launch", "Noted", user_id="u1", session_id="s1")

        assert (await service.sweep_idle_sessions(model, now=idle_now(service)))["entries"] == 1
        totals = await service.run_periodic_summarization(model)
        assert totals["entries"] == 0
        assert model.calls == 1

    async def test_two_idle_sessions_one_user_digest_once(self, service):
        model = FakeModel()
        service.queue_turn("first session turn", "ok", user_id="u1", session_id="s1")
        service.queue_turn("second session turn", "ok", user_id="u1", session_id="s2")

        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals["sessions"] == 2
        assert totals["entries"] == 1
        assert model.calls == 1

    async def test_active_sibling_defers_digest_until_last_session_idles(self, service):
        # Pending turns are per-user: sweeping idle s1 while s2 is still
        # active must NOT consume s2's fresh turns under s1's boundary.
        model = FakeModel()
        service.queue_turn("s1 turn about the kickoff", "ok", user_id="u1", session_id="s1")
        service.queue_turn("s2 turn about the launch", "ok", user_id="u1", session_id="s2")
        # Age s1 past the idle threshold; s2 stays fresh.
        service._session_activity[("u1", "s1")] = time.time() - service.session_idle_seconds - 1

        totals = await service.sweep_idle_sessions(model, now=time.time())
        assert totals["sessions"] == 1  # s1 still ends...
        assert totals["entries"] == 0  # ...but nothing is digested
        assert model.calls == 0
        assert len(service._pending_turns["u1"]) == 2  # queue left intact
        assert ("u1", "s1") not in service._session_activity
        assert ("u1", "s2") in service._session_activity

        # When the user's LAST session idles out, the digest runs exactly
        # once with ALL the queued turns.
        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals["sessions"] == 1
        assert totals["entries"] == 1
        assert model.calls == 1
        assert "s1 turn about the kickoff" in model.prompts[0]
        assert "s2 turn about the launch" in model.prompts[0]
        assert not service._pending_turns.get("u1")

    async def test_active_sibling_sweep_emits_ended_for_idle_session_only(self, service, events):
        service.queue_turn("s1 turn", "ok", user_id="u1", session_id="s1")
        service.queue_turn("s2 turn", "ok", user_id="u1", session_id="s2")
        service._session_activity[("u1", "s1")] = time.time() - service.session_idle_seconds - 1

        await service.sweep_idle_sessions(FakeModel(), now=time.time())
        ended = [
            data
            for event_type, data in events
            if event_type is service_module.observability.ConversationEvents.SESSION_ENDED
        ]
        assert [data["session_id"] for data in ended] == ["s1"]

    async def test_daily_tick_digests_deferred_turns_exactly_once(self, service):
        # Deferred turns (idle s1 + active s2) are not lost: the daily
        # tick digests the intact queue once, and s2's eventual session
        # end has nothing left to double-digest.
        model = FakeModel()
        service.queue_turn("s1 turn", "ok", user_id="u1", session_id="s1")
        service.queue_turn("s2 turn", "ok", user_id="u1", session_id="s2")
        service._session_activity[("u1", "s1")] = time.time() - service.session_idle_seconds - 1

        assert (await service.sweep_idle_sessions(model, now=time.time()))["entries"] == 0
        assert model.calls == 0

        totals = await service.run_periodic_summarization(model)
        assert totals["entries"] == 1
        assert model.calls == 1

        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals["sessions"] == 1  # s2 ends...
        assert totals["entries"] == 0  # ...with nothing left to digest
        assert model.calls == 1

    async def test_session_ended_event_emitted(self, service, events):
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        await service.sweep_idle_sessions(FakeModel(), now=idle_now(service))

        ended = [
            data
            for event_type, data in events
            if event_type is service_module.observability.ConversationEvents.SESSION_ENDED
        ]
        assert len(ended) == 1
        assert ended[0]["user_id"] == "u1"
        assert ended[0]["session_id"] == "s1"
        assert ended[0]["trigger"] == "captains_log_idle_sweep"
        assert ended[0]["idle_seconds"] >= service.session_idle_seconds

    async def test_no_model_keeps_turns_for_daily_tick(self, service):
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        totals = await service.sweep_idle_sessions(None, now=idle_now(service))
        # The session still ended, but the turns wait for the daily tick.
        assert totals["sessions"] == 1
        assert totals["entries"] == 0
        assert len(service._pending_turns["u1"]) == 1
        assert ("u1", "s1") not in service._session_activity

    async def test_digest_failure_requeues_turns(self, service):
        model = FakeModel(RuntimeError("LLM down"))
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")

        totals = await service.sweep_idle_sessions(model, now=idle_now(service))
        assert totals["sessions"] == 1
        assert totals["entries"] == 0
        # The snapshot is back in the queue for the periodic pass.
        assert len(service._pending_turns["u1"]) == 1

    async def test_disabled_trigger_sweeps_nothing(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"session_idle_minutes": 0})
        service.queue_turn("hello", "hi", user_id="u1", session_id="s1")
        totals = await service.sweep_idle_sessions(FakeModel(), now=time.time() + 10**6)
        assert totals == {"sessions": 0, "entries": 0, "sources": 0, "lessons": 0}

    async def test_disabled_service_sweeps_nothing(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        totals = await service.sweep_idle_sessions(FakeModel(), now=time.time())
        assert totals == {"sessions": 0, "entries": 0, "sources": 0, "lessons": 0}


class TestSweepLifecycle:
    async def test_start_creates_and_stop_cancels_sweep_task(self, service):
        service.start(lambda: None)
        assert service._sweep_task is not None
        assert service._task is not None
        await service.stop()
        assert service._sweep_task is None
        assert service._task is None

    async def test_disabled_trigger_starts_no_sweep_task(self, db_manager):
        service = CaptainsLogService(
            db_manager, FORMATION_ID, config={"session_idle_minutes": 0, "schedule": 60}
        )
        service.start(lambda: None)
        assert service._sweep_task is None
        assert service._task is not None
        await service.stop()

    async def test_start_twice_keeps_single_sweep_task(self, service):
        service.start(lambda: None)
        first = service._sweep_task
        service.start(lambda: None)
        assert service._sweep_task is first
        await service.stop()

    async def test_sweep_loop_digests_idle_session_end_to_end(self, db_manager):
        # ~0.12s idle threshold; the sweep loop ticks at its 1s floor.
        service = CaptainsLogService(
            db_manager,
            FORMATION_ID,
            config={"schedule": 3600, "session_idle_minutes": 0.002},
        )
        model = FakeModel()
        service.queue_turn("Plan the launch", "Noted", user_id="u1", session_id="s1")

        service.start(lambda: model)
        await asyncio.sleep(1.4)
        await service.stop()

        assert model.calls == 1
        assert len(await service.storage.list_entries("u1")) == 1
        assert not service._pending_turns.get("u1")
