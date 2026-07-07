"""Replay-equivalence tests for the Memory Event Substrate.

The substrate's core promise: for every projection, write -> wipe ->
replay produces the same queryable state as the incremental writes did.
Each projection is exercised through its REAL dual-write path (the same
code a live formation runs), snapshotted, wiped by its projector, rebuilt
from the event log, and compared under a normalization that ignores only
storage-assigned identity (integer ids, public ids, row timestamps).

Also covers append-failure isolation: when the event log is down, every
projection write path must still succeed (PRD Phase A dual-write posture).
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
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_LESSON_RECORDED,
    EVENT_LOG_ENTRY,
)
from muxi.runtime.services.memory.extractor import MemoryExtractor
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.log.service import CaptainsLogService

FORMATION_ID = "replay-test-formation"
USER = "u1"

DIGEST_RESPONSE = (
    "{"
    '"summary": "The user finalized the memory PRD and founded Automaze.",'
    '"decisions": ["Knowledge graph over flat facts"],'
    '"projects": ["MUXI"],'
    '"context": "Focused on the launch.",'
    '"lessons": [{"rule": "Prefer reportlab over fpdf", "context": "PDF generation"}],'
    '"entities": [],'
    '"relationships": []'
    "}"
)


class FakeModel:
    """Digest LLM double returning a canned response."""

    def __init__(self, response=DIGEST_RESPONSE):
        self.response = response

    async def generate_text(self, prompt, caching=True):
        return self.response


class FakeLongTermMemory:
    """Vector-store double implementing the flat-fact projection contract."""

    def __init__(self):
        self.rows = {}
        self._counter = 0

    async def add(self, content, metadata=None, user_id=None, collection=None, scope=None):
        self._counter += 1
        memory_id = f"m{self._counter}"
        self.rows[memory_id] = {
            "content": content,
            "metadata": dict(metadata or {}),
            "user_id": str(user_id),
            "collection": collection,
            # Memory namespaces: replay stamps the scope recorded on the
            # event; None = user scope (mirrors the real backends).
            "scope": scope,
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


class FakeOverlord:
    """Just enough overlord surface for MemoryExtractor writes."""

    def __init__(self, memory_events):
        self.is_multi_user = True
        self.long_term_memory = FakeLongTermMemory()
        self.memory_events = memory_events
        self.current_agent = "overlord"


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/replay.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def events(db_manager):
    return MemoryEventService(db_manager, FORMATION_ID)


@pytest.fixture
def broken_events(db_manager, monkeypatch):
    """An event service whose appends always fail (database down)."""
    service = MemoryEventService(db_manager, FORMATION_ID)

    async def broken_append(**kwargs):
        raise RuntimeError("event log unavailable")

    monkeypatch.setattr(service.storage, "append", broken_append)
    return service


# ----------------------------------------------------------------------
# Normalized snapshots: structural state keyed by natural identity, with
# storage-assigned ids and row timestamps excluded.
# ----------------------------------------------------------------------


async def snapshot_graph(graph, user_id=USER):
    """Snapshot the full subgraph (all statuses) keyed by names."""
    entities = await graph.storage.list_entities(user_id, status=None, limit=1000)
    entity_key = {e["id"]: (e["type"], e["name"]) for e in entities}
    entity_state = {
        entity_key[e["id"]]: {
            "attributes": e["attributes"],
            "confidence": e["confidence"],
            "status": e["status"],
            "contradicted_by": entity_key.get(e["contradicted_by"]),
            "superseded_by": entity_key.get(e["superseded_by"]),
            "events": e["derived_from_event_ids"],
        }
        for e in entities
    }
    relationships = await graph.storage.list_relationships(user_id, status=None, limit=1000)
    rel_key = {
        r["id"]: (entity_key[r["from_entity_id"]], r["type"], entity_key[r["to_entity_id"]])
        for r in relationships
    }
    rel_state = {
        rel_key[r["id"]]: {
            "attributes": r["attributes"],
            "confidence": r["confidence"],
            "status": r["status"],
            "contradicted_by": rel_key.get(r["contradicted_by"]),
            "superseded_by": rel_key.get(r["superseded_by"]),
            "events": r["derived_from_event_ids"],
        }
        for r in relationships
    }
    return entity_state, rel_state


async def snapshot_log(log, user_id=USER):
    """Snapshot entries (+ lineage) and lessons keyed by natural identity."""
    entries = await log.storage.list_entries(user_id, limit=1000)
    date_by_id = {e["id"]: e["date"] for e in entries}
    sources_by_log = await log.storage.get_sources_for_logs([e["id"] for e in entries])
    entry_state = {
        e["date"]: {
            "summary": e["summary"],
            "decisions": e["decisions"],
            "projects": e["projects"],
            "context": e["context"],
            "events": e["derived_from_event_ids"],
            "sources": sorted(
                (s["source_type"], s["source_id"]) for s in sources_by_log.get(e["id"], [])
            ),
        }
        for e in entries
    }
    lessons = await log.lessons.list_active(user_id, limit=1000)
    lesson_state = {
        (lesson["agent_id"], lesson["rule_hash"]): {
            "rule": lesson["rule"],
            "context": lesson["context"],
            "confidence": lesson["confidence"],
            "hits": lesson["hits"],
            "archived": lesson["archived"],
            "source_log_date": date_by_id.get(lesson["source_log_id"]),
            "events": lesson["derived_from_event_ids"],
        }
        for lesson in lessons
    }
    return entry_state, lesson_state


def snapshot_flat(long_term_memory, user_id=USER):
    """Snapshot flat-fact rows without their storage-assigned ids."""
    rows = [row for row in long_term_memory.rows.values() if row["user_id"] == str(user_id)]
    return sorted(rows, key=lambda row: (row["collection"], row["content"]))


# ----------------------------------------------------------------------
# Knowledge graph projection
# ----------------------------------------------------------------------


class TestKnowledgeGraphReplay:
    async def seed(self, graph):
        """Drive the real dual-write path, covering merge, conflict, supersede."""
        await graph.store_extraction(
            USER,
            {
                "entities": [
                    {"name": "User", "type": "person", "confidence": 0.95},
                    {
                        "name": "London",
                        "type": "location",
                        "confidence": 0.9,
                        "attributes": {"country": "UK"},
                    },
                ],
                "relationships": [
                    {
                        "from": "User",
                        "from_type": "person",
                        "to": "London",
                        "to_type": "location",
                        "type": "lives_in",
                        "confidence": 0.9,
                    }
                ],
            },
        )
        # Conflicting fact on an exclusive predicate (delta below threshold).
        await graph.store_extraction(
            USER,
            {
                "entities": [{"name": "Berlin", "type": "location", "confidence": 0.9}],
                "relationships": [
                    {
                        "from": "User",
                        "from_type": "person",
                        "to": "Berlin",
                        "to_type": "location",
                        "type": "lives_in",
                        "confidence": 0.92,
                    }
                ],
            },
            source="periodic",
        )
        # Superseding fact (delta above threshold) + duplicate entity merge.
        await graph.store_extraction(
            USER,
            {
                "entities": [
                    {
                        "name": "User",
                        "type": "person",
                        "confidence": 0.9,
                        "attributes": {"role": "founder"},
                    },
                    {"name": "Acme", "type": "company", "confidence": 0.5},
                ],
                "relationships": [
                    {
                        "from": "User",
                        "from_type": "person",
                        "to": "Acme",
                        "to_type": "company",
                        "type": "works_at",
                        "confidence": 0.5,
                    }
                ],
            },
        )
        await graph.store_extraction(
            USER,
            {
                "entities": [{"name": "Beta", "type": "company", "confidence": 0.9}],
                "relationships": [
                    {
                        "from": "User",
                        "from_type": "person",
                        "to": "Beta",
                        "to_type": "company",
                        "type": "works_at",
                        "confidence": 0.9,
                    }
                ],
            },
        )

    async def test_wipe_and_replay_reproduces_identical_state(self, db_manager, events):
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(KnowledgeGraphProjector(graph))
        await self.seed(graph)

        before = await snapshot_graph(graph)
        entity_state, rel_state = before
        # Sanity: the seed produced the full contradiction-detection shape.
        assert (
            rel_state[(("person", "User"), "lives_in", ("location", "Berlin"))]["status"]
            == "conflicted"
        )
        assert (
            rel_state[(("person", "User"), "works_at", ("company", "Acme"))]["status"]
            == "superseded"
        )
        assert entity_state[("person", "User")]["attributes"] == {"role": "founder"}
        assert all(state["events"] for state in entity_state.values())

        report = await events.rebuild(USER, projection="knowledge_graph")
        assert report["knowledge_graph"]["events"] == 4
        assert report["knowledge_graph"]["failed"] == 0

        after = await snapshot_graph(graph)
        assert after == before

        checkpoint = await events.storage.get_checkpoint("knowledge_graph", USER)
        graph_events = await events.list_events(USER, event_types=[EVENT_GRAPH_EXTRACTED])
        assert checkpoint["last_event_id"] == graph_events[-1]["id"]

    async def test_replay_is_idempotent_across_repeated_rebuilds(self, db_manager, events):
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(KnowledgeGraphProjector(graph))
        await self.seed(graph)

        await events.rebuild(USER, projection="knowledge_graph")
        first = await snapshot_graph(graph)
        await events.rebuild(USER, projection="knowledge_graph")
        second = await snapshot_graph(graph)
        assert second == first

    async def test_rebuild_scoped_to_one_user(self, db_manager, events):
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(KnowledgeGraphProjector(graph))
        await self.seed(graph)
        await graph.store_extraction(
            "u2",
            {
                "entities": [{"name": "Oslo", "type": "location", "confidence": 0.9}],
                "relationships": [],
            },
        )
        other_before = await snapshot_graph(graph, "u2")

        await events.rebuild(USER, projection="knowledge_graph")
        assert await snapshot_graph(graph, "u2") == other_before

    async def test_append_failure_never_blocks_graph_writes(self, db_manager, broken_events):
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=broken_events)
        await graph.store_extraction(
            USER,
            {
                "entities": [{"name": "Acme", "type": "company", "confidence": 0.9}],
                "relationships": [],
            },
        )
        stored = await graph.storage.get_entity(USER, "company", "Acme")
        assert stored is not None
        assert stored["derived_from_event_ids"] == []  # no event, write still landed


# ----------------------------------------------------------------------
# Captain's log projection (entries + lineage + lessons)
# ----------------------------------------------------------------------


class TestCaptainsLogReplay:
    async def seed(self, log):
        """Drive the real digest and record_lesson dual-write paths."""
        log.queue_turn("We founded Automaze today.", "Congratulations.", USER)
        log.queue_turn("Decided to launch MUXI next month.", "Noted.", USER)
        totals = await log.run_periodic_summarization(FakeModel())
        assert totals["entries"] == 1
        # Tool path, including a duplicate write (confirmation: hits bump).
        await log.record_lesson(USER, "memory_agent", "Always confirm before deleting")
        await log.record_lesson(USER, "memory_agent", "Always confirm before deleting")

    async def test_wipe_and_replay_reproduces_identical_state(self, db_manager, events):
        log = CaptainsLogService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(CaptainsLogProjector(log))
        await self.seed(log)

        before = await snapshot_log(log)
        entry_state, lesson_state = before
        assert len(entry_state) == 1
        (entry,) = entry_state.values()
        assert len(entry["sources"]) == 2  # both buffered turns in the lineage
        assert entry["events"]  # provenance recorded
        # Digest lesson links to its entry by date; confirmation doubled hits.
        digest_lesson = next(
            state for state in lesson_state.values() if state["rule"].startswith("Prefer")
        )
        assert digest_lesson["source_log_date"] in entry_state
        tool_lesson = next(
            state for state in lesson_state.values() if state["rule"].startswith("Always")
        )
        assert tool_lesson["hits"] == 2

        report = await events.rebuild(USER, projection="captains_log")
        assert report["captains_log"]["events"] == 4  # 1 entry + 3 lesson events
        assert report["captains_log"]["failed"] == 0

        after = await snapshot_log(log)
        assert after == before

        log_events = await events.list_events(
            USER, event_types=[EVENT_LOG_ENTRY, EVENT_LESSON_RECORDED]
        )
        checkpoint = await events.storage.get_checkpoint("captains_log", USER)
        assert checkpoint["last_event_id"] == log_events[-1]["id"]

    async def test_append_failure_never_blocks_digest(self, db_manager, broken_events):
        log = CaptainsLogService(db_manager, FORMATION_ID, event_log=broken_events)
        log.queue_turn("We founded Automaze today.", "Congratulations.", USER)
        totals = await log.run_periodic_summarization(FakeModel())
        assert totals["entries"] == 1
        entries = await log.storage.list_entries(USER)
        assert entries[0]["derived_from_event_ids"] == []

    async def test_append_failure_never_blocks_record_lesson(self, db_manager, broken_events):
        log = CaptainsLogService(db_manager, FORMATION_ID, event_log=broken_events)
        lesson = await log.record_lesson(USER, "memory_agent", "Stay calm")
        assert lesson["rule"] == "Stay calm"


# ----------------------------------------------------------------------
# Flat-fact (vector) projection
# ----------------------------------------------------------------------

EXTRACTION_RESULTS = {
    "extracted_info": [
        {
            "memory": "The user's favorite color is blue",
            "confidence": 0.9,
            "importance": 0.7,
            "collection": "preferences",
        },
        {
            "memory": "Works at Automaze",
            "confidence": 0.85,
            "importance": 0.8,
            "collection": "user_identity",
        },
    ]
}


class TestFlatFactReplay:
    async def seed(self, events):
        overlord = FakeOverlord(events)
        extractor = MemoryExtractor(overlord=overlord)
        turn = await events.record(
            user_id=USER,
            event_type="interaction.turn",
            payload={"user_message": "My favorite color is blue and I work at Automaze."},
            source="interaction",
        )
        await extractor._process_extraction_results(
            EXTRACTION_RESULTS, USER, caused_by_event_id=turn["id"]
        )
        # A non-extraction row (conversation) that must survive rebuilds.
        await overlord.long_term_memory.add(
            content="raw conversation text",
            metadata={"source": "conversation"},
            user_id=USER,
            collection="conversations",
        )
        return overlord

    async def test_wipe_and_replay_reproduces_identical_state(self, events):
        overlord = await self.seed(events)
        events.register_projector(FlatFactProjector(overlord.long_term_memory))

        before = snapshot_flat(overlord.long_term_memory)
        extracted = [row for row in before if row["metadata"].get("source") == "extraction"]
        assert len(extracted) == 2
        fact_events = await events.list_events(USER, event_types=[EVENT_FACT_EXTRACTED])
        assert len(fact_events) == 2
        # Provenance chain: fact -> interaction.turn, and the row -> fact event.
        assert all(e["caused_by"] is not None for e in fact_events)
        assert {row["metadata"]["derived_from_event_id"] for row in extracted} == {
            e["id"] for e in fact_events
        }

        report = await events.rebuild(USER, projection="flat_facts")
        assert report["flat_facts"]["events"] == 2
        assert report["flat_facts"]["failed"] == 0

        after = snapshot_flat(overlord.long_term_memory)
        assert after == before

    async def test_rebuild_preserves_non_extraction_memories(self, events):
        overlord = await self.seed(events)
        events.register_projector(FlatFactProjector(overlord.long_term_memory))

        await events.rebuild(USER, projection="flat_facts")
        conversations = [
            row
            for row in overlord.long_term_memory.rows.values()
            if row["collection"] == "conversations"
        ]
        assert len(conversations) == 1

    async def test_append_failure_never_blocks_fact_storage(self, broken_events):
        overlord = FakeOverlord(broken_events)
        extractor = MemoryExtractor(overlord=overlord)
        await extractor._process_extraction_results(EXTRACTION_RESULTS, USER)
        stored = snapshot_flat(overlord.long_term_memory)
        assert len(stored) == 2
        assert all("derived_from_event_id" not in row["metadata"] for row in stored)

    async def test_no_event_service_keeps_legacy_behavior(self):
        overlord = FakeOverlord(None)
        overlord.memory_events = None
        extractor = MemoryExtractor(overlord=overlord)
        await extractor._process_extraction_results(EXTRACTION_RESULTS, USER)
        assert len(snapshot_flat(overlord.long_term_memory)) == 2


# ----------------------------------------------------------------------
# All three projections in one rebuild pass
# ----------------------------------------------------------------------


class TestFullRebuild:
    async def test_rebuild_all_registered_projections(self, db_manager, events):
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        log = CaptainsLogService(db_manager, FORMATION_ID, event_log=events)
        overlord = FakeOverlord(events)
        events.register_projector(KnowledgeGraphProjector(graph))
        events.register_projector(CaptainsLogProjector(log))
        events.register_projector(FlatFactProjector(overlord.long_term_memory))

        await graph.store_extraction(
            USER,
            {
                "entities": [{"name": "Acme", "type": "company", "confidence": 0.9}],
                "relationships": [],
            },
        )
        log.queue_turn("We founded Automaze today.", "Congratulations.", USER)
        await log.run_periodic_summarization(FakeModel())
        extractor = MemoryExtractor(overlord=overlord)
        await extractor._process_extraction_results(EXTRACTION_RESULTS, USER)

        before = (
            await snapshot_graph(graph),
            await snapshot_log(log),
            snapshot_flat(overlord.long_term_memory),
        )
        report = await events.rebuild(USER)
        assert set(report) == {"knowledge_graph", "captains_log", "flat_facts"}
        assert all(section["failed"] == 0 for section in report.values())
        after = (
            await snapshot_graph(graph),
            await snapshot_log(log),
            snapshot_flat(overlord.long_term_memory),
        )
        assert after == before
