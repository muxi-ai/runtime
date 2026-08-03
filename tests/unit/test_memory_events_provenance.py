"""Provenance tests for the Memory Event Substrate (Phase 2c).

"Why do you think X?": a knowledge graph fact must resolve, through its
``derived_from_event_ids``, to the extraction event that wrote it and --
via ``caused_by`` -- to the interaction turn that produced the extraction.
Covers the causation-chain walk (root-first, cycle-cut, user-scoped) and
the entity-level assembly used by GET /v1/memories/provenance.
"""

from __future__ import annotations

import pytest

from muxi.runtime.datatypes.observability import RequestContext
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import KnowledgeGraphProjector, MemoryEventService
from muxi.runtime.services.memory.events.provenance import entity_provenance, event_provenance
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.observability.context import _current_request_context

FORMATION_ID = "provenance-test-formation"
USER = "u1"


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/provenance.db")
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


async def seed_conversation(events, graph):
    """One turn -> one graph extraction, linked via caused_by."""
    turn = await events.record(
        user_id=USER,
        event_type="interaction.turn",
        payload={"user_message": "I live in London and work at Acme."},
        source="interaction",
    )
    await graph.store_extraction(
        USER,
        {
            "entities": [
                {"name": "User", "type": "person", "confidence": 0.95},
                {"name": "London", "type": "location", "confidence": 0.9},
                {"name": "Acme", "type": "company", "confidence": 0.9},
            ],
            "relationships": [
                {
                    "from": "User",
                    "from_type": "person",
                    "to": "London",
                    "to_type": "location",
                    "type": "lives_in",
                    "confidence": 0.9,
                },
                {
                    "from": "User",
                    "from_type": "person",
                    "to": "Acme",
                    "to_type": "company",
                    "type": "works_at",
                    "confidence": 0.85,
                },
            ],
        },
        caused_by=turn["id"],
    )
    return turn


class TestProvenanceChain:
    async def test_chain_walks_causation_root_first(self, events, graph):
        turn = await seed_conversation(events, graph)
        graph_events = await events.list_events(USER, event_types=["graph.extracted"])
        chain = await events.provenance_chain(USER, graph_events[0]["id"])
        assert [e["event_type"] for e in chain] == ["interaction.turn", "graph.extracted"]
        assert chain[0]["id"] == turn["id"]

    async def test_chain_for_root_event_is_itself(self, events, graph):
        turn = await seed_conversation(events, graph)
        chain = await events.provenance_chain(USER, turn["id"])
        assert len(chain) == 1
        assert chain[0]["id"] == turn["id"]

    async def test_chain_is_user_scoped(self, events, graph):
        await seed_conversation(events, graph)
        graph_events = await events.list_events(USER, event_types=["graph.extracted"])
        assert await events.provenance_chain("someone_else", graph_events[0]["id"]) == []

    async def test_unknown_event_returns_empty_chain(self, events):
        assert await events.provenance_chain(USER, 424242) == []

    async def test_chain_surfaces_originating_request_id(self, events, graph):
        # Every hop recorded inside a request carries that request's id,
        # so a chain answers "which request produced this?".
        token = _current_request_context.set(RequestContext(id="req_prov1"))
        try:
            await seed_conversation(events, graph)
        finally:
            _current_request_context.reset(token)
        graph_events = await events.list_events(USER, event_types=["graph.extracted"])
        chain = await events.provenance_chain(USER, graph_events[0]["id"])
        assert [e["request_id"] for e in chain] == ["req_prov1", "req_prov1"]

    async def test_event_provenance_renders_request_id(self, events, graph):
        token = _current_request_context.set(RequestContext(id="req_prov2"))
        try:
            await seed_conversation(events, graph)
        finally:
            _current_request_context.reset(token)
        graph_events = await events.list_events(USER, event_types=["graph.extracted"])
        result = await event_provenance(events, USER, graph_events[0]["public_id"])
        assert result["event"]["request_id"] == "req_prov2"
        assert [e["request_id"] for e in result["chain"]] == ["req_prov2", "req_prov2"]


class TestEntityProvenance:
    async def test_why_do_you_think_i_live_in_london(self, events, graph):
        await seed_conversation(events, graph)
        result = await entity_provenance(events, graph, USER, "London", decay=events.decay)
        assert result is not None
        assert result["entity"]["name"] == "London"
        assert result["entity"]["events"]  # the entity itself has a chain

        lives_in = next(fact for fact in result["facts"] if fact["relationship_type"] == "lives_in")
        assert lives_in["statement"] == "User -[lives_in]-> London"
        assert lives_in["effective_confidence"] == pytest.approx(0.9, abs=0.01)
        # The full chain: interaction.turn -> graph.extracted.
        (chain,) = lives_in["events"]
        assert [e["event_type"] for e in chain] == ["interaction.turn", "graph.extracted"]
        assert chain[0]["source"] == "interaction"

    async def test_entity_name_matching_is_case_insensitive(self, events, graph):
        await seed_conversation(events, graph)
        assert await entity_provenance(events, graph, USER, "london") is not None

    async def test_unknown_entity_returns_none(self, events, graph):
        await seed_conversation(events, graph)
        assert await entity_provenance(events, graph, USER, "Atlantis") is None

    async def test_contradicted_facts_stay_explainable(self, events, graph):
        await seed_conversation(events, graph)
        # A conflicting residence claim (below the supersede delta).
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
                        "confidence": 0.88,
                    }
                ],
            },
        )
        result = await entity_provenance(events, graph, USER, "User")
        statuses = {fact["statement"]: fact["status"] for fact in result["facts"]}
        assert statuses["User -[lives_in]-> London"] == "conflicted"
        assert statuses["User -[lives_in]-> Berlin"] == "conflicted"


class TestEventProvenance:
    async def test_lookup_by_public_id(self, events, graph):
        await seed_conversation(events, graph)
        graph_events = await events.list_events(USER, event_types=["graph.extracted"])
        result = await event_provenance(events, USER, graph_events[0]["public_id"])
        assert result is not None
        assert result["event"]["event_type"] == "graph.extracted"
        assert [e["event_type"] for e in result["chain"]] == [
            "interaction.turn",
            "graph.extracted",
        ]

    async def test_unknown_public_id_returns_none(self, events):
        assert await event_provenance(events, USER, "nope") is None
