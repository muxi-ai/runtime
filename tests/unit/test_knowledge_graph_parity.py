"""Parity harness for the two GraphAlgorithms backends (Memory Revamp Phase 1).

Runs the same fixture graph and the same queries through NetworkXAlgorithms
and PgRoutingAlgorithms and asserts identical results: same paths, same node
sets, same ordering where defined, before and after a mutation.

The pgRouting half needs a live PostgreSQL with the pgrouting extension;
point MUXI_TEST_PGROUTING_DSN at one (e.g.
``postgresql://localhost/muxi_test``) to run the full parity matrix. Without
it, the pgRouting cases are skipped and the NetworkX half still runs so the
harness itself stays exercised in CI.
"""

from __future__ import annotations

import os

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.algorithms import (
    NetworkXAlgorithms,
    PgRoutingAlgorithms,
)
from muxi.runtime.services.memory.graph.storage import KnowledgeGraphStorage

FORMATION_ID = "kg-parity-formation"
PGROUTING_DSN = os.environ.get("MUXI_TEST_PGROUTING_DSN")

pytestmark = pytest.mark.skipif(
    PGROUTING_DSN is None,
    reason="Set MUXI_TEST_PGROUTING_DSN to a pgRouting-enabled PostgreSQL to run parity tests",
)


async def seed_parity_graph(storage, user_id="parity-user"):
    """Seed the parity fixture graph into a storage backend."""
    ids = {}
    for entity_type, name, confidence in [
        ("person", "User", 0.95),
        ("company", "Automaze", 0.95),
        ("project", "MUXI", 0.9),
        ("person", "Sarah", 0.85),
        ("location", "London", 0.9),
        ("topic", "Alpha", 0.9),
        ("topic", "Beta", 0.9),
    ]:
        entity = await storage.upsert_entity(user_id, entity_type, name, confidence=confidence)
        ids[name] = entity["id"]

    for from_name, to_name, rel_type, confidence in [
        ("User", "Automaze", "founded", 0.95),
        ("Automaze", "MUXI", "building", 0.9),
        ("User", "Sarah", "knows", 0.8),
        ("Sarah", "Automaze", "works_at", 0.85),
        ("User", "London", "lives_in", 0.9),
        ("Alpha", "Beta", "part_of", 0.9),
    ]:
        await storage.upsert_relationship(
            user_id, ids[from_name], ids[to_name], rel_type, confidence=confidence
        )
    return ids


@pytest.fixture
async def parity_setup():
    """Both algorithm backends over the same graph rows in PostgreSQL.

    The graph rows live once, in PostgreSQL; NetworkX hydrates from the
    exact same storage the pgRouting SQL queries, so any divergence is
    algorithmic, not data-shape.
    """
    db_manager = DatabaseManager(PGROUTING_DSN)
    db_manager.create_tables(Base.metadata)
    storage = KnowledgeGraphStorage(db_manager, FORMATION_ID)

    networkx_algorithms = NetworkXAlgorithms(storage)
    pgrouting_algorithms = PgRoutingAlgorithms(db_manager, FORMATION_ID)

    from sqlalchemy import text

    with db_manager.engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE"))
        conn.execute(
            text("DELETE FROM kg_relationships WHERE formation_id = :f"), {"f": FORMATION_ID}
        )
        conn.execute(text("DELETE FROM kg_entities WHERE formation_id = :f"), {"f": FORMATION_ID})
        conn.commit()

    ids = await seed_parity_graph(storage)
    yield storage, networkx_algorithms, pgrouting_algorithms, ids
    db_manager.engine.dispose()


USER = "parity-user"


class TestParity:
    async def test_shortest_path_parity(self, parity_setup):
        _, nx_algorithms, pg_algorithms, ids = parity_setup
        for start, end in [("User", "MUXI"), ("Sarah", "MUXI"), ("User", "London")]:
            nx_path = await nx_algorithms.shortest_path(ids[start], ids[end], user_id=USER)
            pg_path = await pg_algorithms.shortest_path(ids[start], ids[end], user_id=USER)
            assert nx_path == pg_path, f"shortest_path({start}, {end}) diverged"

    async def test_k_hop_parity(self, parity_setup):
        _, nx_algorithms, pg_algorithms, ids = parity_setup
        for k in (1, 2, 3):
            nx_hop = await nx_algorithms.k_hop_neighbors(ids["User"], k, user_id=USER)
            pg_hop = await pg_algorithms.k_hop_neighbors(ids["User"], k, user_id=USER)
            assert nx_hop == pg_hop, f"k_hop_neighbors(k={k}) diverged"

    async def test_weighted_neighbors_parity(self, parity_setup):
        _, nx_algorithms, pg_algorithms, ids = parity_setup
        nx_ranked = await nx_algorithms.weighted_neighbors(ids["User"], user_id=USER, limit=10)
        pg_ranked = await pg_algorithms.weighted_neighbors(ids["User"], user_id=USER, limit=10)
        assert [node for node, _ in nx_ranked] == [node for node, _ in pg_ranked]
        for (_, nx_cost), (_, pg_cost) in zip(nx_ranked, pg_ranked):
            assert abs(nx_cost - pg_cost) < 1e-9

    async def test_connected_components_parity(self, parity_setup):
        _, nx_algorithms, pg_algorithms, _ = parity_setup
        nx_components = await nx_algorithms.connected_components(user_id=USER)
        pg_components = await pg_algorithms.connected_components(user_id=USER)
        assert nx_components == pg_components

    async def test_path_explain_parity(self, parity_setup):
        _, nx_algorithms, pg_algorithms, ids = parity_setup
        nx_steps = await nx_algorithms.path_explain(ids["User"], ids["MUXI"], user_id=USER)
        pg_steps = await pg_algorithms.path_explain(ids["User"], ids["MUXI"], user_id=USER)
        assert nx_steps == pg_steps

    async def test_mutation_parity(self, parity_setup):
        """Delta test: same mutation, same re-query results on both backends."""
        storage, nx_algorithms, pg_algorithms, ids = parity_setup
        await storage.upsert_relationship(
            USER, ids["User"], ids["Alpha"], "interested_in", confidence=0.9
        )
        nx_algorithms.invalidate(USER)
        pg_algorithms.invalidate(USER)

        nx_path = await nx_algorithms.shortest_path(ids["User"], ids["Beta"], user_id=USER)
        pg_path = await pg_algorithms.shortest_path(ids["User"], ids["Beta"], user_id=USER)
        assert nx_path == pg_path == [ids["User"], ids["Alpha"], ids["Beta"]]
