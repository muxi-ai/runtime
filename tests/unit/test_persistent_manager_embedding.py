"""Unit tests for the query-embedding path in ``PersistentMemoryManager``.

These tests exercise the migration of
``src/muxi/runtime/formation/memory/persistent_manager.py`` to the
shared embedding helper. Pre-migration the manager read
``memory_backend.embedding_model.embed(...)``; post-migration it reads
the string slug from ``embedding_model_name`` (falling back to the
private ``_embedding_model_name`` used by the memory backends) and
delegates embedding generation to
:func:`muxi.runtime.services.memory.embedding.embed`.

Coverage targets (see ``validation-contract.md``):
  * VAL-NONMEM-006 — ``_generate_query_embedding`` returns a
    ``list[float]`` for a valid query + model slug.
  * VAL-MEMORY-006 — No ``.embedding_model.embed(...)`` call sites
    remain in ``persistent_manager.py`` (static source check).
  * VAL-MEMORY-008 — Query-embedding generation uses the shared helper
    (mock capture), passing the slug string as the model.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from muxi.runtime.formation.memory.persistent_manager import PersistentMemoryManager


def _make_manager(long_term_memory=None, is_multi_user: bool = False) -> PersistentMemoryManager:
    """Build a manager with a MagicMock overlord.

    ``long_term_memory`` is attached to ``overlord.long_term_memory`` so
    the manager's guard (``if not self.overlord.long_term_memory``) does
    not short-circuit.
    """
    overlord = MagicMock()
    overlord.long_term_memory = long_term_memory
    overlord.is_multi_user = is_multi_user
    return PersistentMemoryManager(overlord)


def _make_memory_backend_without_collections_kwarg(
    *,
    embedding_model_name: str | None = "local/nomic-ai/nomic-embed-text-v1.5",
    private_attr: bool = True,
) -> MagicMock:
    """Build a memory backend whose ``search()`` does NOT accept ``collections``.

    This forces the manager into the per-collection fallback path where
    ``_generate_query_embedding`` is invoked upfront so the query is
    embedded once and reused across per-collection ``search`` calls.

    The backend's ``_embedding_model_name`` (or public
    ``embedding_model_name``) attribute is populated with the provided
    slug so the manager has a model to forward to the shared helper.
    """
    backend = MagicMock()

    async def _search(
        query=None,
        limit=None,
        collection=None,
        filter_metadata=None,
        query_embedding=None,
    ):
        return []

    backend.search = _search
    # Build_search_parameters mirrors the LongTermMemory contract: it
    # accepts ``collection`` and ``query_embedding`` keyword arguments.

    def _build(
        query=None,
        k=None,
        user_id=None,
        full_filter=None,
        collection=None,
        query_embedding=None,
    ):
        params = {"query": query, "limit": k}
        if full_filter:
            params["filter_metadata"] = full_filter
        if collection:
            params["collection"] = collection
        if query_embedding is not None:
            params["query_embedding"] = query_embedding
        return params

    backend.build_search_parameters = _build

    # Publish the slug via the chosen attribute name. The manager should
    # read either the public or private form.
    if embedding_model_name is not None:
        if private_attr:
            backend._embedding_model_name = embedding_model_name
            # Ensure the public attribute does not accidentally resolve
            # — we want to validate the private-attribute read path.
            if hasattr(backend, "embedding_model_name"):
                del backend.embedding_model_name
        else:
            backend.embedding_model_name = embedding_model_name
    return backend


@pytest.mark.asyncio
async def test_query_embedding_generated():
    """VAL-NONMEM-006 — the migrated query-embedding path returns ``list[float]``.

    Patches the shared ``embed`` helper imported into ``persistent_manager``
    and verifies that the manager forwards the model slug + query and
    returns the resulting vector.
    """
    backend = _make_memory_backend_without_collections_kwarg()
    manager = _make_manager(long_term_memory=backend)

    expected_vector = [0.1, 0.2, 0.3, 0.4]

    with patch(
        "muxi.runtime.formation.memory.persistent_manager.embed",
        new_callable=AsyncMock,
        return_value=[expected_vector],
    ) as mock_embed:
        vector = await manager._generate_query_embedding(
            memory_backend=backend,
            query="what is the capital of france",
        )

    assert vector == expected_vector
    assert isinstance(vector, list)
    assert all(isinstance(x, float) for x in vector)
    # Helper invoked exactly once with (slug, query).
    assert mock_embed.call_count == 1
    call = mock_embed.call_args
    if call.args:
        assert call.args[0] == "local/nomic-ai/nomic-embed-text-v1.5"
        # Second positional arg OR ``input`` kwarg carries the query.
        if len(call.args) >= 2:
            assert call.args[1] == "what is the capital of france"
        else:
            assert call.kwargs.get("input") == "what is the capital of france"
    else:
        assert call.kwargs.get("model") == "local/nomic-ai/nomic-embed-text-v1.5"
        assert call.kwargs.get("input") == "what is the capital of france"


@pytest.mark.asyncio
async def test_query_embedding_reads_public_attribute_when_present():
    """Backend exposing the PRD-prescribed public ``embedding_model_name`` is honored."""
    backend = _make_memory_backend_without_collections_kwarg(
        embedding_model_name="openai/text-embedding-3-small",
        private_attr=False,
    )
    manager = _make_manager(long_term_memory=backend)

    with patch(
        "muxi.runtime.formation.memory.persistent_manager.embed",
        new_callable=AsyncMock,
        return_value=[[0.0, 0.0]],
    ) as mock_embed:
        vector = await manager._generate_query_embedding(
            memory_backend=backend,
            query="a query",
        )

    assert vector == [0.0, 0.0]
    call = mock_embed.call_args
    slug = call.args[0] if call.args else call.kwargs.get("model")
    assert slug == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_query_embedding_returns_none_when_no_model_slug():
    """Backend without a usable slug → ``_generate_query_embedding`` returns ``None``.

    The multi-collection fallback path in ``search_long_term_memory``
    relies on a ``None`` return to skip forwarding ``query_embedding``
    when no model is configured.
    """
    backend = _make_memory_backend_without_collections_kwarg(embedding_model_name=None)
    # Also strip the private attribute to simulate a backend that has no
    # embedding model configuration at all.
    if hasattr(backend, "_embedding_model_name"):
        del backend._embedding_model_name
    manager = _make_manager(long_term_memory=backend)

    with patch(
        "muxi.runtime.formation.memory.persistent_manager.embed",
        new_callable=AsyncMock,
    ) as mock_embed:
        vector = await manager._generate_query_embedding(
            memory_backend=backend,
            query="anything",
        )

    assert vector is None
    assert mock_embed.call_count == 0


def test_persistent_manager_module_has_no_legacy_embed_callsites():
    """VAL-MEMORY-006 / VAL-MEMORY-008 — no ``.embedding_model.embed(`` in source.

    Static source check guarding against regressions that reintroduce
    the pre-migration provider-object pattern.
    """
    from muxi.runtime.formation.memory import persistent_manager as pm_module

    source = inspect.getsource(pm_module)
    assert ".embedding_model.embed(" not in source, (
        "persistent_manager.py must not call ``.embedding_model.embed(...)`` — "
        "the migration reads ``embedding_model_name`` and delegates to the "
        "shared embedding helper."
    )
    assert (
        "._embedding_model.embed(" not in source
    ), "persistent_manager.py must not call ``._embedding_model.embed(...)``."


def test_persistent_manager_module_imports_shared_embed_helper():
    """The module imports ``embed`` at module scope so tests can patch it."""
    from muxi.runtime.formation.memory import persistent_manager as pm_module

    assert hasattr(
        pm_module, "embed"
    ), "persistent_manager.py must import ``embed`` from services.memory.embedding"


def test_persistent_manager_module_has_no_extract_embedding_helper_dependency():
    """Post-migration the manager no longer relies on the backend's
    ``_extract_embedding_from_response`` helper for query embeddings.

    The shared ``embed()`` helper already returns ``list[list[float]]``,
    so the response-unpacking indirection is obsolete for the query path.
    """
    from muxi.runtime.formation.memory import persistent_manager as pm_module

    source = inspect.getsource(pm_module)
    assert "_extract_embedding_from_response" not in source, (
        "persistent_manager.py must not depend on "
        "``_extract_embedding_from_response`` after the migration — the "
        "shared helper returns ``list[list[float]]`` directly."
    )
