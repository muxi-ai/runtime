"""Unit tests for Memory Revamp Phase 1: graph algorithm backends.

NetworkXAlgorithms runs against real storage on SQLite (the embedded
backend's production path). PgRoutingAlgorithms cannot execute without a
pgRouting-enabled PostgreSQL, so its tests pin the generated SQL and
parameter handling through a capturing fake session; live execution parity
is covered by test_knowledge_graph_parity.py when a DSN is provided.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.algorithms import (
    NetworkXAlgorithms,
    PgRoutingAlgorithms,
    _quote_literal,
)
from muxi.runtime.services.memory.graph.storage import KnowledgeGraphStorage

FORMATION_ID = "kg-test-formation"


async def seed_fixture_graph(storage, user_id="u1"):
    """Seed the canonical fixture graph used across algorithm tests.

    User -[founded 0.95]-> Automaze -[building 0.9]-> MUXI
    User -[knows 0.8]-> Sarah -[works_at 0.85]-> Automaze
    Orphan pair: Alpha -[part_of 0.9]-> Beta (separate component)
    """
    ids = {}
    for entity_type, name, confidence in [
        ("person", "User", 0.95),
        ("company", "Automaze", 0.95),
        ("project", "MUXI", 0.9),
        ("person", "Sarah", 0.85),
        ("topic", "Alpha", 0.9),
        ("topic", "Beta", 0.9),
    ]:
        entity = await storage.upsert_entity(user_id, entity_type, name, confidence=confidence)
        ids[name] = entity["id"]

    await storage.upsert_relationship(
        user_id, ids["User"], ids["Automaze"], "founded", confidence=0.95
    )
    await storage.upsert_relationship(
        user_id, ids["Automaze"], ids["MUXI"], "building", confidence=0.9
    )
    await storage.upsert_relationship(user_id, ids["User"], ids["Sarah"], "knows", confidence=0.8)
    await storage.upsert_relationship(
        user_id, ids["Sarah"], ids["Automaze"], "works_at", confidence=0.85
    )
    await storage.upsert_relationship(user_id, ids["Alpha"], ids["Beta"], "part_of", confidence=0.9)
    return ids


@pytest.fixture
def storage(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/kg.db")
    db_manager.create_tables(Base.metadata)
    yield KnowledgeGraphStorage(db_manager, FORMATION_ID)
    db_manager.engine.dispose()


@pytest.fixture
def algorithms(storage):
    return NetworkXAlgorithms(storage, cache_size=2)


class TestNetworkXAlgorithms:
    async def test_shortest_path_prefers_high_confidence(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        # Direct edge User->Automaze (cost 0.05) beats User->Sarah->Automaze
        path = await algorithms.shortest_path(ids["User"], ids["Automaze"], user_id="u1")
        assert path == [ids["User"], ids["Automaze"]]

    async def test_shortest_path_multi_hop(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        path = await algorithms.shortest_path(ids["User"], ids["MUXI"], user_id="u1")
        assert path == [ids["User"], ids["Automaze"], ids["MUXI"]]

    async def test_shortest_path_no_route(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        assert await algorithms.shortest_path(ids["User"], ids["Alpha"], user_id="u1") == []

    async def test_shortest_path_unknown_node(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        assert await algorithms.shortest_path(ids["User"], 999999, user_id="u1") == []

    async def test_shortest_path_rel_type_filter(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        path = await algorithms.shortest_path(
            ids["User"], ids["Automaze"], user_id="u1", rel_types=["knows", "works_at"]
        )
        assert path == [ids["User"], ids["Sarah"], ids["Automaze"]]

    async def test_k_hop_neighbors(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        one_hop = await algorithms.k_hop_neighbors(ids["User"], 1, user_id="u1")
        assert one_hop == sorted([ids["Automaze"], ids["Sarah"]])

        two_hop = await algorithms.k_hop_neighbors(ids["User"], 2, user_id="u1")
        assert two_hop == sorted([ids["Automaze"], ids["Sarah"], ids["MUXI"]])

    async def test_weighted_neighbors_ranked_by_aggregate_cost(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        ranked = await algorithms.weighted_neighbors(ids["User"], user_id="u1", limit=10)
        assert [node for node, _ in ranked] == [ids["Automaze"], ids["MUXI"], ids["Sarah"]]
        costs = [cost for _, cost in ranked]
        assert costs == sorted(costs)

    async def test_weighted_neighbors_limit(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        ranked = await algorithms.weighted_neighbors(ids["User"], user_id="u1", limit=1)
        assert len(ranked) == 1

    async def test_connected_components(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        components = await algorithms.connected_components(user_id="u1")
        assert len(components) == 2
        assert components[0] == {ids["User"], ids["Automaze"], ids["MUXI"], ids["Sarah"]}
        assert components[1] == {ids["Alpha"], ids["Beta"]}

    async def test_path_explain_returns_edges(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        steps = await algorithms.path_explain(ids["User"], ids["MUXI"], user_id="u1")
        assert [node for node, _ in steps] == [ids["User"], ids["Automaze"], ids["MUXI"]]
        assert steps[-1][1] is None  # arrival step carries no edge
        assert all(edge is not None for _, edge in steps[:-1])

    async def test_cache_invalidation_sees_new_edges(self, storage, algorithms):
        ids = await seed_fixture_graph(storage)
        assert await algorithms.shortest_path(ids["User"], ids["Alpha"], user_id="u1") == []

        # New bridging edge is invisible until the cache is invalidated
        await storage.upsert_relationship(
            "u1", ids["User"], ids["Alpha"], "interested_in", confidence=0.9
        )
        assert await algorithms.shortest_path(ids["User"], ids["Alpha"], user_id="u1") == []

        algorithms.invalidate("u1")
        path = await algorithms.shortest_path(ids["User"], ids["Alpha"], user_id="u1")
        assert path == [ids["User"], ids["Alpha"]]

    async def test_lru_eviction(self, storage, algorithms):
        await seed_fixture_graph(storage, user_id="u1")
        await algorithms.k_hop_neighbors(1, 1, user_id="u1")
        await algorithms.k_hop_neighbors(1, 1, user_id="u2")
        await algorithms.k_hop_neighbors(1, 1, user_id="u3")
        assert len(algorithms._cache) == 2  # cache_size=2, oldest evicted
        assert "u1" not in algorithms._cache


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((str(query), params))
        return FakeResult(self.rows)


class FakeDBManager:
    database_type = "postgresql"

    def __init__(self, rows=None):
        self.session = FakeSession(rows or [])

    @asynccontextmanager
    async def get_async_session(self):
        yield self.session


class TestPgRoutingSQL:
    """Pin the pgRouting query shapes and the canonical edge-source builder."""

    def _algorithms(self, rows=None):
        db_manager = FakeDBManager(rows)
        return PgRoutingAlgorithms(db_manager, FORMATION_ID), db_manager.session

    def test_edge_source_scoping(self):
        algorithms, _ = self._algorithms()
        sql = algorithms._edge_source_sql("u1")
        assert "r.user_id = 'u1'" in sql
        assert f"r.formation_id = '{FORMATION_ID}'" in sql
        assert "r.status = 'active'" in sql
        assert "(1.0 - COALESCE(r.confidence, 0.0)) AS cost" in sql

    def test_edge_source_uniform_cost(self):
        algorithms, _ = self._algorithms()
        sql = algorithms._edge_source_sql("u1", uniform_cost=True)
        assert "1.0 AS cost" in sql

    def test_edge_source_rel_type_filter(self):
        algorithms, _ = self._algorithms()
        sql = algorithms._edge_source_sql("u1", rel_types=["Knows", "works_at"])
        assert "r.type IN ('knows', 'works_at')" in sql

    def test_edge_source_quotes_literals(self):
        algorithms, _ = self._algorithms()
        sql = algorithms._edge_source_sql("u'; DROP TABLE x; --")
        assert "r.user_id = 'u''; DROP TABLE x; --'" in sql

    def test_quote_literal(self):
        assert _quote_literal("plain") == "'plain'"
        assert _quote_literal("O'Brien") == "'O''Brien'"

    async def test_shortest_path_query(self):
        algorithms, session = self._algorithms(rows=[(1,), (2,), (3,)])
        path = await algorithms.shortest_path(1, 3, user_id="u1")
        assert path == [1, 2, 3]
        query, params = session.calls[0]
        assert "pgr_dijkstra" in query
        assert "directed := false" in query
        assert params["start"] == 1 and params["end"] == 3
        assert "r.user_id = 'u1'" in params["edges"]

    async def test_k_hop_query_uses_driving_distance(self):
        algorithms, session = self._algorithms(rows=[(2,), (4,)])
        neighbors = await algorithms.k_hop_neighbors(1, 2, user_id="u1")
        assert neighbors == [2, 4]
        query, params = session.calls[0]
        assert "pgr_drivingDistance" in query
        assert params["distance"] == 2.0
        assert "1.0 AS cost" in params["edges"]  # hop semantics need uniform cost

    async def test_weighted_neighbors_query(self):
        algorithms, session = self._algorithms(rows=[(2, 0.05), (3, 0.15)])
        ranked = await algorithms.weighted_neighbors(1, user_id="u1", limit=5)
        assert ranked == [(2, 0.05), (3, 0.15)]
        query, params = session.calls[0]
        assert "pgr_dijkstra" in query
        assert "array_agg(e.id) FROM kg_entities" in query
        assert params["limit"] == 5

    async def test_connected_components_query(self):
        algorithms, session = self._algorithms(rows=[(1, 1), (1, 2), (2, 5)])
        components = await algorithms.connected_components(user_id="u1")
        assert components == [{1, 2}, {5}]
        query, _ = session.calls[0]
        assert "pgr_connectedComponents" in query

    async def test_path_explain_query(self):
        algorithms, session = self._algorithms(rows=[(1, 10), (2, 11), (3, -1)])
        steps = await algorithms.path_explain(1, 3, user_id="u1")
        assert steps == [(1, 10), (2, 11), (3, None)]

    def test_invalidate_is_noop(self):
        algorithms, _ = self._algorithms()
        algorithms.invalidate("u1")  # must not raise
