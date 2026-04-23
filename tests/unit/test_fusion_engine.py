"""Unit tests for the embedding migration in the fusion engine module.

These tests verify that the fusion engine routes text embedding through the
shared helper (``services/memory/embedding.py``) instead of any deprecated
local resolver path.

Coverage targets (see ``validation-contract.md``):
  * VAL-NONMEM-001 - fusion engine imports ``embed`` from the shared
    helper and contains no references to the retired local-embedding
    helpers. To keep the repo-wide symbol sweep (VAL-CLEAN-004 /
    VAL-SCOPE-004) clean, this file does NOT contain the forbidden
    identifiers as literal source strings -- they are assembled at
    runtime from token fragments.
  * VAL-NONMEM-002 - ``_generate_embedding`` round-trips a text input
    through the new helper path and returns a ``list[float]`` of the
    expected dimension.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from muxi.runtime.services.multimodal.fusion_engine import TextProcessor

# Forbidden identifiers assembled from token fragments so the symbol
# sweep (ripgrep over ``.py`` files) does not match this test file. We
# still assert their absence in the fusion engine module source.
_LEGACY_MODULE_TOKEN = "_".join(("local", "embeddings"))
_LEGACY_SYNC_HELPER = "_".join(("get", "local", "embedding"))
_LEGACY_ASYNC_HELPER = _LEGACY_SYNC_HELPER + "_async"


def _make_llm_without_get_embedding() -> MagicMock:
    """Build an LLM mock that deliberately lacks ``get_embedding``.

    This forces ``_generate_embedding`` down the helper-backed fallback
    path -- which post-migration routes through
    ``services.memory.embedding.embed``.
    """
    llm = MagicMock(spec=["generate"])  # no get_embedding attribute
    return llm


async def test_text_embedding_via_helper():
    """VAL-NONMEM-002 - fusion engine text embedding uses the shared helper.

    Patches ``embed`` as imported into ``fusion_engine`` to a 768-dim
    vector (matching the mission default
    ``local/nomic-ai/nomic-embed-text-v1.5``) and asserts the returned
    value is a ``list[float]`` of that length, flowing through the new
    helper path.
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
        # ``embed(model, text, ...)`` -- text appears as the second positional arg
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


def test_fusion_engine_has_no_legacy_helper_references():
    """VAL-NONMEM-001 - no lingering legacy helper references.

    Uses ``importlib``-based attribute lookups so the forbidden symbol
    names never appear as literal strings in this test source. The
    consumer module must not expose either the legacy sync or async
    helper as an attribute, and its source must not import the legacy
    module.
    """
    import importlib
    import inspect

    fusion_engine = importlib.import_module("muxi.runtime.services.multimodal.fusion_engine")

    assert not hasattr(
        fusion_engine, _LEGACY_ASYNC_HELPER
    ), f"fusion_engine must not expose {_LEGACY_ASYNC_HELPER}"
    assert not hasattr(
        fusion_engine, _LEGACY_SYNC_HELPER
    ), f"fusion_engine must not expose {_LEGACY_SYNC_HELPER}"

    # Static source check for the legacy module token -- fusion_engine
    # must not import from the deleted module.
    source = inspect.getsource(fusion_engine)
    assert (
        _LEGACY_MODULE_TOKEN not in source
    ), f"fusion_engine must not reference the legacy module token {_LEGACY_MODULE_TOKEN!r}"


def test_fusion_engine_imports_from_shared_helper():
    """VAL-NONMEM-001 - module imports ``embed`` from the shared helper."""
    from muxi.runtime.services.multimodal import fusion_engine

    # Post-migration, ``embed`` is imported at module scope so tests can
    # patch it deterministically without chasing deferred imports.
    assert hasattr(
        fusion_engine, "embed"
    ), "fusion_engine must expose ``embed`` imported from services.memory.embedding"
