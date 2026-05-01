"""
Unit tests for ``SOPSystem.find_relevant_sops`` and the cosine-score
path in ``WorkingMemory.search`` for ``namespace="sops"``.

Three layers of coverage:

1. **Signature-binding guard** — ``find_relevant_sops`` calls
   ``WorkingMemory.search`` with specific kwargs. Pin the call shape
   so a future signature drift can't silently re-break SOP routing the
   way the historic ``query_embedding=`` / ``top_k=`` regression did
   (every call raised TypeError, was swallowed by the broad except in
   ``_find_relevant_sop``, and SOP routing was silently dead through
   the semantic path).

2. **Cosine score path** — ``WorkingMemory.search(namespace="sops")``
   must return *true* cosine similarity, not the
   ``1 / (1 + L2²)`` transform used for general-purpose buffer hits.
   The transform compresses the high-similarity range that SOP-routing
   thresholds live in (cos=0.85 maps to score≈0.77 under the old
   formula), so operators reading ``relevance_score >= 0.7`` got
   inconsistent results across queries.

3. **OR-in tag matching** — the merged result of semantic search and
   ``_find_by_tags`` must include any SOP whose tag/name appears in
   the query, even when its semantic score is below threshold.
"""

from __future__ import annotations

import inspect
from typing import List
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from muxi.runtime.formation.workflow.sops import SOPSystem
from muxi.runtime.services.memory.working import WorkingMemory

# ---------------------------------------------------------------------------
# Layer 1 — signature-binding guard
# ---------------------------------------------------------------------------


def test_sops_call_binds_against_workingmemory_search_signature():
    """The kwargs ``find_relevant_sops`` passes to ``WorkingMemory.search``
    must structurally bind against the method's actual signature.

    Regression: the historic call was
    ``working_memory.search(namespace="sops", query_embedding=..., top_k=...)``.
    Neither ``query_embedding`` nor ``top_k`` are parameters of
    ``WorkingMemory.search`` — every invocation raised
    ``TypeError: search() got an unexpected keyword argument
    'query_embedding'``, which the broad except in
    ``_find_relevant_sop`` swallowed. SOP_MATCHED never fired.

    This test pins the kwargs ``find_relevant_sops`` actually uses today,
    so any future drift on either side fails fast at unit time.
    """
    sig = inspect.signature(WorkingMemory.search)

    # Drop ``self`` for a free-call binding check.
    free_params = [p for p in sig.parameters.values() if p.name != "self"]
    free_sig = sig.replace(parameters=free_params)

    # Exactly the kwargs ``find_relevant_sops`` passes today.
    bind = free_sig.bind_partial(
        query="",
        query_vector=[0.1, 0.2, 0.3],
        limit=3,
        recency_bias=0.0,
        namespace="sops",
    )
    bind.apply_defaults()

    # Verify the bound arguments hit the actual parameter names.
    assert "query" in bind.arguments
    assert "query_vector" in bind.arguments
    assert "limit" in bind.arguments
    assert "recency_bias" in bind.arguments
    assert "namespace" in bind.arguments

    # The historic broken kwargs must NOT bind — if they ever bind,
    # someone added them as aliases without updating the SOP path.
    with pytest.raises(TypeError):
        free_sig.bind_partial(
            namespace="sops",
            query_embedding=[0.1],  # legacy broken name
            top_k=3,  # legacy broken name
        )


# ---------------------------------------------------------------------------
# Layer 2 — cosine-score path for namespace="sops"
# ---------------------------------------------------------------------------


def _make_unit_basis_vec(dim: int, axis: int) -> np.ndarray:
    """Return a ``dim``-element unit vector with 1.0 on ``axis``."""
    v = np.zeros(dim, dtype=np.float32)
    v[axis] = 1.0
    return v


@pytest.mark.asyncio
async def test_workingmemory_search_returns_cosine_for_sops_namespace():
    """For ``namespace="sops"`` ``WorkingMemory.search`` must convert
    the FAISS ``IndexFlatL2`` distance to true cosine similarity:

        d == ||a - b||² == 2 - 2·cos(a, b)
        cos == 1 - d / 2

    The general-purpose buffer scoring uses ``1 / (1 + d)`` blended
    with recency, which is wrong for SOP routing thresholds.
    """
    wm = WorkingMemory(formation_id="test-formation")
    # Use the default-sized 768-dim space the FAISS index is built for;
    # the cosine geometry we're testing is dim-agnostic.
    dim = wm.dimension

    # Index a single normalised vector under namespace="sops".
    vec_a = _make_unit_basis_vec(dim, axis=0)
    await wm.add_with_embedding(
        text="Alpha SOP",
        embedding=vec_a.tolist(),
        namespace="sops",
        metadata={"sop_id": "alpha", "name": "Alpha SOP"},
    )

    # Construct a query at known cosine similarity.
    # cos(a, b) = 0.85 → b = 0.85·a + sqrt(1 - 0.85²)·orthogonal
    cos_target = 0.85
    perp = _make_unit_basis_vec(dim, axis=1)
    query = cos_target * vec_a + (1 - cos_target**2) ** 0.5 * perp
    query = query / np.linalg.norm(query)

    results = await wm.search(
        query="",
        query_vector=query.tolist(),
        limit=1,
        recency_bias=0.0,
        namespace="sops",
    )

    assert len(results) == 1, "expected one indexed SOP to come back"
    assert "score" in results[0], (
        "search returned a result without a score — likely fell into the "
        "recency-search fallback because the FAISS index was empty or "
        "dim-mismatched"
    )
    score = results[0]["score"]
    assert score == pytest.approx(cos_target, abs=1e-3), (
        f"expected cosine ≈ {cos_target}, got score={score} (likely the old " "1/(1+L2²) transform)"
    )
    # Round-trip: the SOP id we stored in metadata at index time must
    # come back through search results so callers can map back to the
    # SOP dict.
    assert results[0]["metadata"]["sop_id"] == "alpha"


@pytest.mark.asyncio
async def test_workingmemory_search_keeps_l2_score_for_non_sops_namespace():
    """The cosine override must be SOP-specific. Existing callers
    (e.g. knowledge handler) rely on the ``1 / (1 + L2²)`` blended
    formula and must not see a behaviour change.
    """
    wm = WorkingMemory(formation_id="test-formation")
    dim = wm.dimension

    vec_a = _make_unit_basis_vec(dim, axis=0)
    await wm.add_with_embedding(
        text="document content",
        embedding=vec_a.tolist(),
        namespace="documents",
        metadata={"doc_id": "doc1"},
    )

    # Construct a query at cos=0.85 against the indexed doc — same
    # geometry as the cosine test above. On the non-SOP code path
    # with recency_bias=0.0 the formula reduces to ``1 / (1 + d)``
    # where d == 2 - 2·0.85 == 0.30 → score == 1/1.30 ≈ 0.769.
    cos_target = 0.85
    perp = _make_unit_basis_vec(dim, axis=1)
    query = cos_target * vec_a + (1 - cos_target**2) ** 0.5 * perp
    query = query / np.linalg.norm(query)

    results = await wm.search(
        query="",
        query_vector=query.tolist(),
        limit=1,
        recency_bias=0.0,
        namespace="documents",
    )

    assert len(results) == 1
    expected_legacy_score = 1.0 / (1.0 + (2.0 - 2.0 * cos_target))
    assert results[0]["score"] == pytest.approx(expected_legacy_score, abs=1e-3), (
        "non-SOP namespaces must keep the legacy 1/(1+L2²) score formula; "
        "the cosine override must not leak across namespaces"
    )


# ---------------------------------------------------------------------------
# Layer 3 — OR-in tag matching alongside semantic
# ---------------------------------------------------------------------------


def _make_sop_system_with_sops(sops: dict) -> SOPSystem:
    """Build a stub ``SOPSystem`` populated with the given SOPs.

    Bypasses the file-loader entirely — we want to drive
    ``find_relevant_sops`` against a known in-memory dict so the
    merge logic is testable without touching disk.
    """
    sys_ = SOPSystem.__new__(SOPSystem)
    sys_.enabled = True
    sys_.sops = sops
    sys_.embeddings_cache = {}
    sys_.file_hashes = {}
    sys_._working_memory_ref = None
    sys_._embedding_model_ref = None
    return sys_


@pytest.mark.asyncio
async def test_find_relevant_sops_or_in_tag_match_when_semantic_misses():
    """When the semantic path returns nothing (or only weak matches),
    a tag/name match must still fire so explicit-vocabulary requests
    route correctly.

    Setup: SOP "guestbook" with tag "guestbook"; query "sign the muxi
    guestbook". Semantic path is mocked to return no matches; tag path
    must produce a result with score >= 1 that clears the routing
    threshold.
    """
    sops = {
        "guestbook": {
            "id": "guestbook",
            "name": "Sign Muxi Guestbook",
            "tags": ["guestbook", "intro"],
            "mode": "template",
        },
    }
    sys_ = _make_sop_system_with_sops(sops)

    # Force the semantic path to be inactive (no working_memory).
    sys_._get_working_memory = lambda: None
    sys_._get_embedding_model = lambda: None

    # ``_ensure_indexed`` is async — make it a no-op.
    sys_._ensure_indexed = AsyncMock(return_value=None)

    results = await sys_.find_relevant_sops("sign the muxi guestbook", top_k=3)

    assert len(results) == 1
    assert results[0]["id"] == "guestbook"
    # Tag-based scores are integer >= 1 (well above any 0.7 threshold).
    assert results[0]["relevance_score"] >= 1


@pytest.mark.asyncio
async def test_find_relevant_sops_merges_semantic_and_tag_hits():
    """When BOTH paths fire on overlapping SOP ids, the merged result
    keeps the higher score per id (tag/name match wins over semantic
    on the same SOP — explicit signal beats fuzzy similarity).

    When they fire on DIFFERENT SOP ids, both end up in the result.
    """
    sops = {
        "guestbook": {
            "id": "guestbook",
            "name": "Sign Muxi Guestbook",
            "tags": ["guestbook"],
            "mode": "template",
        },
        "onboarding": {
            "id": "onboarding",
            "name": "Onboarding",
            "tags": ["intro"],
            "mode": "template",
        },
    }
    sys_ = _make_sop_system_with_sops(sops)

    # Mock working memory + embedding model so the semantic path runs.
    fake_wm = MagicMock()
    fake_wm.search = AsyncMock(
        return_value=[
            # Semantic hits "onboarding" with cosine 0.78 (above threshold)
            # and "guestbook" with a weaker cosine 0.55 (below threshold,
            # but still returned by working_memory.search — the threshold
            # filtering happens in _find_relevant_sop). ``sop_id`` lives
            # in metadata because WorkingMemory has no native id field.
            {
                "score": 0.78,
                "metadata": {"sop_id": "onboarding"},
                "text": "Onboarding",
            },
            {
                "score": 0.55,
                "metadata": {"sop_id": "guestbook"},
                "text": "Sign Muxi Guestbook",
            },
        ]
    )
    sys_._get_working_memory = lambda: fake_wm

    fake_model = MagicMock()
    fake_model.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    sys_._get_embedding_model = lambda: fake_model

    sys_._ensure_indexed = AsyncMock(return_value=None)

    results = await sys_.find_relevant_sops(
        # ``guestbook`` literally appears in the query → tag path scores 1+
        "sign the muxi guestbook",
        top_k=5,
    )

    by_id = {r["id"]: r for r in results}
    assert "guestbook" in by_id
    assert "onboarding" in by_id

    # ``guestbook`` appears in BOTH paths — merged score must be the
    # higher of (tag score >= 1) vs (semantic 0.55) → wins.
    assert (
        by_id["guestbook"]["relevance_score"] >= 1
    ), "tag-match score must beat the weak semantic score for the same SOP"

    # ``onboarding`` matched only via semantic — score preserved.
    assert by_id["onboarding"]["relevance_score"] == pytest.approx(0.78)

    # Ordering: highest first. ``guestbook`` (>= 1) must rank ABOVE
    # ``onboarding`` (0.78).
    assert results[0]["id"] == "guestbook"


@pytest.mark.asyncio
async def test_find_relevant_sops_returns_empty_when_neither_path_fires():
    """If semantic returns nothing AND no tag/name matches the query,
    the merged result must be empty — the caller (``_find_relevant_sop``)
    interprets that as "no SOP applies" and routes through the normal
    intent path. Returning a stale or default SOP would be a routing
    bug.
    """
    sops = {
        "guestbook": {
            "id": "guestbook",
            "name": "Sign Muxi Guestbook",
            "tags": ["guestbook"],
            "mode": "template",
        },
    }
    sys_ = _make_sop_system_with_sops(sops)

    fake_wm = MagicMock()
    fake_wm.search = AsyncMock(return_value=[])  # semantic miss
    sys_._get_working_memory = lambda: fake_wm

    fake_model = MagicMock()
    fake_model.generate_embeddings = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    sys_._get_embedding_model = lambda: fake_model

    sys_._ensure_indexed = AsyncMock(return_value=None)

    results: List[dict] = await sys_.find_relevant_sops(
        "completely unrelated request about astrophysics",
        top_k=3,
    )
    assert results == []
