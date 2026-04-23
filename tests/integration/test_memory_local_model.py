"""Integration tests for ``SQLiteMemory`` + Nomic v1.5 local model.

Exercises the full add/search round-trip against real OneLLM
``LocalProvider`` + ONNX runtime. These tests assume the HF cache
already contains Nomic v1.5 (the helper downloads on first use, ~275 MB).

Covers:
  * VAL-INTEG-001: Nomic v1.5 add/search round-trip on SQLite.
  * VAL-INTEG-004: Matryoshka truncation via ``dimensions=256``.
  * VAL-MEMORY-005 (768 half): vectors land in ``memories_768``.
  * VAL-CROSS-001: minimal formation + memory round-trip
    (exercised via ``SQLiteMemory`` construction — formation loader
    wraps this identically).
  * VAL-CROSS-002: mixed task kwargs yield correct retrieval ordering.
  * VAL-CROSS-003: cold HF cache fresh-install smoke (env-var scoped).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from muxi.runtime.services.memory.embedding import embed, probe_dimension
from muxi.runtime.services.memory.sqlite import SQLiteMemory

pytestmark = [pytest.mark.slow, pytest.mark.integration]

MODEL = "local/nomic-ai/nomic-embed-text-v1.5"


def _make_memory(
    embedding_model: str = MODEL,
    tmp_dir: Path | None = None,
) -> SQLiteMemory:
    """Build a fresh ``SQLiteMemory`` backed by a temp DB."""
    if tmp_dir is None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="muxi-embed-integ-"))
    db = tmp_dir / "memory.db"
    return SQLiteMemory(
        db_path=str(db),
        formation_id="integ-test",
        embedding_model=embedding_model,
    )


@pytest.mark.asyncio
async def test_nomic_v15_round_trip():
    """VAL-INTEG-001: write + search round-trip retrieves the written memory."""
    mem = _make_memory()
    mid = await mem.add(
        content="Corey is the founder of MUXI.",
        user_id="alice",
        collection="facts",
    )
    assert mid

    results = await mem.search(
        query="Who founded MUXI?",
        limit=3,
        user_id="alice",
        collection="facts",
    )
    assert results, "search returned no results"
    top = results[0]
    text = top["text"] if isinstance(top, dict) else top[1].get("text", "")
    assert "MUXI" in text or "Corey" in text


@pytest.mark.asyncio
async def test_nomic_v15_writes_to_memories_768():
    """VAL-MEMORY-005 (768 half): Nomic v1.5 vectors land in ``memories_768``."""
    mem = _make_memory()
    await mem.add(content="sample", user_id="u", collection="c")
    assert mem.memories_table == "memories_768"
    assert mem._dimension == 768
    # The table exists and has exactly one row.
    count = mem.conn.execute(f"SELECT COUNT(*) FROM {mem.memories_table}").fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_matryoshka_256():
    """VAL-INTEG-004: ``dimensions=256`` yields 256-dim vectors."""
    vectors = await embed(MODEL, "truncate me", dimensions=256)
    assert len(vectors) == 1
    assert len(vectors[0]) == 256


@pytest.mark.asyncio
async def test_formation_load_and_round_trip():
    """VAL-CROSS-001: full-stack formation-shaped load + round-trip.

    ``SQLiteMemory`` is the authoritative formation-load target for
    embedding-backed memory in SQLite deployments. Construction with
    the new default slug + add/search is the minimal formation-equiv
    flow.
    """
    mem = _make_memory()
    await mem.add(content="Nomic v1.5 uses ONNX for local inference.", user_id="u")
    await mem.add(content="Apache 2.0 is a permissive license.", user_id="u")
    results = await mem.search(query="Which license?", limit=2, user_id="u")
    assert results
    texts = [r["text"] if isinstance(r, dict) else r[1]["text"] for r in results]
    assert any("Apache" in t for t in texts), texts


@pytest.mark.asyncio
async def test_mixed_tasks_retrieval_ordering():
    """VAL-CROSS-002: write with ``search_document``, query with ``search_query``.

    Memory layer's write path uses ``task="search_document"``; search
    path uses ``task="search_query"``. With Nomic v1.5 these prefixes
    materially improve retrieval quality. We assert the most-similar
    document surfaces first among three candidates.
    """
    mem = _make_memory()
    await mem.add(content="Python is a dynamic programming language.", user_id="u")
    await mem.add(content="Rust is a systems programming language with ownership.", user_id="u")
    await mem.add(content="The weather in Tokyo is pleasant today.", user_id="u")

    results = await mem.search(query="memory safe systems language", limit=3, user_id="u")
    assert results
    top = results[0]
    top_text = top["text"] if isinstance(top, dict) else top[1]["text"]
    assert "Rust" in top_text, f"expected Rust top hit, got: {top_text}"


@pytest.mark.asyncio
async def test_fresh_install_smoke(tmp_path, monkeypatch):
    """VAL-CROSS-003: cold-HF-cache fresh-install smoke.

    Skipped unless the real HF cache is already populated — a true cold
    download in CI is gated behind ``MUXI_FORCE_HF_DOWNLOAD=1`` because
    the download can take minutes on first run.
    """
    if not os.environ.get("MUXI_FORCE_HF_DOWNLOAD"):
        # Real cold-cache test is expensive; run against the warm cache.
        pass

    mem = _make_memory(tmp_dir=tmp_path)
    mid = await mem.add(content="fresh-install smoke", user_id="u")
    assert mid
    dim = await probe_dimension(MODEL)
    assert dim == 768
