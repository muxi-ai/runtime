# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Scoring Service - Query/Chunk Similarity with Structural
#               Aggregation
# Description:  Shared embedding + similarity scoring service for value-based
#               retrieval (reasoning-RAG Method B) and future hybrid search
# Role:         Standalone, memory-agnostic scoring primitive
# Usage:        Consumed by tree_search_b / tree_search_hybrid today;
#               memory-revamp Layer 3 (hybrid search) consumes the same
#               interface when that PRD lands
# Author:       Muxi Framework Team
#
# CROSS-PRD CONTRACT (knowledge-reasoning-rag.md + memory-revamp.md)
# ------------------------------------------------------------------
# This service is deliberately standalone: it knows nothing about trees,
# memory tiers, or knowledge sources. Its full public surface is:
#
#   service = ScoringService(embedder)          # slug or async callable
#   vec     = await service.embed("query")      # str -> EmbeddingVec
#   vecs    = await service.embed(["a", "b"])   # list -> list[EmbeddingVec]
#   scores  = await service.score(query_vec, chunk_vecs)   # cosine, [-1, 1]
#   value   = service.aggregate_with_diminishing_returns(scores)
#
# where ``EmbeddingVec = list[float]`` and the aggregation implements the
# PageIndex production formula:
#
#   NodeScore = (1 / sqrt(N + 1)) * sum(ChunkScore)     N = len(scores)
#
# The 1/sqrt(N+1) denominator rewards groups with multiple relevant chunks
# while applying diminishing returns, so a 200-chunk group cannot dominate
# a 5-chunk group that is actually more relevant. ``aggregate`` of an empty
# score list is 0.0 by definition (no evidence, no value).
#
# Consumers group chunks however they like (tree nodes here; memory areas
# in memory-revamp Layer 3) - grouping semantics stay OUT of this service.
#
# Embedding backend
# -----------------
# ``embedder`` is either:
#   * a provider-prefixed model slug (str) - calls flow through the unified
#     embedding layer (``services.memory.embedding.embed``), or
#   * an async callable ``(list[str]) -> list[list[float]]`` - e.g. the
#     KnowledgeHandler's ``generate_embeddings_fn`` - so callers can inject
#     whatever embedding path they already hold.
# Either way, embeddings survive future model swaps via the UEL contract
# (embedding-platform.md).
# =============================================================================

import inspect
import math
from typing import Any, Callable, List, Union

import numpy as np

# Type aliases for the public contract.
EmbeddingVec = List[float]


class ScoringService:
    """
    Query/chunk similarity scoring with diminishing-returns aggregation.

    Args:
        embedder: Provider-prefixed embedding model slug (str), or an async
            callable ``(list[str]) -> list[list[float]]``.
    """

    def __init__(self, embedder: Union[str, Callable[..., Any]]):
        if isinstance(embedder, str):
            if not embedder.strip():
                raise ValueError("ScoringService embedder slug cannot be empty")
            self._model_slug: str = embedder.strip()
            self._embed_fn = None
        elif callable(embedder):
            self._model_slug = ""
            self._embed_fn = embedder
        else:
            raise TypeError(
                "ScoringService embedder must be a model slug (str) or an async "
                f"callable, got {type(embedder).__name__}"
            )

    @property
    def model_slug(self) -> str:
        """The embedding model slug, or "" when using an injected callable."""
        return self._model_slug

    async def embed(self, text: Union[str, List[str]]) -> Union[EmbeddingVec, List[EmbeddingVec]]:
        """
        Embed ``text`` and return one vector (str input) or a list (list input).

        Raises:
            ValueError: On empty input (mirrors the UEL's empty-input policy).
        """
        single = isinstance(text, str)
        items = [text] if single else list(text)
        if not items or all(not isinstance(t, str) or not t.strip() for t in items):
            raise ValueError("ScoringService.embed input cannot be empty")

        if self._embed_fn is not None:
            result = self._embed_fn(items)
            vectors = await result if inspect.isawaitable(result) else result
        else:
            from .....services.memory.embedding import embed as uel_embed

            vectors = await uel_embed(self._model_slug, items)

        vectors = [list(map(float, v)) for v in vectors]
        return vectors[0] if single else vectors

    async def score(self, query_vec: EmbeddingVec, chunk_vecs: List[EmbeddingVec]) -> List[float]:
        """
        Cosine similarity of ``query_vec`` against each vector in ``chunk_vecs``.

        Returns one float per chunk vector, in order, in ``[-1.0, 1.0]``.
        Zero-norm vectors score 0.0 (no direction, no similarity). The
        method is async for interface stability (future backends may score
        remotely); the numpy implementation never awaits.
        """
        if not chunk_vecs:
            return []
        query = np.asarray(query_vec, dtype=np.float32)
        chunks = np.asarray(chunk_vecs, dtype=np.float32)
        query_norm = float(np.linalg.norm(query))
        chunk_norms = np.linalg.norm(chunks, axis=1)
        if query_norm == 0.0:
            return [0.0] * len(chunk_vecs)
        denom = chunk_norms * query_norm
        # Zero-norm chunks: avoid divide-by-zero, score 0.0.
        safe_denom = np.where(denom == 0.0, 1.0, denom)
        sims = (chunks @ query) / safe_denom
        sims = np.where(denom == 0.0, 0.0, sims)
        return [float(s) for s in sims]

    @staticmethod
    def aggregate_with_diminishing_returns(scores: List[float]) -> float:
        """
        Aggregate chunk scores into one group score: ``(1/sqrt(N+1)) * sum``.

        The PageIndex production formula. Empty input aggregates to 0.0
        (no evidence). Negative similarities are kept as-is - anti-relevant
        chunks legitimately drag a group down.
        """
        if not scores:
            return 0.0
        return float(sum(scores) / math.sqrt(len(scores) + 1))
