"""Integration tests for OpenAI cloud embeddings (regression).

Covers:
  * VAL-INTEG-003: OpenAI text-embedding-3-small round-trip works.
  * VAL-MEMORY-005 (1536 half): OpenAI vectors land in ``memories_1536``.
  * VAL-HELPER-012: ``task`` kwarg is NOT forwarded to cloud providers.
  * VAL-CROSS-004: existing OpenAI formations keep working unchanged.

Tests skip gracefully when ``OPENAI_API_KEY`` is unset.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from muxi.runtime.services.memory.embedding import embed
from muxi.runtime.services.memory.sqlite import SQLiteMemory

pytestmark = [pytest.mark.slow, pytest.mark.integration]

MODEL = "openai/text-embedding-3-small"


def _skip_if_no_key():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set — OpenAI integration tests require a live key")


def _make_memory() -> SQLiteMemory:
    tmp_dir = Path(tempfile.mkdtemp(prefix="muxi-openai-"))
    db = tmp_dir / "memory.db"
    return SQLiteMemory(db_path=str(db), formation_id="openai-test", embedding_model=MODEL)


@pytest.mark.asyncio
async def test_openai_regression():
    """VAL-INTEG-003: OpenAI text-embedding-3-small round-trip works."""
    _skip_if_no_key()
    mem = _make_memory()
    await mem.add(content="The Pacific Ocean is the largest ocean on Earth.", user_id="u")
    results = await mem.search(query="Which is the biggest ocean?", limit=1, user_id="u")
    assert results
    top = results[0]
    text = top["text"] if isinstance(top, dict) else top[1]["text"]
    assert "Pacific" in text or "ocean" in text.lower()


@pytest.mark.asyncio
async def test_openai_writes_to_memories_1536():
    """VAL-MEMORY-005 (1536 half): OpenAI vectors land in ``memories_1536``."""
    _skip_if_no_key()
    mem = _make_memory()
    await mem.add(content="dim-bucket test", user_id="u")
    assert mem.memories_table == "memories_1536"
    assert mem._dimension == 1536


@pytest.mark.asyncio
async def test_openai_embed_does_not_receive_task_kwarg(monkeypatch):
    """VAL-HELPER-012: ``task`` is NOT forwarded to cloud providers.

    Patches the underlying ``onellm.Embedding.acreate`` to capture
    kwargs and asserts ``task`` is absent even when the helper is
    invoked with one (the helper strips ``task`` for non-``local/*``
    slugs).
    """
    import onellm
    from onellm.models import EmbeddingData, EmbeddingResponse

    captured: dict = {}

    async def fake_acreate(**kwargs):
        captured.update(kwargs)
        # Return a minimal fake response.
        fake_embedding = [0.0] * 1536
        return EmbeddingResponse(
            object="list",
            data=[EmbeddingData(object="embedding", embedding=fake_embedding, index=0)],
            model=kwargs.get("model", MODEL),
            usage={"prompt_tokens": 1, "total_tokens": 1},
        )

    monkeypatch.setattr(onellm.Embedding, "acreate", fake_acreate)

    await embed(MODEL, "hello", task="search_document")
    assert (
        "task" not in captured
    ), f"task kwarg must be stripped for cloud model slugs; captured: {captured}"


@pytest.mark.asyncio
async def test_existing_openai_formation_unchanged():
    """VAL-CROSS-004: existing OpenAI formations work with no user-visible change."""
    _skip_if_no_key()
    mem = _make_memory()
    mid = await mem.add(content="baseline memory", user_id="u")
    assert mid
    results = await mem.search(query="baseline memory", limit=1, user_id="u")
    assert results
