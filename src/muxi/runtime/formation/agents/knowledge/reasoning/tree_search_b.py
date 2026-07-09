# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tree Search Method B - Value-Based Node Scoring
# Description:  Query-time retrieval over a document tree via per-node chunk
#               embedding scores (no LLM calls at query time)
# Role:         Retrieval-side component of reasoning-based RAG (Method B)
# Usage:        Invoked by KnowledgeHandler.search for ``retrieval: tree-vector``
#               sources; also used by the hybrid runner (tree_search_hybrid)
# Author:       Muxi Framework Team
#
# At tree build time, each node's raw content is split into small chunks and
# embedded through the ScoringService (unified embedding layer). At query
# time the query is embedded once, every chunk is cosine-scored against it,
# and node-level scores aggregate with diminishing returns:
#
#   NodeScore(n) = (1 / sqrt(N(n) + 1)) * sum(ChunkScore(c))  c in chunks(n)
#
# You retrieve NODES, not chunks - the chunks are scoring scaffolding only.
# The structural aggregation is Method B's value-add over flat vector
# search: a node with 3 highly-relevant chunks beats a node with 50 weakly
# relevant ones.
#
# Failure isolation: any embedding/scoring failure raises
# ``TreeNavigationError``; the caller falls back to vector search results.
# =============================================================================

import re
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from .....services import observability
from .scoring_service import ScoringService
from .types import RetrievalResult, TreeIndex, TreeNavigationError

# Cap on raw content characters returned per selected node (same guard as
# Method A - a selected parent node cannot flood the context).
_MAX_NODE_CONTENT_CHARS = 6000

# Fallback chunker window (chars). PRD Method B calls for small chunks
# (~500-1000 chars) for embedding quality.
_CHUNK_CHARS = 800

# Nodes must clear this aggregated score to be returned. Cosine scores of
# unrelated text hover around 0; a small positive floor keeps clearly
# unrelated documents from contributing noise nodes.
_MIN_NODE_SCORE = 0.05

# Type of the optional injected chunker: text -> list of chunk strings.
Chunker = Callable[[str], Awaitable[List[str]]]


def split_text_for_scoring(text: str, window_chars: int = _CHUNK_CHARS) -> List[str]:
    """
    Deterministic paragraph-boundary chunker used when no chunker is injected.

    Splits on blank lines, then re-packs paragraphs into windows of at most
    ``window_chars``; paragraphs longer than a window are hard-split. Never
    returns empty chunks.
    """
    if not text or not text.strip():
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > window_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:window_chars])
            para = para[window_chars:].strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > window_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


async def build_node_chunk_embeddings(
    tree: TreeIndex,
    scoring_service: ScoringService,
    chunker: Optional[Chunker] = None,
) -> int:
    """
    Compute per-node chunk embeddings for every node with raw content.

    Fills ``tree.chunk_embeddings`` (node_id -> list of chunk vectors) and
    ``tree.embedding_model`` in place. Chunk texts are scaffolding only and
    are not retained. Returns the total number of chunks embedded.

    Args:
        tree: The tree index to embed (kv must be populated).
        scoring_service: Embedding + scoring backend.
        chunker: Optional async chunker (e.g. wrapping DocumentChunkManager).
            Falls back to :func:`split_text_for_scoring` when absent or when
            it fails for a node.

    Raises:
        Exception: Propagates embedding failures (the caller decides the
            fallback policy - at ingestion this means Method B is skipped
            and the tree serves Method A only).
    """
    # Collect (node_id, chunks) pairs first so all texts embed in one
    # batched pass per node (bounded: nodes are capped at
    # max_tokens_per_node by the builder).
    node_chunks: List[Tuple[str, List[str]]] = []
    for node in tree.walk():
        raw = tree.fetch_raw(node.node_id)
        if not raw or not raw.strip():
            continue
        chunks: List[str] = []
        if chunker is not None:
            try:
                chunks = [c for c in await chunker(raw) if c and c.strip()]
            except Exception:
                chunks = []
        if not chunks:
            chunks = split_text_for_scoring(raw)
        if chunks:
            node_chunks.append((node.node_id, chunks))

    total = 0
    embeddings = {}
    for node_id, chunks in node_chunks:
        vectors = await scoring_service.embed(chunks)
        embeddings[node_id] = vectors
        total += len(vectors)

    tree.chunk_embeddings = embeddings
    tree.embedding_model = scoring_service.model_slug or tree.embedding_model
    return total


class TreeSearchB:
    """
    Method B retriever: per-node chunk-embedding scoring, no LLM calls.

    Args:
        scoring_service: The shared :class:`ScoringService` used to embed
            the query and score it against per-node chunk vectors.
    """

    def __init__(self, scoring_service: ScoringService):
        self.scoring = scoring_service

    async def search(
        self, query: str, tree: TreeIndex, max_nodes: int = 3
    ) -> List[RetrievalResult]:
        """
        Score every node of ``tree`` against ``query``; return the top nodes.

        Raises:
            TreeNavigationError: On embedding failure or when the tree has
                no chunk embeddings to score against.
        """
        max_nodes = max(1, int(max_nodes))
        if not tree.chunk_embeddings:
            raise TreeNavigationError(
                f"Tree for '{tree.document}' has no chunk embeddings (Method B "
                "requires per-node embeddings built at ingestion)"
            )
        try:
            query_vec = await self.scoring.embed(query)
        except Exception as e:
            raise TreeNavigationError(f"Query embedding failed for '{tree.document}': {e}") from e

        scored: List[Tuple[float, Any]] = []
        for node in tree.walk():
            chunk_vecs = tree.chunk_embeddings.get(node.node_id)
            if not chunk_vecs:
                continue
            chunk_scores = await self.scoring.score(query_vec, chunk_vecs)
            node_score = self.scoring.aggregate_with_diminishing_returns(chunk_scores)
            if node_score > _MIN_NODE_SCORE:
                scored.append((node_score, node))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        selected = scored[:max_nodes]

        if selected:
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_TREE_NODE_SELECTED,
                level=observability.EventLevel.DEBUG,
                description="Method B value scoring selected nodes",
                data={
                    "document": tree.document,
                    "method": "b",
                    "node_ids": [node.node_id for _, node in selected],
                    "node_scores": [round(score, 4) for score, _ in selected],
                    "scored_nodes": len(scored),
                },
            )

        results: List[RetrievalResult] = []
        source_type = "agent_tree" if tree.scope == "agent" else "tree"
        for node_score, node in selected:
            content = tree.resolve_content(node.node_id, _MAX_NODE_CONTENT_CHARS)
            if not content:
                continue
            results.append(
                RetrievalResult(
                    source_type=source_type,
                    content=content,
                    # Aggregated node scores are unbounded above 1.0 in
                    # theory (many strong chunks); clamp for the unified
                    # relevance contract and keep the raw score in metadata.
                    relevance=max(0.0, min(1.0, node_score)),
                    metadata={
                        "document": tree.document,
                        "node_id": node.node_id,
                        "node_title": node.title,
                        "node_score": round(node_score, 6),
                        "retrieval_method": "tree_b",
                    },
                    node_path=tree.node_path(node.node_id),
                )
            )
        return results
