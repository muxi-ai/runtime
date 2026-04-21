"""Unit tests for the lazy-dim embedding path in ``SQLiteMemory``.

These tests exercise the migration of ``services/memory/sqlite.py`` to
the shared embedding helper (``services/memory/embedding.py``). They
patch the helper's ``probe_dimension`` / ``embed`` symbols (as imported
into ``sqlite``) to avoid any OneLLM / network / HF calls, and use a
real on-disk SQLite database (with the sqlite-vec extension) so the
round-trip assertion exercises actual BLOB storage and
``vec_distance_cosine`` search.

Coverage targets (see ``validation-contract.md``):
  * VAL-MEMORY-004 — ``SQLiteMemory`` ctor invokes zero
    ``probe_dimension`` and zero ``embed`` calls. First write packs
    vectors at the probed dim. ``add()`` → ``search()`` round-trip
    returns the written memory. Vector BLOB length matches
    ``probed_dim * sizeof(float32)``. Table name is
    ``memories_{probed_dim}``.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from muxi.runtime.services.memory.sqlite import SQLiteMemory

DIM = 768
MODEL = "local/nomic-ai/nomic-embed-text-v1.5"


def _deterministic_vec(text: str, dim: int = DIM) -> list[float]:
    """Cheap deterministic embedder: hash text → dim-sized float32 vector.

    Used by the round-trip test so that embedding the same text twice
    (once on ``add``, once on ``search``) produces identical vectors.
    ``vec_distance_cosine`` returns ~0 for identical vectors, so the
    just-added memory is guaranteed to be the top search hit.
    """
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(np.float32).tolist()


def _make_memory(db_path: str) -> SQLiteMemory:
    """Construct ``SQLiteMemory`` against a fresh on-disk file.

    Uses the default-model path by omitting ``embedding_model`` when
    possible; tests that require a specific slug pass it explicitly.
    """
    return SQLiteMemory(
        db_path=db_path,
        formation_id="test-formation",
        embedding_model=MODEL,
    )


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "memory.db")


async def test_construction_does_not_invoke_onellm(db_path):
    """VAL-MEMORY-004 — ``__init__`` makes zero probe / embed calls.

    Also verifies the lazy-dim invariants: the slug is stored as a
    string, ``_dimension`` is ``None`` until probed, and the
    dim-specific ``memories_{dim}`` table is NOT created at
    construction time.
    """
    with (
        patch(
            "muxi.runtime.services.memory.sqlite.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.sqlite.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mem = _make_memory(db_path)

        assert mock_probe.call_count == 0
        assert mock_embed.call_count == 0
        # Attribute contract: slug stored as a string; dim lazy-resolved.
        assert isinstance(mem._embedding_model_name, str)
        assert mem._embedding_model_name == MODEL
        assert mem._dimension is None
        # Dim-specific table is not created until _ensure_dim runs.
        assert mem.memories_table is None


async def test_add_search_round_trip(db_path):
    """VAL-MEMORY-004 — ``add()`` then ``search()`` returns the written text.

    Also verifies:
      * ``probe_dimension`` is called exactly once across add + search
        (memoized by ``_ensure_dim``).
      * The dim-specific ``memories_{dim}`` table is created at the
        probed dim.
      * Vector BLOB length equals ``probed_dim * sizeof(float32)``
        (4 bytes per element).
      * The write path forwards ``task="search_document"`` and the
        search path forwards ``task="search_query"`` via the shared
        helper — preserves the Nomic-style task prefix contract.
    """
    with (
        patch(
            "muxi.runtime.services.memory.sqlite.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.sqlite.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mock_probe.return_value = DIM

        def deterministic_embed(model, text, *, task=None, **_kw):
            # Match the helper contract: always returns list[list[float]].
            if isinstance(text, list):
                return [_deterministic_vec(t) for t in text]
            return [_deterministic_vec(text)]

        mock_embed.side_effect = deterministic_embed

        mem = _make_memory(db_path)

        memory_id = await mem.add("hello world")
        assert memory_id, "add() must return a non-empty memory id"

        # Probe called exactly once, dim memoized, table name derived.
        assert mock_probe.call_count == 1
        assert mem._dimension == DIM
        assert mem.memories_table == f"memories_{DIM}"

        # Round-trip via search — deterministic_embed produces identical
        # vectors for identical text, so cosine distance is ~0.
        results = await mem.search("hello world", limit=5)
        assert results, "search must return results for the just-added memory"
        assert results[0]["text"] == "hello world"

        # Probe still called only once after add + search (memoized).
        assert mock_probe.call_count == 1

        # Vector BLOB length must match probed dim * sizeof(float32).
        cursor = mem.conn.execute(
            f"SELECT length(embedding) FROM memories_{DIM} WHERE id = ?",
            (memory_id,),
        )
        blob_len = cursor.fetchone()[0]
        assert blob_len == DIM * 4, f"expected BLOB length {DIM * 4} (dim*float32), got {blob_len}"

        # Task-prefix contract — write path uses search_document,
        # search path uses search_query.
        add_calls = [
            c for c in mock_embed.call_args_list if c.kwargs.get("task") == "search_document"
        ]
        search_calls = [
            c for c in mock_embed.call_args_list if c.kwargs.get("task") == "search_query"
        ]
        assert len(add_calls) == 1, (
            f"expected 1 write call with task='search_document'; got: "
            f"{[c.kwargs for c in mock_embed.call_args_list]}"
        )
        assert len(search_calls) == 1, (
            f"expected 1 search call with task='search_query'; got: "
            f"{[c.kwargs for c in mock_embed.call_args_list]}"
        )
        # First positional arg is always the model slug.
        for call in mock_embed.call_args_list:
            assert call.args[0] == MODEL
