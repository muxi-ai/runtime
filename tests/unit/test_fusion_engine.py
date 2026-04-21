"""Unit tests for the embedding migration in ``MultiModalFusionEngine``.

These tests verify that ``services/multimodal/fusion_engine.py`` uses the
shared embedding helper (``services/memory/embedding.py``) instead of the
deprecated ``services/memory/local_embeddings.py`` path.

Coverage targets (see ``validation-contract.md``):
  * VAL-NONMEM-001 — ``FusionEngine`` imports from
    ``services.memory.embedding`` and contains no references to
    ``get_local_embedding_async`` / ``get_local_embedding``.
  * VAL-NONMEM-002 — ``_generate_embedding`` text round-trip returns a
    ``list[float]`` of the expected dimension via the new helper path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from muxi.runtime.services.multimodal.fusion_engine import TextProcessor


def _make_llm_without_get_embedding() -> MagicMock:
    """Build an ``LLM`` mock that deliberately lacks ``get_embedding``.

    This forces ``_generate_embedding`` down the helper-backed fallback
    path — which post-migration routes through
    ``services.memory.embedding.embed``.
    """
    llm = MagicMock(spec=["generate"])  # no get_embedding attribute
    return llm


async def test_text_embedding_via_helper():
    """VAL-NONMEM-002 — fusion engine text embedding uses the shared helper.

    Patches ``embed`` as imported into ``fusion_engine`` to a 768-dim
    vector (matching the mission default ``local/nomic-ai/nomic-embed-text-v1.5``)
    and asserts the returned value is a ``list[float]`` of that length,
    flowing through the new helper path.
    """
    expected_vector = [0.1] * 768

    with patch(
        "muxi.runtime.services.multimodal.fusion_engine.embed",
        new_callable=AsyncMock,
        return_value=[expected_vector],
    ) as mock_embed:
        processor = TextProcessor(_make_llm_without_get_embedding())

        result = await processor._generate_embedding("hello world")

        assert isinstance(result, list), f"expected list[float], got {type(result).__name__}"
        assert len(result) == 768, f"expected dim 768, got {len(result)}"
        assert all(isinstance(x, float) for x in result), "expected list[float] elements"
        assert result == expected_vector, "helper output must be returned unchanged"

        # Helper invoked exactly once with the provided text.
        assert mock_embed.call_count == 1
        call = mock_embed.call_args
        # ``embed(model, text, ...)`` — text appears as the second positional arg
        # or as the ``input`` kwarg. Support either style.
        if len(call.args) >= 2:
            assert call.args[1] == "hello world"
        else:
            assert call.kwargs.get("input") == "hello world"


async def test_text_embedding_helper_failure_falls_back():
    """When the helper raises, ``_generate_embedding`` must not crash.

    The existing contract preserves a fallback to the locally-computed
    semantic embedding (``_generate_semantic_fallback_embedding``). This
    test guards that behavior after the migration so any future helper
    outage does not break multimodal fusion.
    """
    with patch(
        "muxi.runtime.services.multimodal.fusion_engine.embed",
        new_callable=AsyncMock,
        side_effect=RuntimeError("helper unavailable"),
    ):
        processor = TextProcessor(_make_llm_without_get_embedding())

        result = await processor._generate_embedding("hello world")

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(x, float) for x in result)


def test_fusion_engine_has_no_local_embeddings_references():
    """VAL-NONMEM-001 — no lingering ``get_local_embedding*`` references.

    Static check on the module source to keep regressions from silently
    reintroducing the legacy path.
    """
    import inspect

    from muxi.runtime.services.multimodal import fusion_engine

    source = inspect.getsource(fusion_engine)
    assert (
        "get_local_embedding_async" not in source
    ), "fusion_engine.py must not reference get_local_embedding_async"
    assert (
        "get_local_embedding" not in source
    ), "fusion_engine.py must not reference get_local_embedding"
    assert (
        "local_embeddings" not in source
    ), "fusion_engine.py must not import from services.memory.local_embeddings"


def test_fusion_engine_imports_from_shared_helper():
    """VAL-NONMEM-001 — module imports ``embed`` from the shared helper."""
    from muxi.runtime.services.multimodal import fusion_engine

    # Post-migration, ``embed`` is imported at module scope so tests can
    # patch it deterministically without chasing deferred imports.
    assert hasattr(
        fusion_engine, "embed"
    ), "fusion_engine must expose ``embed`` imported from services.memory.embedding"
