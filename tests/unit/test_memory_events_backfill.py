"""Legacy backfill tests (Memory Substrate Phase 2d / PRD Phase B).

Pre-event-log rows (created before the substrate shipped, so without any
``derived_from_event_ids`` provenance) get synthetic ``source='legacy'``
events keyed per row. Covers: synthesis + in-place provenance stamping
for graph/log rows, event synthesis for orphan flat facts, idempotent
re-runs, and the rebuild-after-backfill path that makes legacy data
replayable.
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import (
    CaptainsLogProjector,
    FlatFactProjector,
    KnowledgeGraphProjector,
    MemoryEventService,
)
from muxi.runtime.services.memory.events.models import SOURCE_LEGACY
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.log.service import CaptainsLogService

FORMATION_ID = "backfill-test-formation"
USER = "u1"


class FakeLongTermMemory:
    """Vector-store double with the orphan-listing backfill surface."""

    def __init__(self):
        self.rows = {}
        self._counter = 0

    async def add(self, content, metadata=None, user_id=None, collection=None, scope=None):
        self._counter += 1
        memory_id = f"m{self._counter}"
        self.rows[memory_id] = {
            "id": memory_id,
            "text": content,
            "metadata": dict(metadata or {}),
            "user_id": str(user_id),
            "collection": collection,
            "scope": scope,
            "created_at": "2025-06-01T00:00:00",
        }
        return memory_id

    async def delete_extracted_memories(self, user_id):
        doomed = [
            memory_id
            for memory_id, row in self.rows.items()
            if row["user_id"] == str(user_id)
            and (
                row["metadata"].get("source") == "extraction"
                or row["metadata"].get("derived_from_event_id") is not None
            )
        ]
        for memory_id in doomed:
            del self.rows[memory_id]
        return len(doomed)

    async def list_extracted_orphan_memories(self, user_id):
        return [
            dict(row)
            for row in self.rows.values()
            if row["user_id"] == str(user_id)
            and row["metadata"].get("source") == "extraction"
            and row["metadata"].get("derived_from_event_id") is None
        ]


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/backfill.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def events(db_manager):
    return MemoryEventService(db_manager, FORMATION_ID)


async def seed_legacy_graph(db_manager):
    """A pre-substrate subgraph: direct writes, no event log involved."""
    graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=None)
    user = await graph.storage.upsert_entity(USER, "person", "User", confidence=0.95)
    london = await graph.storage.upsert_entity(
        USER, "location", "London", confidence=0.9, attributes={"country": "UK"}
    )
    await graph.storage.upsert_relationship(
        USER, user["id"], london["id"], "lives_in", confidence=0.9
    )
    return graph


class TestKnowledgeGraphBackfill:
    async def test_synthesizes_and_stamps_provenance(self, db_manager, events):
        graph = await seed_legacy_graph(db_manager)
        events.register_projector(KnowledgeGraphProjector(graph))

        report = await events.backfill_user(USER)
        assert report["knowledge_graph"] == 3  # 2 entities + 1 relationship

        legacy = await events.list_events(USER, source=SOURCE_LEGACY)
        assert len(legacy) == 3
        assert all(e["source_id"].startswith("legacy/kg_") for e in legacy)

        # Rows stamped in place; content untouched.
        london = await graph.storage.get_entity(USER, "location", "London")
        assert london["derived_from_event_ids"]
        assert london["attributes"] == {"country": "UK"}
        relationships = await graph.storage.list_relationships(USER)
        assert all(r["derived_from_event_ids"] for r in relationships)

    async def test_backfill_is_idempotent(self, db_manager, events):
        graph = await seed_legacy_graph(db_manager)
        events.register_projector(KnowledgeGraphProjector(graph))

        first = await events.backfill_user(USER)
        second = await events.backfill_user(USER)
        assert first["knowledge_graph"] == 3
        assert second["knowledge_graph"] == 0  # everything already stamped
        assert len(await events.list_events(USER, source=SOURCE_LEGACY)) == 3

    async def test_rebuild_after_backfill_reproduces_legacy_rows(self, db_manager, events):
        graph = await seed_legacy_graph(db_manager)
        events.register_projector(KnowledgeGraphProjector(graph))
        await events.backfill_user(USER)

        entities_before = {
            (e["type"], e["name"]): (e["confidence"], e["attributes"])
            for e in await graph.storage.list_entities(USER, status=None)
        }
        report = await events.rebuild(USER, projection="knowledge_graph")
        assert report["knowledge_graph"]["failed"] == 0
        entities_after = {
            (e["type"], e["name"]): (e["confidence"], e["attributes"])
            for e in await graph.storage.list_entities(USER, status=None)
        }
        assert entities_after == entities_before
        relationships = await graph.storage.list_relationships(USER)
        assert len(relationships) == 1
        assert relationships[0]["type"] == "lives_in"


class TestCaptainsLogBackfill:
    async def seed_legacy_log(self, db_manager):
        """Pre-substrate entries + lessons: direct writes, no events."""
        from datetime import date

        log = CaptainsLogService(db_manager, FORMATION_ID, event_log=None)
        entry = await log.storage.upsert_entry(
            USER,
            date(2025, 6, 1),
            summary="Founded Automaze.",
            decisions=["Ship the runtime"],
            projects=["MUXI"],
            context="Launch week.",
        )
        await log.storage.add_sources(
            USER, entry["id"], [{"source_type": "buffer_item", "source_id": "t1"}]
        )
        await log.lessons.upsert_lesson(
            user_id=USER,
            agent_id="overlord",
            rule="Prefer reportlab over fpdf",
            source_log_id=entry["id"],
        )
        return log

    async def test_synthesizes_and_stamps(self, db_manager, events):
        log = await self.seed_legacy_log(db_manager)
        events.register_projector(CaptainsLogProjector(log))

        report = await events.backfill_user(USER)
        assert report["captains_log"] == 2  # 1 entry + 1 lesson

        entries = await log.storage.list_entries(USER)
        assert entries[0]["derived_from_event_ids"]
        lessons = await log.lessons.list_all_for_user(USER)
        assert lessons[0]["derived_from_event_ids"]
        # Lesson hits untouched by the stamping confirmation? The apply
        # bumps hits (confirmation semantics); what matters is the rule
        # set and lineage are unchanged.
        assert lessons[0]["rule"] == "Prefer reportlab over fpdf"

        assert await events.backfill_user(USER) == {"captains_log": 0}

    async def test_rebuild_after_backfill_reproduces_entries(self, db_manager, events):
        log = await self.seed_legacy_log(db_manager)
        events.register_projector(CaptainsLogProjector(log))
        await events.backfill_user(USER)

        report = await events.rebuild(USER, projection="captains_log")
        assert report["captains_log"]["failed"] == 0
        entries = await log.storage.list_entries(USER)
        assert len(entries) == 1
        assert entries[0]["summary"] == "Founded Automaze."
        sources = await log.storage.get_sources(entries[0]["id"])
        assert [(s["source_type"], s["source_id"]) for s in sources] == [("buffer_item", "t1")]
        lessons = await log.lessons.list_all_for_user(USER)
        assert len(lessons) == 1
        assert lessons[0]["source_log_id"] == entries[0]["id"]  # re-linked by date


class TestFlatFactBackfill:
    async def test_synthesizes_events_for_orphan_rows(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        # Legacy extraction row (no provenance) + a manual row (never event-sourced).
        await long_term.add(
            content="Likes tea",
            metadata={"source": "extraction", "confidence": 0.9},
            user_id=USER,
            collection="preferences",
        )
        await long_term.add(
            content="manual note",
            metadata={"source": "user"},
            user_id=USER,
            collection="context",
        )

        report = await events.backfill_user(USER)
        assert report["flat_facts"] == 1
        legacy = await events.list_events(USER, source=SOURCE_LEGACY)
        assert len(legacy) == 1
        assert legacy[0]["payload"]["memory"] == "Likes tea"

        assert await events.backfill_user(USER) == {"flat_facts": 0}  # idempotent? no:
        # the row is still orphaned (stamping happens on rebuild), but the
        # per-row legacy source_id makes the re-run an idempotent skip.

    async def test_rebuild_after_backfill_stamps_provenance(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        await long_term.add(
            content="Likes tea",
            metadata={"source": "extraction", "confidence": 0.9},
            user_id=USER,
            collection="preferences",
        )
        await events.backfill_user(USER)

        report = await events.rebuild(USER, projection="flat_facts")
        assert report["flat_facts"] == {"events": 1, "applied": 1, "failed": 0}
        rows = [row for row in long_term.rows.values() if row["user_id"] == USER]
        assert len(rows) == 1
        assert rows[0]["text"] == "Likes tea"
        assert rows[0]["metadata"]["derived_from_event_id"] is not None
        # Now provenance-complete: nothing left to backfill.
        assert await events.backfill_user(USER) == {"flat_facts": 0}
