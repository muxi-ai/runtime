"""Unit tests for the embedding dim-probe migration in ``KnowledgeHandler``.

These tests verify that
``src/muxi/runtime/formation/agents/knowledge/handler.py`` routes dim
resolution through the shared helper
(``services/memory/embedding.py::probe_dimension``) instead of the
deprecated ``services/memory/local_embeddings.py`` resolvers, and that
the probe result is memoized per handler instance.

Coverage targets (see ``validation-contract.md``):
  * VAL-NONMEM-005 — ``handler.py`` imports ``probe_dimension`` from the
    shared helper. No references to ``resolve_embedding_dimension`` or
    ``get_local_embedding_dimension`` remain. The dim probe is memoized
    on the handler instance (mock capture confirms a single underlying
    ``probe_dimension`` call across repeated ``_probe_embedding_dim``
    invocations).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muxi.runtime.formation.agents.knowledge.handler import KnowledgeHandler


def _make_working_memory_mock() -> MagicMock:
    """Build a ``WorkingMemory`` mock sufficient for handler construction.

    The handler's ``_init_document_components`` accepts a pre-built
    ``WorkingMemory`` and skips its own lazy instantiation, keeping the
    test insulated from FAISS / filesystem init.
    """
    wm = MagicMock()
    wm.add_with_embedding = AsyncMock()
    wm.search = AsyncMock(return_value=[])
    wm.get_items_by_metadata = MagicMock(return_value=[])
    wm.remove_by_metadata = MagicMock(return_value=0)
    return wm


def _make_handler(embedding_dimension: int | None = 768) -> KnowledgeHandler:
    """Construct a ``KnowledgeHandler`` with a pre-built ``WorkingMemory``.

    ``embedding_dimension`` is forwarded to the ctor; callers that want to
    exercise the lazy probe path can reset ``_embedding_dim_cache`` on the
    returned handler to force a re-probe on the next
    ``_probe_embedding_dim`` call.
    """
    return KnowledgeHandler(
        agent_id_or_sources="test-agent",
        formation_id="test-formation",
        embedding_dimension=embedding_dimension,
        working_memory=_make_working_memory_mock(),
        auto_inject_knowledge=False,
    )


def test_handler_imports_probe_dimension_from_shared_helper():
    """VAL-NONMEM-005 (import check): ``probe_dimension`` at module scope."""
    from muxi.runtime.formation.agents.knowledge import handler as handler_module

    assert hasattr(handler_module, "probe_dimension"), (
        "handler.py must import ``probe_dimension`` at module scope from "
        "services.memory.embedding so tests can patch it deterministically."
    )


def test_handler_has_no_legacy_dim_imports():
    """VAL-NONMEM-005 (sweep guard): no references to legacy dim resolvers.

    Source-level static check — prevents regressions that silently
    reintroduce the deprecated ``local_embeddings.py`` resolvers.
    """
    from muxi.runtime.formation.agents.knowledge import handler as handler_module

    source = inspect.getsource(handler_module)
    assert "resolve_embedding_dimension" not in source, (
        "handler.py must not reference ``resolve_embedding_dimension`` "
        "(deprecated — replaced by ``probe_dimension`` from the shared helper)."
    )
    assert "get_local_embedding_dimension" not in source, (
        "handler.py must not reference ``get_local_embedding_dimension`` "
        "(deprecated — replaced by ``probe_dimension`` from the shared helper)."
    )
    assert (
        "local_embeddings" not in source
    ), "handler.py must not import from ``services.memory.local_embeddings``."


@pytest.mark.asyncio
async def test_dim_probe_memoized():
    """VAL-NONMEM-005: ``_probe_embedding_dim`` memoizes per handler instance.

    Multiple invocations of ``_probe_embedding_dim`` on the same handler
    result in exactly one call to ``probe_dimension``. The cached result
    is returned on every subsequent invocation.
    """
    handler = _make_handler()
    # Reset the cache to exercise the lazy probe path.
    handler._embedding_dim_cache = None

    with patch(
        "muxi.runtime.formation.agents.knowledge.handler.probe_dimension",
        new_callable=AsyncMock,
        return_value=768,
    ) as mock_probe:
        d1 = await handler._probe_embedding_dim("local/nomic-ai/nomic-embed-text-v1.5")
        d2 = await handler._probe_embedding_dim("local/nomic-ai/nomic-embed-text-v1.5")
        d3 = await handler._probe_embedding_dim("local/nomic-ai/nomic-embed-text-v1.5")

    assert d1 == d2 == d3 == 768
    assert mock_probe.call_count == 1, (
        f"probe_dimension must be invoked exactly once per handler instance; "
        f"got {mock_probe.call_count} calls."
    )
    assert handler._embedding_dim_cache == 768


@pytest.mark.asyncio
async def test_dim_probe_delegates_to_shared_helper():
    """VAL-NONMEM-005: ``_probe_embedding_dim`` delegates to the shared helper.

    The method must forward the model slug to
    ``services.memory.embedding.probe_dimension`` — not any legacy
    resolver — and return the helper's result unchanged.
    """
    handler = _make_handler()
    handler._embedding_dim_cache = None

    with patch(
        "muxi.runtime.formation.agents.knowledge.handler.probe_dimension",
        new_callable=AsyncMock,
        return_value=1024,
    ) as mock_probe:
        dim = await handler._probe_embedding_dim("custom/model-slug")

    assert dim == 1024
    mock_probe.assert_awaited_once_with("custom/model-slug")


@pytest.mark.asyncio
async def test_dim_probe_returns_prepopulated_cache_without_probe():
    """VAL-NONMEM-005: handler ctor pre-populates the cache from ``embedding_dimension``.

    When the cache is non-empty at invocation time, ``_probe_embedding_dim``
    must NOT call ``probe_dimension`` — the pre-resolved dim short-circuits
    any lazy probe. This guards consumers that construct the handler
    directly with an explicit dim (bypassing ``from_agent_config``).
    """
    handler = _make_handler(embedding_dimension=1536)

    with patch(
        "muxi.runtime.formation.agents.knowledge.handler.probe_dimension",
        new_callable=AsyncMock,
        return_value=9999,  # deliberately different to prove cache wins
    ) as mock_probe:
        dim = await handler._probe_embedding_dim("any/slug")

    assert dim == 1536
    assert mock_probe.call_count == 0
