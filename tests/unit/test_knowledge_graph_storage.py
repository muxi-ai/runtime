"""Unit tests for Memory Revamp Phase 1: knowledge graph storage round-trips.

Covers entity/relationship upserts, attribute merging, user isolation, the
active-only edge iterator, and the PRD contradiction-detection model
(conflict cross-referencing and confidence-based supersession with full
retention of old facts).
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.models import (
    STATUS_ACTIVE,
    STATUS_CONFLICTED,
    STATUS_SUPERSEDED,
)
from muxi.runtime.services.memory.graph.storage import KnowledgeGraphStorage, normalize_type

FORMATION_ID = "kg-test-formation"


@pytest.fixture
def storage(tmp_path):
    """Graph storage backed by a file SQLite database.

    A file (not :memory:) is required because the DatabaseManager keeps
    separate sync and async engines; both must see the same tables.
    """
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/kg.db")
    db_manager.create_tables(Base.metadata)
    yield KnowledgeGraphStorage(db_manager, FORMATION_ID)
    db_manager.engine.dispose()


class TestEntityRoundTrips:
    async def test_insert_and_get(self, storage):
        created = await storage.upsert_entity(
            "u1", "company", "Automaze", attributes={"type": "services"}, confidence=0.95
        )
        assert created["id"] > 0
        assert created["status"] == STATUS_ACTIVE

        fetched = await storage.get_entity("u1", "company", "Automaze")
        assert fetched == created

    async def test_get_by_id(self, storage):
        created = await storage.upsert_entity("u1", "person", "Sarah")
        assert (await storage.get_entity_by_id(created["id"]))["name"] == "Sarah"
        assert await storage.get_entity_by_id(999999) is None

    async def test_upsert_merges_attributes_and_keeps_max_confidence(self, storage):
        await storage.upsert_entity(
            "u1", "person", "Sarah", attributes={"role": "CTO"}, confidence=0.9
        )
        updated = await storage.upsert_entity(
            "u1", "person", "Sarah", attributes={"rel": "colleague"}, confidence=0.7
        )
        assert updated["attributes"] == {"role": "CTO", "rel": "colleague"}
        assert updated["confidence"] == 0.9  # max wins, lower does not regress

    async def test_upsert_does_not_duplicate(self, storage):
        first = await storage.upsert_entity("u1", "person", "Sarah")
        second = await storage.upsert_entity("u1", "person", "Sarah")
        assert first["id"] == second["id"]
        assert len(await storage.list_entities("u1")) == 1

    async def test_type_normalization(self, storage):
        created = await storage.upsert_entity("u1", " Person ", "Sarah")
        assert created["type"] == "person"
        assert normalize_type("Lives In") == "lives_in"

    async def test_user_isolation(self, storage):
        await storage.upsert_entity("u1", "person", "Sarah")
        await storage.upsert_entity("u2", "person", "Bob")
        assert [e["name"] for e in await storage.list_entities("u1")] == ["Sarah"]
        assert [e["name"] for e in await storage.list_entities("u2")] == ["Bob"]

    async def test_list_filters_by_type(self, storage):
        await storage.upsert_entity("u1", "person", "Sarah")
        await storage.upsert_entity("u1", "company", "Acme")
        people = await storage.list_entities("u1", entity_type="person")
        assert [e["name"] for e in people] == ["Sarah"]

    async def test_get_entities_by_ids_batched(self, storage):
        sarah = await storage.upsert_entity("u1", "person", "Sarah")
        acme = await storage.upsert_entity("u1", "company", "Acme")
        await storage.upsert_entity("u1", "project", "MUXI")

        rows = await storage.get_entities_by_ids({sarah["id"], acme["id"]})
        assert {row["name"] for row in rows} == {"Sarah", "Acme"}

    async def test_get_entities_by_ids_empty_and_unknown(self, storage):
        assert await storage.get_entities_by_ids([]) == []
        assert await storage.get_entities_by_ids([999999]) == []


class TestRelationshipRoundTrips:
    async def _entities(self, storage):
        user = await storage.upsert_entity("u1", "person", "User", confidence=0.95)
        acme = await storage.upsert_entity("u1", "company", "Acme", confidence=0.95)
        london = await storage.upsert_entity("u1", "location", "London", confidence=0.9)
        berlin = await storage.upsert_entity("u1", "location", "Berlin", confidence=0.9)
        return user, acme, london, berlin

    async def test_insert_and_list(self, storage):
        user, acme, _, _ = await self._entities(storage)
        created = await storage.upsert_relationship(
            "u1", user["id"], acme["id"], "works_at", confidence=0.92
        )
        assert created["status"] == STATUS_ACTIVE

        listed = await storage.list_relationships("u1")
        assert [r["id"] for r in listed] == [created["id"]]

        fetched = await storage.get_relationship_by_id(created["id"])
        assert fetched["type"] == "works_at"

    async def test_duplicate_edge_merges(self, storage):
        user, acme, _, _ = await self._entities(storage)
        first = await storage.upsert_relationship(
            "u1", user["id"], acme["id"], "works_at", attributes={"since": "2024"}, confidence=0.9
        )
        second = await storage.upsert_relationship(
            "u1", user["id"], acme["id"], "works_at", attributes={"role": "CEO"}, confidence=0.8
        )
        assert first["id"] == second["id"]
        assert second["attributes"] == {"since": "2024", "role": "CEO"}
        assert second["confidence"] == 0.9
        assert len(await storage.list_relationships("u1", status=None)) == 1

    async def test_non_exclusive_predicates_coexist(self, storage):
        user, acme, _, _ = await self._entities(storage)
        sarah = await storage.upsert_entity("u1", "person", "Sarah")
        bob = await storage.upsert_entity("u1", "person", "Bob")
        first = await storage.upsert_relationship("u1", user["id"], sarah["id"], "knows")
        second = await storage.upsert_relationship("u1", user["id"], bob["id"], "knows")
        assert first["status"] == STATUS_ACTIVE
        assert second["status"] == STATUS_ACTIVE


class TestContradictionDetection:
    """PRD contradiction model on exclusive predicates."""

    async def test_conflict_marks_both_and_cross_references(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        london = await storage.upsert_entity("u1", "location", "London")
        berlin = await storage.upsert_entity("u1", "location", "Berlin")

        old = await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.9
        )
        new = await storage.upsert_relationship(
            "u1", user["id"], berlin["id"], "lives_in", confidence=0.92
        )

        old_row = await storage.get_relationship_by_id(old["id"])
        assert old_row["status"] == STATUS_CONFLICTED
        assert old_row["contradicted_by"] == new["id"]
        assert new["status"] == STATUS_CONFLICTED
        assert new["contradicted_by"] == old["id"]

    async def test_high_confidence_supersedes(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        london = await storage.upsert_entity("u1", "location", "London")
        berlin = await storage.upsert_entity("u1", "location", "Berlin")

        old = await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.5
        )
        new = await storage.upsert_relationship(
            "u1", user["id"], berlin["id"], "lives_in", confidence=0.95
        )

        old_row = await storage.get_relationship_by_id(old["id"])
        assert old_row["status"] == STATUS_SUPERSEDED
        assert old_row["superseded_by"] == new["id"]
        assert new["status"] == STATUS_ACTIVE

    async def test_old_fact_retained_not_deleted(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        london = await storage.upsert_entity("u1", "location", "London")
        berlin = await storage.upsert_entity("u1", "location", "Berlin")
        await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.5
        )
        await storage.upsert_relationship(
            "u1", user["id"], berlin["id"], "lives_in", confidence=0.95
        )
        all_rows = await storage.list_relationships("u1", status=None)
        assert len(all_rows) == 2  # history accumulates, never overwritten

    async def test_multi_conflict_back_link_is_most_recent(self, storage):
        """With several conflicting rows, the new fact's contradicted_by
        deterministically points at the most recent one."""
        user = await storage.upsert_entity("u1", "person", "User")
        london = await storage.upsert_entity("u1", "location", "London")
        berlin = await storage.upsert_entity("u1", "location", "Berlin")
        paris = await storage.upsert_entity("u1", "location", "Paris")

        # Two active lives_in rows: London superseded by Berlin, then revived.
        first = await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.5
        )
        second = await storage.upsert_relationship(
            "u1", user["id"], berlin["id"], "lives_in", confidence=0.95
        )
        await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.7
        )

        third = await storage.upsert_relationship(
            "u1", user["id"], paris["id"], "lives_in", confidence=0.9
        )

        first_row = await storage.get_relationship_by_id(first["id"])
        second_row = await storage.get_relationship_by_id(second["id"])
        assert first_row["status"] == STATUS_CONFLICTED
        assert first_row["contradicted_by"] == third["id"]
        assert second_row["status"] == STATUS_CONFLICTED
        assert second_row["contradicted_by"] == third["id"]
        # Back-link points at the most recent conflicting row, not whichever
        # the loop visited last.
        assert third["contradicted_by"] == max(first["id"], second["id"])

    async def test_reasserted_fact_revives_superseded_edge(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        london = await storage.upsert_entity("u1", "location", "London")
        berlin = await storage.upsert_entity("u1", "location", "Berlin")
        old = await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.5
        )
        await storage.upsert_relationship(
            "u1", user["id"], berlin["id"], "lives_in", confidence=0.95
        )
        revived = await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.6
        )
        assert revived["id"] == old["id"]
        assert revived["status"] == STATUS_ACTIVE
        assert revived["superseded_by"] is None


class TestEdgeIterator:
    async def test_iter_edges_active_only(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        london = await storage.upsert_entity("u1", "location", "London")
        berlin = await storage.upsert_entity("u1", "location", "Berlin")
        acme = await storage.upsert_entity("u1", "company", "Acme")

        await storage.upsert_relationship("u1", user["id"], acme["id"], "works_at")
        await storage.upsert_relationship(
            "u1", user["id"], london["id"], "lives_in", confidence=0.9
        )
        # Conflicts both lives_in edges out of the active set
        await storage.upsert_relationship(
            "u1", user["id"], berlin["id"], "lives_in", confidence=0.9
        )

        edges = await storage.iter_edges("u1")
        assert [e["type"] for e in edges] == ["works_at"]

    async def test_iter_edges_rel_type_filter(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        acme = await storage.upsert_entity("u1", "company", "Acme")
        muxi = await storage.upsert_entity("u1", "project", "MUXI")
        await storage.upsert_relationship("u1", user["id"], acme["id"], "works_at")
        await storage.upsert_relationship("u1", acme["id"], muxi["id"], "building")

        edges = await storage.iter_edges("u1", rel_types=["building"])
        assert [e["type"] for e in edges] == ["building"]

    async def test_iter_edges_user_scoped(self, storage):
        user = await storage.upsert_entity("u1", "person", "User")
        acme = await storage.upsert_entity("u1", "company", "Acme")
        await storage.upsert_relationship("u1", user["id"], acme["id"], "works_at")
        assert await storage.iter_edges("u2") == []
