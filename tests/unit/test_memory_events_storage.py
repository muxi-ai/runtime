"""Unit tests for the Memory Event Substrate storage layer.

Covers append (validation, ordering, causation, decay declaration),
idempotency, immutability (no update surface), soft delete + hard purge,
replay listing filters, user/formation isolation, and the projection
checkpoint cursor. Runs on SQLite; set MUXI_TEST_POSTGRES_DSN to run the
same suite against a live PostgreSQL.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_INTERACTION_TURN,
    MemoryEvent,
    ProjectionCheckpoint,
)
from muxi.runtime.services.memory.events.storage import MemoryEventStorage
from muxi.runtime.utils.datetime_utils import utc_now_naive

FORMATION_ID = "events-test-formation"
POSTGRES_DSN = os.environ.get("MUXI_TEST_POSTGRES_DSN")
BACKENDS = ["sqlite"] + (["postgresql"] if POSTGRES_DSN else [])

EVENT_TABLES = [MemoryEvent.__table__, ProjectionCheckpoint.__table__]


@pytest.fixture(params=BACKENDS)
def storage(request, tmp_path):
    """Event storage backed by a per-test database.

    SQLite uses a file (not :memory:) because the DatabaseManager keeps
    separate sync and async engines; both must see the same tables.
    """
    if request.param == "postgresql":
        db_manager = DatabaseManager(POSTGRES_DSN)
        Base.metadata.drop_all(db_manager.engine, tables=EVENT_TABLES)
    else:
        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/events.db")
    db_manager.create_tables(Base.metadata, tables=EVENT_TABLES)
    yield MemoryEventStorage(db_manager, FORMATION_ID)
    if request.param == "postgresql":
        Base.metadata.drop_all(db_manager.engine, tables=EVENT_TABLES)
    db_manager.engine.dispose()


async def append_turn(storage, user_id="u1", message="hello", **kwargs):
    """Append a minimal interaction.turn event."""
    return await storage.append(
        user_id=user_id,
        event_type=EVENT_INTERACTION_TURN,
        payload={"user_message": message},
        source="interaction",
        **kwargs,
    )


class TestAppend:
    async def test_append_returns_full_event(self, storage):
        event, created = await append_turn(storage, agent_id="assistant")
        assert created is True
        assert event["id"] > 0
        assert len(event["public_id"]) == 21
        assert event["user_id"] == "u1"
        assert event["formation_id"] == FORMATION_ID
        assert event["scope_type"] == "user"
        assert event["scope_id"] == "u1"
        assert event["event_type"] == EVENT_INTERACTION_TURN
        assert event["event_version"] == 1
        assert event["payload"] == {"user_message": "hello"}
        assert event["source"] == "interaction"
        assert event["source_confidence"] == 1.0
        assert event["decay_rate"] == "static"
        assert event["agent_id"] == "assistant"
        assert event["occurred_at"] is not None
        assert event["ingested_at"] is not None
        assert event["deleted_at"] is None

    async def test_append_order_is_the_replay_cursor(self, storage):
        first, _ = await append_turn(storage, message="one")
        second, _ = await append_turn(storage, message="two")
        third, _ = await append_turn(storage, message="three")
        assert first["id"] < second["id"] < third["id"]

        events = await storage.list_events("u1")
        assert [e["payload"]["user_message"] for e in events] == ["one", "two", "three"]

    async def test_causation_link(self, storage):
        turn, _ = await append_turn(storage)
        fact, _ = await storage.append(
            user_id="u1",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "Likes tea", "collection": "preferences"},
            source="interaction",
            caused_by=turn["id"],
        )
        assert fact["caused_by"] == turn["id"]

    async def test_explicit_occurred_at_preserved(self, storage):
        backfill_time = utc_now_naive() - timedelta(days=30)
        event, _ = await append_turn(storage, occurred_at=backfill_time)
        assert event["occurred_at"] == backfill_time.isoformat()
        assert event["ingested_at"] != event["occurred_at"]

    async def test_invalid_payload_rejected(self, storage):
        with pytest.raises(ValueError, match="missing required keys"):
            await storage.append(
                user_id="u1",
                event_type=EVENT_FACT_EXTRACTED,
                payload={"memory": "no collection"},
                source="interaction",
            )
        assert await storage.list_events("u1") == []

    async def test_unknown_event_type_rejected(self, storage):
        with pytest.raises(ValueError, match="Unknown memory event type"):
            await storage.append(
                user_id="u1", event_type="bogus.type", payload={}, source="interaction"
            )

    async def test_invalid_decay_rate_rejected(self, storage):
        with pytest.raises(ValueError, match="Invalid decay_rate"):
            await append_turn(storage, decay_rate="sometimes")

    async def test_empty_source_rejected(self, storage):
        with pytest.raises(ValueError, match="non-empty source"):
            await storage.append(
                user_id="u1",
                event_type=EVENT_INTERACTION_TURN,
                payload={"user_message": "hi"},
                source=" ",
            )


class TestIdempotency:
    async def test_duplicate_source_id_returns_existing(self, storage):
        first, created_first = await append_turn(storage, source_id="conv/1/turn/1")
        second, created_second = await append_turn(
            storage, message="different body", source_id="conv/1/turn/1"
        )
        assert created_first is True
        assert created_second is False
        assert second["id"] == first["id"]
        assert second["payload"] == first["payload"]  # original write wins
        assert len(await storage.list_events("u1")) == 1

    async def test_same_source_id_different_user_both_stored(self, storage):
        await append_turn(storage, user_id="u1", source_id="turn/1")
        await append_turn(storage, user_id="u2", source_id="turn/1")
        assert len(await storage.list_events("u1")) == 1
        assert len(await storage.list_events("u2")) == 1

    async def test_soft_deleted_source_id_can_be_rewritten(self, storage):
        first, _ = await append_turn(storage, source_id="turn/1")
        await storage.soft_delete_events("u1", [first["id"]], "user_request")
        second, created = await append_turn(storage, source_id="turn/1")
        assert created is True
        assert second["id"] != first["id"]


class TestImmutability:
    def test_storage_exposes_no_update_surface(self, storage):
        mutators = [
            name
            for name in dir(storage)
            if not name.startswith("_") and callable(getattr(storage, name))
        ]
        assert sorted(mutators) == [
            "append",
            "count_events",  # read-only size-cap accounting
            "expire_volatile",  # soft-delete of expired volatile events
            "find_by_source_id",  # read-only idempotency-key lookup
            "get_checkpoint",
            "get_event",
            "get_event_by_public_id",  # read-only provenance lookup
            "hard_purge",
            "list_event_user_ids",  # read-only maintenance enumeration
            "list_events",
            "max_event_id",  # read-only cursor tail lookup
            "reset_checkpoint",
            "set_checkpoint",
            "soft_delete_events",
        ]

    async def test_soft_delete_preserves_event_content(self, storage):
        event, _ = await append_turn(storage)
        await storage.soft_delete_events("u1", [event["id"]], "gdpr")
        stored = await storage.get_event(event["id"])
        assert stored["payload"] == event["payload"]
        assert stored["deleted_at"] is not None
        assert stored["deleted_reason"] == "gdpr"


class TestListing:
    async def test_filters_by_event_type(self, storage):
        await append_turn(storage)
        await storage.append(
            user_id="u1",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "Likes tea", "collection": "preferences"},
            source="interaction",
        )
        facts = await storage.list_events("u1", event_types=[EVENT_FACT_EXTRACTED])
        assert [e["event_type"] for e in facts] == [EVENT_FACT_EXTRACTED]

    async def test_filters_by_source(self, storage):
        await append_turn(storage)
        await storage.append(
            user_id="u1",
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "Fact", "collection": "context"},
            source="periodic",
        )
        periodic = await storage.list_events("u1", source="periodic")
        assert [e["source"] for e in periodic] == ["periodic"]

    async def test_after_id_cursor_and_limit(self, storage):
        first, _ = await append_turn(storage, message="one")
        await append_turn(storage, message="two")
        await append_turn(storage, message="three")
        after = await storage.list_events("u1", after_id=first["id"], limit=1)
        assert [e["payload"]["user_message"] for e in after] == ["two"]

    async def test_soft_deleted_excluded_by_default(self, storage):
        keep, _ = await append_turn(storage, message="keep")
        drop, _ = await append_turn(storage, message="drop")
        await storage.soft_delete_events("u1", [drop["id"]], "user_request")

        visible = await storage.list_events("u1")
        assert [e["id"] for e in visible] == [keep["id"]]

        everything = await storage.list_events("u1", include_deleted=True)
        assert [e["id"] for e in everything] == [keep["id"], drop["id"]]

    async def test_user_isolation(self, storage):
        await append_turn(storage, user_id="u1")
        await append_turn(storage, user_id="u2")
        assert {e["user_id"] for e in await storage.list_events("u1")} == {"u1"}
        assert {e["user_id"] for e in await storage.list_events("u2")} == {"u2"}

    async def test_get_event_scoped_to_formation(self, storage):
        event, _ = await append_turn(storage)
        assert (await storage.get_event(event["id"]))["id"] == event["id"]
        assert await storage.get_event(999999) is None


class TestSoftDeleteAndPurge:
    async def test_soft_delete_counts_only_live_rows(self, storage):
        event, _ = await append_turn(storage)
        assert await storage.soft_delete_events("u1", [event["id"]], "user_request") == 1
        assert await storage.soft_delete_events("u1", [event["id"]], "user_request") == 0
        assert await storage.soft_delete_events("u1", [], "user_request") == 0

    async def test_hard_purge_honors_grace_period(self, storage):
        fresh, _ = await append_turn(storage, message="fresh")
        aged, _ = await append_turn(storage, message="aged")
        live, _ = await append_turn(storage, message="live")
        await storage.soft_delete_events("u1", [fresh["id"], aged["id"]], "user_request")

        # Age one soft-delete past the grace period.
        async with storage.db_manager.get_async_session() as session:
            row = await session.get(MemoryEvent, aged["id"])
            row.deleted_at = utc_now_naive() - timedelta(days=31)

        purged = await storage.hard_purge(grace_period_days=30)
        assert purged == 1
        remaining = await storage.list_events("u1", include_deleted=True)
        assert {e["id"] for e in remaining} == {fresh["id"], live["id"]}


class TestCheckpoints:
    async def test_get_missing_checkpoint(self, storage):
        assert await storage.get_checkpoint("knowledge_graph", "u1") is None

    async def test_set_and_update_checkpoint(self, storage):
        created = await storage.set_checkpoint("knowledge_graph", "u1", last_event_id=5)
        assert created["last_event_id"] == 5
        assert created["schema_version"] == 1

        updated = await storage.set_checkpoint("knowledge_graph", "u1", last_event_id=9)
        assert updated["last_event_id"] == 9
        assert updated["id"] == created["id"]  # upsert, not a second row

        fetched = await storage.get_checkpoint("knowledge_graph", "u1")
        assert fetched["last_event_id"] == 9

    async def test_checkpoints_scoped_per_projection_and_user(self, storage):
        await storage.set_checkpoint("knowledge_graph", "u1", last_event_id=1)
        await storage.set_checkpoint("captains_log", "u1", last_event_id=2)
        await storage.set_checkpoint("knowledge_graph", "u2", last_event_id=3)
        assert (await storage.get_checkpoint("knowledge_graph", "u1"))["last_event_id"] == 1
        assert (await storage.get_checkpoint("captains_log", "u1"))["last_event_id"] == 2
        assert (await storage.get_checkpoint("knowledge_graph", "u2"))["last_event_id"] == 3

    async def test_reset_checkpoint(self, storage):
        await storage.set_checkpoint("knowledge_graph", "u1", last_event_id=5)
        await storage.reset_checkpoint("knowledge_graph", "u1")
        assert await storage.get_checkpoint("knowledge_graph", "u1") is None
        await storage.reset_checkpoint("knowledge_graph", "u1")  # idempotent
