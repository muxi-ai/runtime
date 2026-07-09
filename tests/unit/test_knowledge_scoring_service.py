"""Unit tests for the ScoringService (reasoning-RAG Phase 2).

The ScoringService is a cross-PRD contract (knowledge-reasoning-rag +
memory-revamp Layer 3): ``embed`` / ``score`` /
``aggregate_with_diminishing_returns``. These tests pin:

  * The aggregation formula ``(1/sqrt(N+1)) * sum`` exactly (PageIndex
    reference), including the edge cases: empty input, single chunk,
    negative similarities, and the diminishing-returns property itself
    (few strong chunks beat many weak ones).
  * Cosine scoring correctness and zero-norm safety.
  * Both embedder backends: model slug (routed through the UEL) and an
    injected callable, sync or async.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from muxi.runtime.formation.agents.knowledge.reasoning import ScoringService


async def _identity_embedder(texts):
    """Deterministic embedder: vector = [len(text), 1.0]."""
    return [[float(len(t)), 1.0] for t in texts]


def make_service() -> ScoringService:
    return ScoringService(_identity_embedder)


# ---------------------------------------------------------------------------
# aggregate_with_diminishing_returns - the PageIndex formula
# ---------------------------------------------------------------------------


class TestAggregation:
    def test_empty_scores_aggregate_to_zero(self):
        assert ScoringService.aggregate_with_diminishing_returns([]) == 0.0

    def test_single_chunk(self):
        # N=1 -> score / sqrt(2)
        result = ScoringService.aggregate_with_diminishing_returns([0.8])
        assert result == pytest.approx(0.8 / math.sqrt(2))

    @pytest.mark.parametrize("n", [1, 2, 5, 50, 200])
    def test_matches_reference_formula(self, n):
        scores = [0.5 + 0.001 * i for i in range(n)]
        expected = sum(scores) / math.sqrt(n + 1)
        result = ScoringService.aggregate_with_diminishing_returns(scores)
        assert result == pytest.approx(expected, rel=1e-9)

    def test_diminishing_returns_property(self):
        """A node with 3 strong chunks must beat a node with 50 weak ones.

        This is Method B's core value-add over flat similarity search:
        without the 1/sqrt(N+1) denominator the 50-chunk node would win
        on raw sum (5.0 vs 2.7).
        """
        few_strong = ScoringService.aggregate_with_diminishing_returns([0.9, 0.9, 0.9])
        many_weak = ScoringService.aggregate_with_diminishing_returns([0.1] * 50)
        assert sum([0.1] * 50) > sum([0.9] * 3), "sanity: raw sum favors the weak node"
        assert few_strong > many_weak, "aggregation must favor the strong node"

    def test_more_relevant_chunks_still_rewarded(self):
        """Diminishing, not capped: extra relevant chunks still add value."""
        one = ScoringService.aggregate_with_diminishing_returns([0.9])
        three = ScoringService.aggregate_with_diminishing_returns([0.9, 0.9, 0.9])
        assert three > one

    def test_negative_similarities_drag_the_aggregate_down(self):
        mixed = ScoringService.aggregate_with_diminishing_returns([0.9, -0.9])
        positive = ScoringService.aggregate_with_diminishing_returns([0.9])
        assert mixed < positive
        assert mixed == pytest.approx(0.0, abs=1e-9)

    def test_all_zero_scores(self):
        assert ScoringService.aggregate_with_diminishing_returns([0.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# score - cosine similarity
# ---------------------------------------------------------------------------


class TestScore:
    def test_identical_vector_scores_one(self):
        service = make_service()
        scores = asyncio.run(service.score([1.0, 2.0, 3.0], [[1.0, 2.0, 3.0]]))
        assert scores[0] == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vector_scores_zero(self):
        service = make_service()
        scores = asyncio.run(service.score([1.0, 0.0], [[0.0, 1.0]]))
        assert scores[0] == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vector_scores_minus_one(self):
        service = make_service()
        scores = asyncio.run(service.score([1.0, 0.0], [[-1.0, 0.0]]))
        assert scores[0] == pytest.approx(-1.0, abs=1e-6)

    def test_magnitude_invariance(self):
        service = make_service()
        scores = asyncio.run(service.score([1.0, 1.0], [[10.0, 10.0], [0.1, 0.1]]))
        assert scores[0] == pytest.approx(scores[1], abs=1e-6)

    def test_empty_chunk_list_returns_empty(self):
        service = make_service()
        assert asyncio.run(service.score([1.0, 0.0], [])) == []

    def test_zero_norm_chunk_scores_zero(self):
        service = make_service()
        scores = asyncio.run(service.score([1.0, 0.0], [[0.0, 0.0], [1.0, 0.0]]))
        assert scores[0] == 0.0
        assert scores[1] == pytest.approx(1.0, abs=1e-6)

    def test_zero_norm_query_scores_all_zero(self):
        service = make_service()
        scores = asyncio.run(service.score([0.0, 0.0], [[1.0, 0.0], [0.0, 1.0]]))
        assert scores == [0.0, 0.0]

    def test_preserves_chunk_order(self):
        service = make_service()
        scores = asyncio.run(service.score([1.0, 0.0], [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]))
        assert scores[0] > scores[2] > scores[1]


# ---------------------------------------------------------------------------
# embed - backend contract
# ---------------------------------------------------------------------------


class TestEmbed:
    def test_single_string_returns_single_vector(self):
        service = make_service()
        vec = asyncio.run(service.embed("hello"))
        assert vec == [5.0, 1.0]

    def test_list_returns_list_of_vectors(self):
        service = make_service()
        vecs = asyncio.run(service.embed(["a", "abc"]))
        assert vecs == [[1.0, 1.0], [3.0, 1.0]]

    def test_sync_callable_embedder_supported(self):
        service = ScoringService(lambda texts: [[1.0] for _ in texts])
        assert asyncio.run(service.embed("x")) == [1.0]

    @pytest.mark.parametrize("bad", ["", "   ", [], ["", "  "]])
    def test_empty_input_raises(self, bad):
        service = make_service()
        with pytest.raises(ValueError):
            asyncio.run(service.embed(bad))

    def test_invalid_embedder_type_raises(self):
        with pytest.raises(TypeError):
            ScoringService(42)

    def test_empty_slug_raises(self):
        with pytest.raises(ValueError):
            ScoringService("   ")

    def test_slug_backend_exposes_model_slug(self):
        service = ScoringService("openai/text-embedding-3-small")
        assert service.model_slug == "openai/text-embedding-3-small"

    def test_callable_backend_has_empty_slug(self):
        assert make_service().model_slug == ""
