"""Legacy backfill tests (Memory Substrate Phase 2d / PRD Phase B).

Pre-event-log rows (created before the substrate shipped, so without any
``derived_from_event_ids`` provenance) get synthetic ``source='legacy'``
events keyed per row. Covers: synthesis + in-place provenance stamping
for graph/log rows, event synthesis for orphan flat facts, idempotent
re-runs, the rebuild-after-backfill path that makes legacy data
replayable, and the bounded multi-pass scan (per-pass row bound with a
persisted resume cursor, crash-safe re-runs without duplicates).
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

    async def list_extracted_orphan_memories(self, user_id, limit=None, offset=None):
        orphans = [
            dict(row)
            for row in self.rows.values()
            if row["user_id"] == str(user_id)
            and row["metadata"].get("source") == "extraction"
            and row["metadata"].get("derived_from_event_id") is None
        ]
        start = offset or 0
        end = start + limit if limit is not None else None
        return orphans[start:end]


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
        # 2 entities + 1 relationship, all scanned in one pass.
        assert report["knowledge_graph"] == {"synthesized": 3, "complete": True}

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
        assert first["knowledge_graph"]["synthesized"] == 3
        # Everything already stamped on the re-run (cursors were cleared
        # by the completed pass, so the re-run scanned from the start).
        assert second["knowledge_graph"] == {"synthesized": 0, "complete": True}
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
        # 1 entry + 1 lesson.
        assert report["captains_log"] == {"synthesized": 2, "complete": True}

        entries = await log.storage.list_entries(USER)
        assert entries[0]["derived_from_event_ids"]
        lessons = await log.lessons.list_all_for_user(USER)
        assert lessons[0]["derived_from_event_ids"]
        # Lesson hits untouched by the stamping confirmation? The apply
        # bumps hits (confirmation semantics); what matters is the rule
        # set and lineage are unchanged.
        assert lessons[0]["rule"] == "Prefer reportlab over fpdf"

        rerun = await events.backfill_user(USER)
        assert rerun == {"captains_log": {"synthesized": 0, "complete": True}}

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
        assert report["flat_facts"] == {"synthesized": 1, "complete": True}
        legacy = await events.list_events(USER, source=SOURCE_LEGACY)
        assert len(legacy) == 1
        assert legacy[0]["payload"]["memory"] == "Likes tea"

        rerun = await events.backfill_user(USER)  # idempotent? no:
        # the row is still orphaned (stamping happens on rebuild), but the
        # per-row legacy source_id makes the re-run an idempotent skip.
        assert rerun == {"flat_facts": {"synthesized": 0, "complete": True}}

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
        rerun = await events.backfill_user(USER)
        assert rerun == {"flat_facts": {"synthesized": 0, "complete": True}}


class TestMultiPassBackfill:
    """The per-pass row bound with a persisted resume cursor.

    Legacy tables larger than BACKFILL_MAX_ROWS_PER_PASS backfill across
    multiple ``backfill_user`` calls: an incomplete pass persists its
    scan cursor in projection_checkpoints (``backfill/...`` names) and
    reports ``complete: false``; the next pass resumes past it. No row
    is skipped and no legacy event is duplicated across passes.
    """

    async def seed_entities(self, db_manager, count):
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=None)
        for index in range(count):
            await graph.storage.upsert_entity(USER, "company", f"Corp{index}", confidence=0.9)
        return graph

    async def test_kg_backfill_resumes_across_passes(self, db_manager, events):
        graph = await self.seed_entities(db_manager, 5)
        projector = KnowledgeGraphProjector(graph)
        projector.backfill_batch_rows = 2  # shrink the per-pass bound
        events.register_projector(projector)

        synthesized = []
        for _ in range(2):
            report = await events.backfill_user(USER)
            assert report["knowledge_graph"]["complete"] is False
            synthesized.append(report["knowledge_graph"]["synthesized"])
            # The resume cursor persisted like a projection cursor.
            checkpoint = await events.storage.get_checkpoint(
                "backfill/knowledge_graph/entities", USER
            )
            assert checkpoint is not None

        final = await events.backfill_user(USER)
        assert final["knowledge_graph"]["complete"] is True
        synthesized.append(final["knowledge_graph"]["synthesized"])

        # Every entity synthesized exactly once across the passes.
        assert sum(synthesized) == 5
        legacy = await events.list_events(USER, source=SOURCE_LEGACY)
        assert len(legacy) == 5
        assert len({e["source_id"] for e in legacy}) == 5
        entities = await graph.storage.list_entities(USER, status=None)
        assert all(e["derived_from_event_ids"] for e in entities)
        # The completed pass cleared its cursors.
        assert await events.storage.get_checkpoint("backfill/knowledge_graph/entities", USER) is (
            None
        )

    async def test_kg_crash_between_passes_never_duplicates(self, db_manager, events):
        """A re-run after an interrupted pass re-scans that pass's rows;
        the per-row (source, source_id) key keeps events unique."""
        graph = await self.seed_entities(db_manager, 4)
        projector = KnowledgeGraphProjector(graph)
        projector.backfill_batch_rows = 2
        events.register_projector(projector)

        await events.backfill_user(USER)  # pass 1 (rows 1-2), cursor persisted

        # Simulate a crash before pass 2 persisted anything: wipe the
        # cursor so the next run re-scans from the start.
        await events.storage.reset_checkpoint("backfill/knowledge_graph/entities", USER)
        await events.storage.reset_checkpoint("backfill/knowledge_graph/relationships", USER)

        report = await events.backfill_user(USER)  # re-scans rows 1-2
        assert report["knowledge_graph"] == {"synthesized": 0, "complete": False}
        final = await events.backfill_user(USER)  # rows 3-4
        assert final["knowledge_graph"]["synthesized"] == 2

        legacy = await events.list_events(USER, source=SOURCE_LEGACY)
        assert len(legacy) == 4  # no duplicates despite the re-scan
        assert len({e["source_id"] for e in legacy}) == 4

    async def test_flat_fact_offset_cursor_resumes(self, events):
        long_term = FakeLongTermMemory()
        projector = FlatFactProjector(long_term)
        projector.backfill_batch_rows = 2
        events.register_projector(projector)
        for index in range(5):
            await long_term.add(
                content=f"Fact {index}",
                metadata={"source": "extraction"},
                user_id=USER,
                collection="preferences",
            )

        first = await events.backfill_user(USER)
        assert first["flat_facts"] == {"synthesized": 2, "complete": False}
        second = await events.backfill_user(USER)
        assert second["flat_facts"] == {"synthesized": 2, "complete": False}
        third = await events.backfill_user(USER)
        assert third["flat_facts"] == {"synthesized": 1, "complete": True}

        legacy = await events.list_events(USER, source=SOURCE_LEGACY)
        assert sorted(e["payload"]["memory"] for e in legacy) == [
            f"Fact {index}" for index in range(5)
        ]
        # Completed pass cleared the offset cursor.
        assert await events.storage.get_checkpoint("backfill/flat_facts/memories", USER) is None

    async def test_lessons_resolve_entry_dates_across_pages(self, db_manager, events):
        """A paginated lesson page still resolves its source entry's date
        even when that entry was scanned in an earlier page."""
        from datetime import date

        log = CaptainsLogService(db_manager, FORMATION_ID, event_log=None)
        entry = await log.storage.upsert_entry(USER, date(2025, 6, 1), summary="Day one.")
        await log.lessons.upsert_lesson(
            user_id=USER, agent_id="overlord", rule="Rule A", source_log_id=entry["id"]
        )
        projector = CaptainsLogProjector(log)
        projector.backfill_batch_rows = 1  # entry page and lesson page split
        events.register_projector(projector)

        reports = []
        for _ in range(3):
            reports.append(await events.backfill_user(USER))
            if reports[-1]["captains_log"]["complete"]:
                break
        assert reports[-1]["captains_log"]["complete"] is True

        lesson_events = await events.list_events(USER, event_types=["lesson.recorded"])
        assert len(lesson_events) == 1
        assert lesson_events[0]["payload"]["source_log_date"] == "2025-06-01"
