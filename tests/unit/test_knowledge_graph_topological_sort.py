"""Unit tests for Memory Revamp Phase 2: GraphAlgorithms.topological_sort.

Covers the shared lexicographic Kahn sort (determinism, cycle detection),
the NetworkX backend's entity-graph and registered-DAG paths, and provider
registration errors. The pgRouting backend shares the same sort function
and provider registry by construction; its edge-fetch SQL is exercised by
the parity suite when a pgRouting-enabled DSN is provided.
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.algorithms import (
    NetworkXAlgorithms,
    lexicographic_topological_sort,
)
from muxi.runtime.services.memory.graph.storage import KnowledgeGraphStorage

FORMATION_ID = "kg-test-formation"


@pytest.fixture
def storage(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/kg.db")
    db_manager.create_tables(Base.metadata)
    yield KnowledgeGraphStorage(db_manager, FORMATION_ID)
    db_manager.engine.dispose()


@pytest.fixture
def algorithms(storage):
    return NetworkXAlgorithms(storage)


class TestSharedSort:
    def test_orders_sources_first(self):
        assert lexicographic_topological_sort((), [(1, 2), (2, 3)]) == [1, 2, 3]

    def test_lexicographic_tie_breaking(self):
        # 5 and 2 are both ready after 1; the smaller id comes first.
        assert lexicographic_topological_sort((), [(1, 5), (1, 2), (2, 9)]) == [1, 2, 5, 9]

    def test_isolated_nodes_included(self):
        assert lexicographic_topological_sort([7, 3], [(3, 5)]) == [3, 5, 7]

    def test_cycle_returns_empty(self):
        assert lexicographic_topological_sort((), [(1, 2), (2, 1)]) == []

    def test_self_loop_returns_empty(self):
        assert lexicographic_topological_sort((), [(1, 1)]) == []

    def test_empty_graph(self):
        assert lexicographic_topological_sort((), []) == []


class TestEntityGraphSort:
    async def _seed_chain(self, storage):
        user = await storage.upsert_entity("u1", "person", "User", confidence=0.9)
        automaze = await storage.upsert_entity("u1", "company", "Automaze", confidence=0.9)
        muxi = await storage.upsert_entity("u1", "project", "MUXI", confidence=0.9)
        await storage.upsert_relationship(
            "u1", user["id"], automaze["id"], "founded", confidence=0.9
        )
        await storage.upsert_relationship(
            "u1", automaze["id"], muxi["id"], "building", confidence=0.9
        )
        return user, automaze, muxi

    async def test_entity_graph_order(self, storage, algorithms):
        user, automaze, muxi = await self._seed_chain(storage)
        order = await algorithms.topological_sort(user_id="u1")
        assert order == [user["id"], automaze["id"], muxi["id"]]

    async def test_isolated_entities_included(self, storage, algorithms):
        """Entities without relationships must still appear in the order.

        The node set comes from storage independently of the edge set --
        the same contract the pgRouting backend implements with its nodes
        query -- so isolated entities cannot vanish on either backend.
        """
        user, automaze, muxi = await self._seed_chain(storage)
        isolated = await storage.upsert_entity("u1", "topic", "Isolated", confidence=0.9)
        algorithms.invalidate("u1")

        order = await algorithms.topological_sort(user_id="u1")
        assert isolated["id"] in order
        assert set(order) == {user["id"], automaze["id"], muxi["id"], isolated["id"]}
        # Edge constraints still hold around the isolated node.
        assert order.index(user["id"]) < order.index(automaze["id"]) < order.index(muxi["id"])

    async def test_node_source_is_active_entities_only(self, storage, algorithms):
        """The fetched node set is active entities, matching the edge filter."""
        from sqlalchemy import text

        from muxi.runtime.services.memory.graph.models import STATUS_SUPERSEDED

        user, automaze, muxi = await self._seed_chain(storage)
        isolated = await storage.upsert_entity("u1", "topic", "Isolated", confidence=0.9)
        with storage.db_manager.engine.connect() as conn:
            conn.execute(
                text("UPDATE kg_entities SET status = :status WHERE id = :id"),
                {"status": STATUS_SUPERSEDED, "id": isolated["id"]},
            )
            conn.commit()
        algorithms.invalidate("u1")

        assert isolated["id"] not in await storage.iter_entity_ids("u1")
        order = await algorithms.topological_sort(user_id="u1")
        assert isolated["id"] not in order
        assert order == [user["id"], automaze["id"], muxi["id"]]

    async def test_cyclic_entity_graph_returns_empty(self, storage, algorithms):
        user, automaze, _ = await self._seed_chain(storage)
        await storage.upsert_relationship(
            "u1", automaze["id"], user["id"], "part_of", confidence=0.9
        )
        algorithms.invalidate("u1")
        assert await algorithms.topological_sort(user_id="u1") == []

    async def test_empty_graph_returns_empty(self, algorithms):
        assert await algorithms.topological_sort(user_id="nobody") == []


class TestRegisteredDagSort:
    async def test_registered_provider_used(self, algorithms):
        async def edges(user_id):
            assert user_id == "u1"
            return [(10, 20), (20, 30), (10, 30)]

        algorithms.register_dag_edge_provider("captains_log_sources", edges)
        order = await algorithms.topological_sort(user_id="u1", dag="captains_log_sources")
        assert order == [10, 20, 30]

    async def test_unknown_dag_raises(self, algorithms):
        with pytest.raises(ValueError, match="no edge provider registered"):
            await algorithms.topological_sort(user_id="u1", dag="unknown_dag")
