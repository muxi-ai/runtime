"""Unit tests for the lazy-dim embedding path in ``WorkingMemory``.

These tests exercise the migration of ``services/memory/working.py`` to
the shared embedding helper (``services/memory/embedding.py``). They
patch the helper's ``probe_dimension`` / ``embed`` symbols (as imported
into ``working``) to avoid any OneLLM / network / HF calls.

Coverage targets (see ``validation-contract.md``):
  * VAL-MEMORY-003 — ``WorkingMemory`` ctor invokes zero
    ``probe_dimension`` and zero ``embed`` calls; ``probe_dimension`` is
    called exactly once across the first two ``add()`` ops + first
    ``search()`` op, and the memoized dim is reused.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from muxi.runtime.services.memory.working import WorkingMemory


def _make_memory() -> WorkingMemory:
    """Construct ``WorkingMemory`` with the lazy-dim slug-only contract.

    ``buffer_multiplier`` and ``max_size`` are kept small so tests remain
    fast; the ``formation_id`` is set on every buffer item as part of
    ``add()`` — search filters rely on it.
    """
    return WorkingMemory(
        formation_id="test-formation",
        max_size=10,
        buffer_multiplier=2,
        embedding_model="local/nomic-ai/nomic-embed-text-v1.5",
    )


async def test_construction_does_not_invoke_onellm():
    """VAL-MEMORY-003 — ``__init__`` makes zero probe / embed calls."""
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
        mem = _make_memory()

        assert mock_probe.call_count == 0
        assert mock_embed.call_count == 0
        # Attribute contract: slug stored as a string; dim lazy-resolved.
        assert isinstance(mem._embedding_model_name, str)
        assert mem._embedding_model_name == "local/nomic-ai/nomic-embed-text-v1.5"
        assert mem._dimension is None


async def test_probe_called_once_across_first_ops():
    """VAL-MEMORY-003 — probe once across add, add, search.

    Also asserts that the shared helper (``embed``) is invoked exactly
    once per operation — confirming no legacy ``self.model.embed(...)``
    site remains in ``working.py``.
    """
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
        mock_probe.return_value = 768
        mock_embed.return_value = [[0.1] * 768]

        mem = _make_memory()

        await mem.add("first memory")
        await mem.add("second memory")
        await mem.search("query text")

        # Single probe across all three operations.
        assert mock_probe.call_count == 1
        assert mem._dimension == 768
        # Each op that needed embedding called the shared helper once:
        # two writes (search_document) + one search (search_query).
        assert mock_embed.call_count == 3

        # Kwargs verify task-prefix routing: writes use search_document,
        # search uses search_query. Helper is positional (model, input)
        # plus keyword ``task`` — matches the long_term.py contract.
        add_calls = [
            c for c in mock_embed.call_args_list if c.kwargs.get("task") == "search_document"
        ]
        search_calls = [
            c for c in mock_embed.call_args_list if c.kwargs.get("task") == "search_query"
        ]
        assert len(add_calls) == 2, (
            f"expected 2 write calls with task='search_document'; got: "
            f"{[c.kwargs for c in mock_embed.call_args_list]}"
        )
        assert len(search_calls) == 1, (
            f"expected 1 search call with task='search_query'; got: "
            f"{[c.kwargs for c in mock_embed.call_args_list]}"
        )
        # First positional arg is always the model slug.
        for call in mock_embed.call_args_list:
            assert call.args[0] == "local/nomic-ai/nomic-embed-text-v1.5"
