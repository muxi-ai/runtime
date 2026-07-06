"""Unit tests for per-session FAISS partitioning in ``WorkingMemory``.

``WorkingMemory`` used to hold one ``IndexFlatL2`` for the whole
formation and scope results with post-search Python filters. That made
every search scan every session's vectors and — worse — let a busy
session crowd another session's relevant items out of the global top-k
(recall dilution). Vectors are now partitioned: "buffer"-namespace items
carrying a session_id get a per-session index, everything else (sops,
knowledge, docs, sessionless buffer items) shares ``SHARED_PARTITION``.

These tests pin the partition-routing rules, the recall-dilution fix,
namespaced (sops) search through the shared partition, rebuild-after-
eviction consistency (including garbage collection of dead sessions),
and clear().

Patches ``probe_dimension`` / ``embed`` (as imported into ``working``)
to avoid any OneLLM / network / HF calls.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

from muxi.runtime.services.memory.working import SHARED_PARTITION, WorkingMemory

DIM = 8


def _one_hot(position: int) -> list:
    """Distinct, orthogonal embedding for deterministic FAISS ranking."""
    vector = [0.0] * DIM
    vector[position] = 1.0
    return vector


def _mix(position_a: int, position_b: int) -> list:
    """Unit vector halfway between two one-hot axes (cosine 0.707 to each)."""
    weight = 1.0 / math.sqrt(2.0)
    vector = [0.0] * DIM
    vector[position_a] = weight
    vector[position_b] = weight
    return vector


def _make_memory() -> WorkingMemory:
    return WorkingMemory(
        formation_id="test-formation",
        max_size=10,
        buffer_multiplier=10,
        embedding_model="local/nomic-ai/nomic-embed-text-v1.5",
    )


def _patched():
    return (
        patch(
            "muxi.runtime.services.memory.working.probe_dimension",
            new_callable=AsyncMock,
        ),
        patch(
            "muxi.runtime.services.memory.working.embed",
            new_callable=AsyncMock,
        ),
    )


async def test_sessions_land_in_separate_partitions():
    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(i)] for i in range(4)]

        mem = _make_memory()
        await mem.add("a1", metadata={"session_id": "session-a"})
        await mem.add("a2", metadata={"session_id": "session-a"})
        await mem.add("b1", metadata={"session_id": "session-b"})
        await mem.add("no session")  # buffer item without session_id

        assert set(mem.partitions.keys()) == {"session-a", "session-b", SHARED_PARTITION}
        assert mem.partitions["session-a"].index_count == 2
        assert mem.partitions["session-b"].index_count == 1
        assert mem.partitions[SHARED_PARTITION].index_count == 1
        assert mem.index_count == 4


async def test_session_search_not_crowded_out_by_other_session():
    """Recall-dilution regression test.

    One relevant item in session A, twenty items in session B that sit
    exactly on the query vector, and a more recent decoy in session A.
    With the old single formation-wide index, top-k (k = limit * 2 = 2)
    was filled entirely by session B, the session filter emptied the
    results, and the recency fallback returned session A's most recent
    item — the decoy, without a semantic score. The per-session
    partition must return the relevant item via vector search.
    """
    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        embeddings = [[_mix(0, 1)]]  # session A: relevant (cos 0.707 to query)
        embeddings += [[_one_hot(1)] for _ in range(20)]  # session B: on the query
        embeddings += [[_one_hot(2)]]  # session A: recent decoy, orthogonal
        mock_embed.side_effect = embeddings

        mem = _make_memory()
        await mem.add("relevant", metadata={"session_id": "session-a"})
        for i in range(20):
            await mem.add(f"noise {i}", metadata={"session_id": "session-b"})
        await mem.add("decoy", metadata={"session_id": "session-a"})

        results = await mem.search(
            "query",
            query_vector=_one_hot(1),
            limit=1,
            session_id="session-a",
        )

        assert len(results) == 1
        assert results[0]["text"] == "relevant"
        # Vector-search result, not the recency fallback the old
        # single-index path degraded to.
        assert "score" in results[0]


async def test_sops_namespace_searchable_without_session_id():
    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(1)], [_one_hot(2)]]

        mem = _make_memory()
        # Session traffic must not interfere with the sops partition.
        await mem.add("chat a", metadata={"session_id": "session-a"})
        await mem.add("chat b", metadata={"session_id": "session-b"})
        await mem.add_with_embedding(
            "deploy runbook",
            embedding=_one_hot(0),
            metadata={"sop_id": "sop-1"},
            namespace="sops",
        )

        results = await mem.search(
            "how do I deploy",
            query_vector=_one_hot(0),
            limit=3,
            recency_bias=0.0,
            namespace="sops",
        )

        assert len(results) == 1
        assert results[0]["metadata"]["sop_id"] == "sop-1"
        # sops scoring returns true cosine similarity; exact match ~= 1.0.
        assert results[0]["score"] > 0.99


async def test_rebuild_after_eviction_drops_empty_partitions():
    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(i)] for i in range(4)] + [[_one_hot(3)]]

        mem = _make_memory()
        await mem.add("a1", metadata={"session_id": "session-a"})
        await mem.add("a2", metadata={"session_id": "session-a"})
        await mem.add("b1", metadata={"session_id": "session-b"})
        await mem.add("b2", metadata={"session_id": "session-b"})

        # Simulate eviction of all session A items (they are oldest),
        # then rebuild as the search path would.
        mem.buffer.popleft()
        mem.buffer.popleft()
        mem._rebuild_index()

        # Dead session partition is garbage-collected.
        assert set(mem.partitions.keys()) == {"session-b"}
        partition = mem.partitions["session-b"]
        assert partition.index_count == 2
        # Buffer indices shifted after eviction; mappings must follow.
        assert partition.index_mapping == {0: 0, 1: 1}
        assert partition.reverse_index_mapping == {0: 0, 1: 1}

        # Search still resolves the correct item post-rebuild (query
        # embedding is the final side_effect entry, matching "b2").
        results = await mem.search("query", limit=1, session_id="session-b")
        assert results
        assert results[0]["text"] == "b2"


async def test_clear_resets_all_partitions():
    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(i)] for i in range(3)]

        mem = _make_memory()
        await mem.add("a1", metadata={"session_id": "session-a"})
        await mem.add("b1", metadata={"session_id": "session-b"})
        await mem.add("shared")

        mem.clear()

        assert mem.partitions == {}
        assert mem.index_count == 0
        assert len(mem.buffer) == 0
