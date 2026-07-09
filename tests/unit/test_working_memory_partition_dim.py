"""Unit tests for per-partition FAISS dimensionality in ``WorkingMemory``.

Pre-computed embeddings (``add_with_embedding`` — the knowledge-chunk
path) may carry a different dimensionality than the memory's own
embedding model (e.g. 1536-dim OpenAI document embeddings inside the
768-dim Nomic buffer memory). Partitions must be created — and rebuilt —
at the dim of the vectors they store:

* creation at the memory-wide dim used to make every ``index.add`` fail
  silently (items landed in the buffer but never in FAISS), and
* ``_rebuild_index`` (triggered by ``remove_by_metadata``) used to
  shape-crash every subsequent vector search.

``probe_dimension`` is patched so no OneLLM / network calls happen.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from muxi.runtime.services.memory.working import WorkingMemory, _IndexPartition

MEMORY_DIM = 768
DOC_DIM = 1536


def _make_memory() -> WorkingMemory:
    return WorkingMemory(
        formation_id="test-formation",
        max_size=10,
        buffer_multiplier=2,
        embedding_model="local/nomic-ai/nomic-embed-text-v1.5",
    )


def _probe_patch():
    return patch(
        "muxi.runtime.services.memory.working.probe_dimension",
        new_callable=AsyncMock,
        return_value=MEMORY_DIM,
    )


class TestGetPartitionDimension:
    def test_explicit_dimension_wins_over_memory_dim(self):
        memory = _make_memory()
        partition = memory._get_partition("knowledge", dimension=DOC_DIM)
        assert isinstance(partition, _IndexPartition)
        assert partition.index.d == DOC_DIM

    def test_absent_dimension_falls_back_to_memory_dim(self):
        memory = _make_memory()
        partition = memory._get_partition("buffer")
        assert partition.index.d == memory.dimension

    def test_explicit_none_falls_back_but_explicit_value_never_does(self):
        """Only ``None`` means "no override" — the fallback is an explicit
        ``is not None`` check, not truthiness."""
        memory = _make_memory()
        assert memory._get_partition("a", dimension=None).index.d == memory.dimension
        assert memory._get_partition("b", dimension=DOC_DIM).index.d == DOC_DIM

    def test_existing_partition_returned_unchanged(self):
        memory = _make_memory()
        first = memory._get_partition("knowledge", dimension=DOC_DIM)
        second = memory._get_partition("knowledge")
        assert second is first
        assert second.index.d == DOC_DIM


class TestPrecomputedEmbeddingIndexing:
    async def test_add_with_embedding_indexes_foreign_dim_vectors(self):
        """A pre-computed vector whose dim differs from the memory's own
        model must actually land in FAISS (not just the buffer)."""
        memory = _make_memory()
        with _probe_patch():
            await memory.add_with_embedding(
                text="knowledge chunk",
                embedding=[0.1] * DOC_DIM,
                metadata={"source": "/mirror/a.md", "file_path": "/mirror/a.md"},
                namespace="knowledge",
            )
        # Knowledge-namespace items land in the formation-global partition
        key = memory._partition_key("knowledge", None)
        partition = memory.partitions[key]
        assert partition.index.d == DOC_DIM
        assert partition.index_count == 1

    async def test_rebuild_after_removal_preserves_partition_dims(self):
        """remove_by_metadata marks the index for rebuild; the rebuild
        must recreate each partition at its vectors' dim, and search with
        a matching query vector must succeed (this used to shape-crash)."""
        memory = _make_memory()
        with _probe_patch():
            for name in ("a", "b", "c"):
                await memory.add_with_embedding(
                    text=f"chunk {name}",
                    embedding=[0.1] * DOC_DIM,
                    metadata={"source": f"/mirror/{name}.md", "file_path": f"/mirror/{name}.md"},
                    namespace="knowledge",
                )

            removed = memory.remove_by_metadata(
                metadata_filter={"file_path": "/mirror/b.md"}, namespace="knowledge"
            )
            assert removed == 1
            assert memory.needs_rebuild

            results = await memory.search(
                query="",
                query_vector=[0.1] * DOC_DIM,
                limit=5,
                namespace="knowledge",
            )

        assert not memory.needs_rebuild
        key = memory._partition_key("knowledge", None)
        assert memory.partitions[key].index.d == DOC_DIM
        assert memory.partitions[key].index_count == 2
        texts = {result["text"] for result in results}
        assert texts == {"chunk a", "chunk c"}
