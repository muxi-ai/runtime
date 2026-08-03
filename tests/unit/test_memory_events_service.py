"""Unit tests for the MemoryEventService coordination layer.

Covers failure-isolated recording (an append failure or a disabled
substrate never raises into the caller's write path), the projector
registry, the rebuild driver (reset -> ordered replay -> checkpoint,
dry-run, per-event failure containment), selective forgetting, and the
hard-purge lifecycle.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from muxi.runtime.datatypes.observability import RequestContext
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_INTERACTION_TURN,
    EVENT_USER_DELETION,
)
from muxi.runtime.services.memory.events.service import MemoryEventService
from muxi.runtime.services.observability.context import _current_request_context

FORMATION_ID = "events-test-formation"


@pytest.fixture
def service(tmp_path):
    """Event service backed by a file SQLite database."""
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/events.db")
    db_manager.create_tables(Base.metadata)
    yield MemoryEventService(db_manager, FORMATION_ID)
    db_manager.engine.dispose()


class RecordingProjector:
    """Test double implementing the projector contract."""

    def __init__(self, name="test_projection", event_types=(EVENT_FACT_EXTRACTED,)):
        self.name = name
        self.event_types = event_types
        self.applied = []
        self.resets = []
        self.fail_on_event_ids = set()

    async def apply(self, event):
        if event["id"] in self.fail_on_event_ids:
            raise RuntimeError("projector exploded")
        self.applied.append(event["id"])

    async def reset(self, user_id):
        self.resets.append(str(user_id))
        self.applied = []


@contextmanager
def request_context(request_id: str):
    """Activate an observability RequestContext for the enclosed block."""
    token = _current_request_context.set(RequestContext(id=request_id))
    try:
        yield
    finally:
        _current_request_context.reset(token)


async def record_fact(service, memory="Likes tea", **kwargs):
    return await service.record(
        user_id="u1",
        event_type=EVENT_FACT_EXTRACTED,
        payload={"memory": memory, "collection": "preferences"},
        source="interaction",
        **kwargs,
    )


class TestRecord:
    async def test_record_appends_and_returns_event(self, service):
        event = await record_fact(service)
        assert event is not None
        assert event["event_type"] == EVENT_FACT_EXTRACTED
        assert [e["id"] for e in await service.list_events("u1")] == [event["id"]]

    async def test_record_idempotent_duplicate_returns_existing(self, service):
        first = await record_fact(service, source_id="conv/1")
        second = await record_fact(service, memory="other", source_id="conv/1")
        assert second["id"] == first["id"]
        assert len(await service.list_events("u1")) == 1

    async def test_record_never_raises_on_append_failure(self, service, monkeypatch):
        async def broken_append(**kwargs):
            raise RuntimeError("database down")

        monkeypatch.setattr(service.storage, "append", broken_append)
        assert await record_fact(service) is None  # swallowed, not raised

    async def test_record_never_raises_on_invalid_payload(self, service):
        event = await service.record(
            user_id="u1",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "missing collection"},
            source="interaction",
        )
        assert event is None

    async def test_record_disabled_returns_none(self, service):
        service.enabled = False
        assert await record_fact(service) is None
        service.enabled = True
        assert await service.list_events("u1") == []

    async def test_record_inside_request_context_stamps_request_id(self, service):
        with request_context("req_abc123"):
            event = await record_fact(service)
        assert event["request_id"] == "req_abc123"
        assert (await service.list_events("u1"))[0]["request_id"] == "req_abc123"

    async def test_record_outside_request_context_stores_null(self, service):
        event = await record_fact(service)
        assert event["request_id"] is None

    async def test_idempotency_unaffected_by_differing_request_ids(self, service):
        # Same (source, source_id) retried from a different request must
        # still dedup; the original event's request_id is preserved.
        with request_context("req_first"):
            first = await record_fact(service, source_id="conv/1")
        with request_context("req_retry"):
            second = await record_fact(service, memory="other", source_id="conv/1")
        assert second["id"] == first["id"]
        assert second["request_id"] == "req_first"
        assert len(await service.list_events("u1")) == 1


class TestRebuild:
    async def test_rebuild_resets_replays_and_checkpoints(self, service):
        projector = RecordingProjector()
        service.register_projector(projector)

        first = await record_fact(service, memory="one")
        second = await record_fact(service, memory="two")
        # An event outside the projector's types must not be replayed.
        await service.record(
            user_id="u1",
            event_type=EVENT_INTERACTION_TURN,
            payload={"user_message": "hello"},
            source="interaction",
        )

        report = await service.rebuild("u1")
        assert report == {"test_projection": {"events": 2, "applied": 2, "failed": 0}}
        assert projector.resets == ["u1"]
        assert projector.applied == [first["id"], second["id"]]

        checkpoint = await service.storage.get_checkpoint("test_projection", "u1")
        assert checkpoint["last_event_id"] == second["id"]

    async def test_rebuild_preserves_request_id(self, service):
        # Rebuild replays the log read-only: the request_id recorded at
        # append time survives, and the replayed event carries it.
        projector = RecordingProjector()
        service.register_projector(projector)
        with request_context("req_rebuild"):
            event = await record_fact(service)

        await service.rebuild("u1")
        assert projector.applied == [event["id"]]
        replayed = (await service.list_events("u1"))[0]
        assert replayed["request_id"] == "req_rebuild"

    async def test_rebuild_specific_projection_only(self, service):
        target = RecordingProjector(name="target")
        bystander = RecordingProjector(name="bystander")
        service.register_projector(target)
        service.register_projector(bystander)
        await record_fact(service)

        report = await service.rebuild("u1", projection="target")
        assert list(report) == ["target"]
        assert bystander.resets == []

    async def test_rebuild_unknown_projection_raises(self, service):
        with pytest.raises(ValueError, match="Unknown projection"):
            await service.rebuild("u1", projection="nope")

    async def test_rebuild_disabled_raises(self, service):
        service.enabled = False
        with pytest.raises(ValueError, match="disabled"):
            await service.rebuild("u1")

    async def test_rebuild_dry_run_touches_nothing(self, service):
        projector = RecordingProjector()
        service.register_projector(projector)
        await record_fact(service)

        report = await service.rebuild("u1", dry_run=True)
        assert report["test_projection"] == {
            "events": 1,
            "applied": 0,
            "failed": 0,
            "dry_run": True,
        }
        assert projector.resets == []
        assert projector.applied == []
        assert await service.storage.get_checkpoint("test_projection", "u1") is None

    async def test_rebuild_contains_per_event_failures(self, service):
        projector = RecordingProjector()
        service.register_projector(projector)
        bad = await record_fact(service, memory="bad")
        good = await record_fact(service, memory="good")
        projector.fail_on_event_ids = {bad["id"]}

        report = await service.rebuild("u1")
        assert report["test_projection"] == {"events": 2, "applied": 1, "failed": 1}
        assert projector.applied == [good["id"]]

    async def test_rebuild_skips_soft_deleted_events(self, service):
        projector = RecordingProjector()
        service.register_projector(projector)
        forgotten = await record_fact(service, memory="forgotten")
        kept = await record_fact(service, memory="kept")
        await service.storage.soft_delete_events("u1", [forgotten["id"]], "user_request")

        report = await service.rebuild("u1")
        assert report["test_projection"]["events"] == 1
        assert projector.applied == [kept["id"]]


class TestForgetSource:
    async def test_forget_source_soft_deletes_and_audits(self, service):
        projector = RecordingProjector()
        service.register_projector(projector)
        await record_fact(service, memory="one")
        await record_fact(service, memory="two")

        result = await service.forget_source("u1", "interaction", reason="gdpr")
        assert result["deleted_events"] == 2
        assert result["rebuild_required"] == ["test_projection"]

        live = await service.list_events("u1")
        assert [e["event_type"] for e in live] == [EVENT_USER_DELETION]
        assert live[0]["payload"]["reason"] == "gdpr"
        assert len(live[0]["payload"]["target_event_ids"]) == 2

    async def test_forget_source_leaves_other_sources(self, service):
        await record_fact(service)
        await service.record(
            user_id="u1",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "periodic fact", "collection": "context"},
            source="periodic",
        )
        result = await service.forget_source("u1", "interaction")
        assert result["deleted_events"] == 1
        sources = {e["source"] for e in await service.list_events("u1")}
        assert "periodic" in sources


class TestPurgeLifecycle:
    async def test_start_and_stop_maintenance_loop(self, service):
        service.start()
        assert service._maintenance_task is not None
        first_task = service._maintenance_task
        service.start()  # idempotent while running
        assert service._maintenance_task is first_task
        assert service._applier_task is None  # dual-write mode: no applier
        await service.stop()
        assert service._maintenance_task is None
        await service.stop()  # idempotent when stopped

    async def test_start_event_first_spawns_applier(self, tmp_path):
        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/ef.db")
        db_manager.create_tables(Base.metadata)
        ef_service = MemoryEventService(db_manager, FORMATION_ID, config={"event_first": True})
        ef_service.start()
        assert ef_service._applier_task is not None
        await ef_service.stop()
        assert ef_service._applier_task is None
        db_manager.engine.dispose()

    async def test_start_disabled_is_noop(self, service):
        service.enabled = False
        service.start()
        assert service._maintenance_task is None

    async def test_run_hard_purge_empty_log(self, service):
        assert await service.run_hard_purge() == 0


class TestConfig:
    def test_defaults(self, service):
        assert service.enabled is True
        assert service.grace_period_days == 30

    def test_config_overrides(self, tmp_path):
        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/cfg.db")
        db_manager.create_tables(Base.metadata)
        configured = MemoryEventService(
            db_manager,
            FORMATION_ID,
            config={"enabled": True, "retention": {"grace_period_days": 7}},
        )
        assert configured.grace_period_days == 7
        db_manager.engine.dispose()

    def test_invalid_grace_period_fails_fast(self, tmp_path):
        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/bad.db")
        with pytest.raises(ValueError):
            MemoryEventService(
                db_manager,
                FORMATION_ID,
                config={"retention": {"grace_period_days": "forever"}},
            )
        db_manager.engine.dispose()
