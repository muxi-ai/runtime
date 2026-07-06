"""Unit tests for the FAISS reverse index mapping in ``WorkingMemory``.

Semantic search previously mapped FAISS result indices back to buffer
indices by scanning the entire ``index_mapping`` dict per result
(O(k*n)). ``reverse_index_mapping`` replaces that with O(1) lookups.
These tests pin the invariant that both mappings stay exact inverses of
each other across every write path (add, rebuild, clear) and that
search results resolve to the correct buffer items.

Patches ``probe_dimension`` / ``embed`` (as imported into ``working``)
to avoid any OneLLM / network / HF calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from muxi.runtime.services.memory.working import WorkingMemory

DIM = 8


def _one_hot(position: int) -> list:
    """Distinct, orthogonal embedding for deterministic FAISS ranking."""
    vector = [0.0] * DIM
    vector[position] = 1.0
    return vector


def _make_memory() -> WorkingMemory:
    return WorkingMemory(
        formation_id="test-formation",
        max_size=10,
        buffer_multiplier=2,
        embedding_model="local/nomic-ai/nomic-embed-text-v1.5",
    )


def _assert_inverse(mem: WorkingMemory) -> None:
    """Both mappings must be exact inverses of each other."""
    assert mem.reverse_index_mapping == {
        faiss_idx: buffer_idx for buffer_idx, faiss_idx in mem.index_mapping.items()
    }
    assert len(mem.reverse_index_mapping) == len(mem.index_mapping)


async def test_mappings_stay_inverse_across_adds():
    with (
        patch(
            "muxi.runtime.services.memory.working.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.working.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(i)] for i in range(4)]

        mem = _make_memory()
        for i in range(4):
            await mem.add(f"memory {i}")

        assert mem.index_count == 4
        _assert_inverse(mem)


async def test_search_resolves_correct_buffer_item():
    with (
        patch(
            "muxi.runtime.services.memory.working.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.working.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_probe.return_value = DIM
        # Three writes, then a search query identical to item 1's vector.
        mock_embed.side_effect = [
            [_one_hot(0)],
            [_one_hot(1)],
            [_one_hot(2)],
            [_one_hot(1)],
        ]

        mem = _make_memory()
        await mem.add("memory zero")
        await mem.add("memory one")
        await mem.add("memory two")

        results = await mem.search("query matching memory one", limit=1)

        assert results, "semantic search returned no results"
        assert results[0]["text"] == "memory one"


async def test_mappings_stay_inverse_after_rebuild():
    with (
        patch(
            "muxi.runtime.services.memory.working.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.working.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(i)] for i in range(4)]

        mem = _make_memory()
        for i in range(4):
            await mem.add(f"memory {i}")

        # Simulate eviction: drop the oldest item so buffer indices
        # shift, then rebuild the index as the search path would.
        mem.buffer.popleft()
        mem._rebuild_index()

        assert mem.index_count == 3
        _assert_inverse(mem)
        # Buffer index 0 now holds what was item 1; FAISS row 0 must
        # resolve back to buffer index 0.
        assert mem.reverse_index_mapping[0] == 0


async def test_clear_resets_both_mappings():
    with (
        patch(
            "muxi.runtime.services.memory.working.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.working.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_probe.return_value = DIM
        mock_embed.side_effect = [[_one_hot(i)] for i in range(2)]

        mem = _make_memory()
        await mem.add("memory zero")
        await mem.add("memory one")

        mem.clear()

        assert mem.index_mapping == {}
        assert mem.reverse_index_mapping == {}
        assert mem.index_count == 0
