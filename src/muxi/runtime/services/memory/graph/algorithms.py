# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Graph Algorithms - Backend-Specific Traversal Layer
# Description:  Shared protocol with pgRouting and NetworkX implementations
# Role:         Multi-hop exploration, pathfinding, and clustering over the KG
# Usage:        Selected per backend by KnowledgeGraphService
# Author:       Muxi Framework Team
#
# Storage of entities and relationships is plain SQL (see storage.py). Graph
# algorithms are delegated to a backend-specific layer behind the shared
# GraphAlgorithms protocol (Memory Revamp Phase 1):
#
# - PgRoutingAlgorithms (PostgreSQL): issues pgRouting SQL (pgr_dijkstra,
#   pgr_drivingDistance, pgr_connectedComponents) against a canonical
#   edge-source query. No in-memory cache; algorithms run in C inside the
#   database. invalidate() is a no-op.
# - NetworkXAlgorithms (SQLite / fallback): per-user LRU cache of DiGraph
#   objects hydrated from storage.iter_edges(). invalidate(user_id) drops
#   the cached graph; the service calls it after every graph write.
#
# Both implementations return identical shapes and are pinned together by a
# fixture-driven parity test suite (tests/unit/test_knowledge_graph_parity.py;
# the pgRouting side runs when a pgRouting-enabled DSN is provided).
#
# Edge cost is (1.0 - confidence): strong edges are short distances, so
# cumulative path cost ranks entities by aggregate relatedness.
# =============================================================================

from collections import OrderedDict
from typing import Dict, List, Optional, Protocol, Set, Tuple

import networkx as nx
from sqlalchemy import text

from .storage import KnowledgeGraphStorage, normalize_type


class GraphAlgorithms(Protocol):
    """Backend-agnostic algorithm surface over a user's knowledge graph."""

    async def shortest_path(
        self,
        start: int,
        end: int,
        *,
        user_id: str,
        rel_types: Optional[List[str]] = None,
    ) -> List[int]:
        """Return the confidence-weighted node path from start to end."""
        ...

    async def k_hop_neighbors(
        self,
        start: int,
        k: int,
        *,
        user_id: str,
        rel_types: Optional[List[str]] = None,
    ) -> List[int]:
        """Return entity ids reachable within k hops of start."""
        ...

    async def weighted_neighbors(
        self,
        start: int,
        *,
        user_id: str,
        limit: int = 10,
        rel_types: Optional[List[str]] = None,
    ) -> List[Tuple[int, float]]:
        """Return (entity_id, cumulative_cost) ranked by aggregate proximity."""
        ...

    async def connected_components(self, *, user_id: str) -> List[Set[int]]:
        """Return clusters of related entities."""
        ...

    async def path_explain(
        self,
        start: int,
        end: int,
        *,
        user_id: str,
    ) -> List[Tuple[int, Optional[int]]]:
        """Return (node_id, edge_id) steps along the start-to-end path.

        The final step's edge_id is None (arrival node).
        """
        ...

    def invalidate(self, user_id: str) -> None:
        """Drop any cached graph state for a user (no-op on pgRouting)."""
        ...


class NetworkXAlgorithms:
    """In-memory graph algorithms for the SQLite backend (and fallback).

    Maintains a per-user LRU cache of ``nx.DiGraph`` objects. On embedded
    single-user deployments the cache never holds more than one graph;
    re-hydration after invalidation is sub-100ms at personal-assistant scale.
    """

    def __init__(self, storage: KnowledgeGraphStorage, cache_size: int = 8):
        self._storage = storage
        self._cache_size = max(1, cache_size)
        self._cache: "OrderedDict[str, nx.DiGraph]" = OrderedDict()

    async def _get_graph(self, user_id: str) -> nx.DiGraph:
        user_id = str(user_id)
        if user_id in self._cache:
            self._cache.move_to_end(user_id)
            return self._cache[user_id]

        graph = nx.DiGraph()
        for edge in await self._storage.iter_edges(user_id):
            graph.add_edge(
                edge["from_entity_id"],
                edge["to_entity_id"],
                weight=1.0 - (edge["confidence"] or 0.0),
                rel_type=edge["type"],
                rel_id=edge["id"],
            )
        self._cache[user_id] = graph
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return graph

    @staticmethod
    def _filtered(graph: nx.DiGraph, rel_types: Optional[List[str]]) -> nx.DiGraph:
        if not rel_types:
            return graph
        wanted = {normalize_type(t) for t in rel_types}
        return graph.edge_subgraph(
            (u, v) for u, v, d in graph.edges(data=True) if d["rel_type"] in wanted
        )

    async def shortest_path(
        self,
        start: int,
        end: int,
        *,
        user_id: str,
        rel_types: Optional[List[str]] = None,
    ) -> List[int]:
        graph = self._filtered(await self._get_graph(user_id), rel_types)
        undirected = graph.to_undirected(as_view=False)
        if start not in undirected or end not in undirected:
            return []
        try:
            return list(nx.shortest_path(undirected, start, end, weight="weight"))
        except nx.NetworkXNoPath:
            return []

    async def k_hop_neighbors(
        self,
        start: int,
        k: int,
        *,
        user_id: str,
        rel_types: Optional[List[str]] = None,
    ) -> List[int]:
        graph = self._filtered(await self._get_graph(user_id), rel_types)
        undirected = graph.to_undirected(as_view=False)
        if start not in undirected:
            return []
        lengths = nx.single_source_shortest_path_length(undirected, start, cutoff=k)
        return sorted(node for node in lengths if node != start)

    async def weighted_neighbors(
        self,
        start: int,
        *,
        user_id: str,
        limit: int = 10,
        rel_types: Optional[List[str]] = None,
    ) -> List[Tuple[int, float]]:
        graph = self._filtered(await self._get_graph(user_id), rel_types)
        undirected = graph.to_undirected(as_view=False)
        if start not in undirected:
            return []
        distances = nx.single_source_dijkstra_path_length(undirected, start, weight="weight")
        ranked = sorted(
            ((node, cost) for node, cost in distances.items() if node != start),
            key=lambda item: (item[1], item[0]),
        )
        return ranked[:limit]

    async def connected_components(self, *, user_id: str) -> List[Set[int]]:
        graph = await self._get_graph(user_id)
        components = [set(component) for component in nx.weakly_connected_components(graph)]
        return sorted(components, key=lambda component: (-len(component), min(component)))

    async def path_explain(
        self,
        start: int,
        end: int,
        *,
        user_id: str,
    ) -> List[Tuple[int, Optional[int]]]:
        graph = await self._get_graph(user_id)
        undirected = graph.to_undirected(as_view=False)
        node_path = await self.shortest_path(start, end, user_id=user_id)
        if not node_path:
            return []
        steps: List[Tuple[int, Optional[int]]] = []
        for index, node in enumerate(node_path):
            if index < len(node_path) - 1:
                edge_data = undirected.get_edge_data(node, node_path[index + 1]) or {}
                steps.append((node, edge_data.get("rel_id")))
            else:
                steps.append((node, None))
        return steps

    def invalidate(self, user_id: str) -> None:
        self._cache.pop(str(user_id), None)


class PgRoutingAlgorithms:
    """pgRouting-backed graph algorithms for the PostgreSQL backend.

    Every method passes a canonical edge-source SQL string (user-scoped,
    active edges only, cost = 1 - confidence) to the corresponding pgRouting
    function. There is no cache to invalidate; algorithms run inside the
    database.
    """

    def __init__(self, db_manager, formation_id: str):
        self.db_manager = db_manager
        self.formation_id = formation_id

    def _edge_source_sql(
        self,
        user_id: str,
        rel_types: Optional[List[str]] = None,
        uniform_cost: bool = False,
    ) -> str:
        """Build the canonical user-scoped edge-source query.

        pgRouting executes this SQL internally, so scope values are inlined
        as quoted literals (bind parameters cannot cross that boundary).
        This builder is the single place edge-source SQL is written; all
        user-scoping is enforced here.
        """
        cost = "1.0" if uniform_cost else "(1.0 - COALESCE(r.confidence, 0.0))"
        sql = (
            "SELECT r.id AS id, r.from_entity_id AS source, r.to_entity_id AS target, "
            f"{cost} AS cost "
            "FROM kg_relationships r "
            f"WHERE r.user_id = {_quote_literal(str(user_id))} "
            f"AND r.formation_id = {_quote_literal(self.formation_id)} "
            "AND r.status = 'active'"
        )
        if rel_types:
            normalized = sorted({normalize_type(t) for t in rel_types})
            quoted = ", ".join(_quote_literal(t) for t in normalized)
            sql += f" AND r.type IN ({quoted})"
        return sql

    async def shortest_path(
        self,
        start: int,
        end: int,
        *,
        user_id: str,
        rel_types: Optional[List[str]] = None,
    ) -> List[int]:
        edges = self._edge_source_sql(user_id, rel_types)
        query = text(
            "SELECT d.node FROM pgr_dijkstra(:edges, :start, :end, directed := false) d "
            "ORDER BY d.path_seq"
        )
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(
                query, {"edges": edges, "start": int(start), "end": int(end)}
            )
            return [int(row[0]) for row in result.fetchall()]

    async def k_hop_neighbors(
        self,
        start: int,
        k: int,
        *,
        user_id: str,
        rel_types: Optional[List[str]] = None,
    ) -> List[int]:
        # Uniform edge cost turns pgr_drivingDistance's distance bound into
        # a hop bound, matching NetworkX's cutoff-k BFS exactly.
        edges = self._edge_source_sql(user_id, rel_types, uniform_cost=True)
        query = text(
            "SELECT d.node FROM pgr_drivingDistance(:edges, :start, :distance, "
            "directed := false) d WHERE d.node <> :start ORDER BY d.node"
        )
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(
                query, {"edges": edges, "start": int(start), "distance": float(k)}
            )
            return [int(row[0]) for row in result.fetchall()]

    async def weighted_neighbors(
        self,
        start: int,
        *,
        user_id: str,
        limit: int = 10,
        rel_types: Optional[List[str]] = None,
    ) -> List[Tuple[int, float]]:
        edges = self._edge_source_sql(user_id, rel_types)
        targets = (
            "SELECT array_agg(e.id) FROM kg_entities e "
            f"WHERE e.user_id = {_quote_literal(str(user_id))} "
            f"AND e.formation_id = {_quote_literal(self.formation_id)} "
            "AND e.status = 'active'"
        )
        query = text(
            "SELECT d.end_vid, MIN(d.agg_cost) AS cost "
            f"FROM pgr_dijkstra(:edges, :start, ({targets}), directed := false) d "
            "WHERE d.edge = -1 AND d.end_vid <> :start "
            "GROUP BY d.end_vid ORDER BY cost ASC, d.end_vid ASC LIMIT :limit"
        )
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(
                query, {"edges": edges, "start": int(start), "limit": int(limit)}
            )
            return [(int(row[0]), float(row[1])) for row in result.fetchall()]

    async def connected_components(self, *, user_id: str) -> List[Set[int]]:
        edges = self._edge_source_sql(user_id)
        query = text(
            "SELECT c.component, c.node FROM pgr_connectedComponents(:edges) c "
            "ORDER BY c.component, c.node"
        )
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(query, {"edges": edges})
            grouped: Dict[int, Set[int]] = {}
            for component, node in result.fetchall():
                grouped.setdefault(int(component), set()).add(int(node))
            components = list(grouped.values())
            return sorted(components, key=lambda component: (-len(component), min(component)))

    async def path_explain(
        self,
        start: int,
        end: int,
        *,
        user_id: str,
    ) -> List[Tuple[int, Optional[int]]]:
        edges = self._edge_source_sql(user_id)
        query = text(
            "SELECT d.node, d.edge FROM pgr_dijkstra(:edges, :start, :end, "
            "directed := false) d ORDER BY d.path_seq"
        )
        async with self.db_manager.get_async_session() as session:
            result = await session.execute(
                query, {"edges": edges, "start": int(start), "end": int(end)}
            )
            steps: List[Tuple[int, Optional[int]]] = []
            for node, edge in result.fetchall():
                steps.append((int(node), None if edge == -1 else int(edge)))
            return steps

    def invalidate(self, user_id: str) -> None:
        """No-op: pgRouting queries the live tables on every call."""


def _quote_literal(value: str) -> str:
    """Quote a string as a safe SQL literal for inlined edge-source queries."""
    return "'" + value.replace("'", "''") + "'"
