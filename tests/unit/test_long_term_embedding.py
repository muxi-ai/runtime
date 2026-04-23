"""Unit tests for the lazy-dim embedding path in ``LongTermMemory``.

These tests exercise the migration to the shared embedding helper
(``services/memory/embedding.py``) in isolation. They patch the helper's
``probe_dimension`` / ``embed`` symbols (as imported into
``long_term``) to avoid any OneLLM / network / HF calls.

Coverage targets (see ``validation-contract.md``):
  * VAL-MEMORY-001 — ``LongTermMemory`` ctor invokes zero ``probe_dimension``
    and zero ``embed`` calls.
  * VAL-MEMORY-002 — ``probe_dimension`` called exactly once across the
    first two ``add()`` calls + first ``search()`` call.
  * VAL-HELPER-008 — concurrent ``_ensure_dim()`` calls share a single
    probe (asyncio.Lock).
  * VAL-INTEG-005 — ``add()`` forwards ``task="search_document"`` and
    ``search()`` forwards ``task="search_query"``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muxi.runtime.services.memory.long_term import LongTermMemory


def _build_db_manager():
    """Build a MagicMock ``DatabaseManager`` that looks like PostgreSQL.

    Using ``database_type="postgresql"`` keeps the SQLite-only
    ``_ensure_default_user`` path out of the constructor. The pgvector
    extension check is patched out separately (see ``_make_memory``).
    """
    db = MagicMock()
    db.database_type = "postgresql"
    db.engine = MagicMock()
    db.Session = MagicMock()
    db.AsyncSession = MagicMock()
    db.get_async_session = MagicMock()
    return db


def _make_memory(db_manager) -> LongTermMemory:
    """Construct ``LongTermMemory`` with pgvector setup neutralized.

    ``_ensure_pgvector_extension`` runs raw SQL against the engine in
    single-user mode; patching it keeps the constructor pure.
    """
    with patch.object(LongTermMemory, "_ensure_pgvector_extension", lambda self: None):
        return LongTermMemory(
            db_manager=db_manager,
            formation_id="test-formation",
            embedding_model="local/nomic-ai/nomic-embed-text-v1.5",
        )


@pytest.fixture
def db_manager():
    return _build_db_manager()


async def test_construction_does_not_invoke_onellm(db_manager):
    """VAL-MEMORY-001 — ``__init__`` makes zero probe / embed calls."""
    with (
        patch(
            "muxi.runtime.services.memory.long_term.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.long_term.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
    ):
        mem = _make_memory(db_manager)

        assert mock_probe.call_count == 0
        assert mock_embed.call_count == 0
        # Attribute contract: slug stored as a string; dim lazy-resolved.
        assert isinstance(mem._embedding_model_name, str)
        assert mem._embedding_model_name == "local/nomic-ai/nomic-embed-text-v1.5"
        assert mem._dimension is None


async def test_probe_called_once_across_first_ops(db_manager):
    """VAL-MEMORY-002 — probe once across add, add, search."""
    with (
        patch(
            "muxi.runtime.services.memory.long_term.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.long_term.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
        patch.object(
            LongTermMemory,
            "_add_internal_async",
            new_callable=AsyncMock,
            return_value="mem-id",
        ),
        patch.object(
            LongTermMemory,
            "_search_internal_async",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_probe.return_value = 768
        mock_embed.return_value = [[0.0] * 768]

        mem = _make_memory(db_manager)

        await mem.add("first memory")
        await mem.add("second memory")
        await mem.search("query text")

        assert mock_probe.call_count == 1
        assert mem._dimension == 768
        # Each op that needed embedding called the shared helper once.
        assert mock_embed.call_count == 3


async def test_ensure_dim_concurrent_single_probe(db_manager):
    """VAL-HELPER-008 — concurrent ``_ensure_dim`` shares a single probe.

    Two coroutines hit ``_ensure_dim`` simultaneously on a fresh
    instance; only one underlying ``probe_dimension`` call is issued,
    and both callers receive the same memoized dim.
    """
    with patch(
        "muxi.runtime.services.memory.long_term.probe_dimension",
        new_callable=AsyncMock,
    ) as mock_probe:

        async def slow_probe(*_args, **_kwargs):
            # Yield control so the second coroutine enters the lock's
            # acquire queue before the first finishes probing.
            await asyncio.sleep(0.01)
            return 768

        mock_probe.side_effect = slow_probe

        mem = _make_memory(db_manager)

        d1, d2 = await asyncio.gather(mem._ensure_dim(), mem._ensure_dim())

        assert d1 == 768
        assert d2 == 768
        assert mock_probe.call_count == 1


async def test_task_prefix_on_add_and_search(db_manager):
    """VAL-INTEG-005 — add() uses ``search_document``; search() uses ``search_query``."""
    with (
        patch(
            "muxi.runtime.services.memory.long_term.probe_dimension",
            new_callable=AsyncMock,
        ) as mock_probe,
        patch(
            "muxi.runtime.services.memory.long_term.embed",
            new_callable=AsyncMock,
        ) as mock_embed,
        patch.object(
            LongTermMemory,
            "_add_internal_async",
            new_callable=AsyncMock,
            return_value="mem-id",
        ),
        patch.object(
            LongTermMemory,
            "_search_internal_async",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_probe.return_value = 768
        mock_embed.return_value = [[0.0] * 768]

        mem = _make_memory(db_manager)

        await mem.add("a document to embed")
        add_call = mock_embed.call_args
        assert (
            add_call.kwargs.get("task") == "search_document"
        ), f"add() must forward task='search_document'; got kwargs={add_call.kwargs}"
        # First positional arg is the model slug, second is the text.
        assert add_call.args[0] == "local/nomic-ai/nomic-embed-text-v1.5"
        assert add_call.args[1] == "a document to embed"

        await mem.search("a retrieval query")
        search_call = mock_embed.call_args
        assert (
            search_call.kwargs.get("task") == "search_query"
        ), f"search() must forward task='search_query'; got kwargs={search_call.kwargs}"
        assert search_call.args[0] == "local/nomic-ai/nomic-embed-text-v1.5"
        assert search_call.args[1] == "a retrieval query"
