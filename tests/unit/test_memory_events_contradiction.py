"""Contradiction-detection audit tests (Memory Substrate Phase 2c).

The knowledge graph already marks conflicting/superseded facts at write
time; the substrate now records each detection as a ``fact.contradicted``
event linked (caused_by) to the extraction that triggered it. Replay
purity: rebuilds re-mark the rows but never re-record the audit events.
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import KnowledgeGraphProjector, MemoryEventService
from muxi.runtime.services.memory.events.models import EVENT_FACT_CONTRADICTED
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService

FORMATION_ID = "contradiction-test-formation"
USER = "u1"


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/contradiction.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def events(db_manager):
    return MemoryEventService(db_manager, FORMATION_ID)


@pytest.fixture
def graph(db_manager, events):
    service = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
    events.register_projector(KnowledgeGraphProjector(service))
    return service


def residence(city, confidence):
    return {
        "entities": [{"name": city, "type": "location", "confidence": 0.9}],
        "relationships": [
            {
                "from": "User",
                "from_type": "person",
                "to": city,
                "to_type": "location",
                "type": "lives_in",
                "confidence": confidence,
            }
        ],
    }


class TestContradictionEvents:
    async def test_conflict_records_fact_contradicted_event(self, events, graph):
        await graph.store_extraction(USER, residence("London", 0.9))
        await graph.store_extraction(USER, residence("Berlin", 0.88))

        recorded = await events.list_events(USER, event_types=[EVENT_FACT_CONTRADICTED])
        assert len(recorded) == 1
        payload = recorded[0]["payload"]
        assert payload["relationship_type"] == "lives_in"
        assert payload["detection"] == "conflicted"
        assert payload["existing_relationship_public_id"]
        assert payload["new_relationship_public_id"]
        # Audit event links back to the extraction that triggered it.
        graph_events = await events.list_events(USER, event_types=["graph.extracted"])
        assert recorded[0]["caused_by"] == graph_events[-1]["id"]

    async def test_supersede_records_detection_kind(self, events, graph):
        await graph.store_extraction(USER, residence("London", 0.5))
        await graph.store_extraction(USER, residence("Berlin", 0.95))

        recorded = await events.list_events(USER, event_types=[EVENT_FACT_CONTRADICTED])
        assert len(recorded) == 1
        assert recorded[0]["payload"]["detection"] == "superseded"

    async def test_projection_rows_marked(self, events, graph):
        await graph.store_extraction(USER, residence("London", 0.9))
        await graph.store_extraction(USER, residence("Berlin", 0.88))
        relationships = await graph.storage.list_relationships(USER, status=None)
        statuses = sorted(r["status"] for r in relationships)
        assert statuses == ["conflicted", "conflicted"]

    async def test_duplicate_fact_is_not_a_contradiction(self, events, graph):
        await graph.store_extraction(USER, residence("London", 0.9))
        await graph.store_extraction(USER, residence("London", 0.92))
        assert await events.list_events(USER, event_types=[EVENT_FACT_CONTRADICTED]) == []

    async def test_rebuild_replays_marking_without_new_audit_events(self, events, graph):
        await graph.store_extraction(USER, residence("London", 0.9))
        await graph.store_extraction(USER, residence("Berlin", 0.88))
        before = await events.list_events(USER, event_types=[EVENT_FACT_CONTRADICTED])

        await events.rebuild(USER, projection="knowledge_graph")

        after = await events.list_events(USER, event_types=[EVENT_FACT_CONTRADICTED])
        assert [e["id"] for e in after] == [e["id"] for e in before]  # replay purity
        relationships = await graph.storage.list_relationships(USER, status=None)
        assert sorted(r["status"] for r in relationships) == ["conflicted", "conflicted"]

    async def test_event_first_path_records_contradictions(self, db_manager):
        events = MemoryEventService(db_manager, FORMATION_ID, config={"event_first": True})
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(KnowledgeGraphProjector(graph))

        await graph.store_extraction(USER, residence("London", 0.9))
        await graph.store_extraction(USER, residence("Berlin", 0.88))

        recorded = await events.list_events(USER, event_types=[EVENT_FACT_CONTRADICTED])
        assert len(recorded) == 1
        assert recorded[0]["payload"]["detection"] == "conflicted"
