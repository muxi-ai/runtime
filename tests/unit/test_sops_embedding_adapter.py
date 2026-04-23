"""Unit tests for ``OneLLMEmbeddingAdapter`` in ``formation/workflow/sops.py``.

These tests verify that the SOP system's embedding adapter wraps the
shared :func:`muxi.runtime.services.memory.embedding.embed` helper and
exposes the minimal ``generate_embeddings`` contract the SOP search flow
depends on.

Coverage targets (see ``validation-contract.md``):
  * VAL-NONMEM-003 — ``OneLLMEmbeddingAdapter`` exists with
    ``__init__(self, model_name: str)`` and
    ``async def generate_embeddings(self, texts: list[str]) -> list[list[float]]``.
  * VAL-NONMEM-004 — ``adapter.generate_embeddings(["a", "b", "c"])`` returns
    a ``list`` of 3 ``list[float]`` elements.
  * VAL-MEMORY-008 — No ``.embedding_model.embed(...)`` call sites remain in
    ``sops.py``.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.formation.workflow.sops import OneLLMEmbeddingAdapter


def test_adapter_shape():
    """VAL-NONMEM-003: adapter has the exact public shape the contract requires.

    ``OneLLMEmbeddingAdapter`` must expose:
      * ``__init__(self, model_name: str)`` — a single required string arg
      * ``async def generate_embeddings(self, texts: list[str]) -> list[list[float]]``
    """
    # __init__ signature — exactly one required param beyond ``self``, named ``model_name``
    init_sig = inspect.signature(OneLLMEmbeddingAdapter.__init__)
    params = list(init_sig.parameters.values())
    assert params[0].name == "self"
    assert len(params) == 2, f"expected __init__(self, model_name), got {init_sig}"
    assert params[1].name == "model_name"

    # generate_embeddings is an async method
    assert hasattr(OneLLMEmbeddingAdapter, "generate_embeddings")
    assert asyncio.iscoroutinefunction(
        OneLLMEmbeddingAdapter.generate_embeddings
    ), "generate_embeddings must be async"

    gen_sig = inspect.signature(OneLLMEmbeddingAdapter.generate_embeddings)
    gen_params = list(gen_sig.parameters.values())
    assert gen_params[0].name == "self"
    assert gen_params[1].name == "texts"

    # Construction is cheap — the adapter stores the model name as a string only.
    adapter = OneLLMEmbeddingAdapter("local/nomic-ai/nomic-embed-text-v1.5")
    assert isinstance(adapter.model_name, str)
    assert adapter.model_name == "local/nomic-ai/nomic-embed-text-v1.5"


@pytest.mark.asyncio
async def test_generate_embeddings_shape():
    """VAL-NONMEM-004: ``generate_embeddings`` returns ``list[list[float]]`` of correct length."""
    expected = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]

    # Patch the ``embed`` helper as imported into sops.py (module-level import).
    with patch(
        "muxi.runtime.formation.workflow.sops.embed",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_embed:
        adapter = OneLLMEmbeddingAdapter("local/nomic-ai/nomic-embed-text-v1.5")
        result = await adapter.generate_embeddings(["a", "b", "c"])

    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(vec, list) for vec in result)
    assert all(isinstance(x, float) for vec in result for x in vec)
    assert result == expected

    # Helper must have been invoked exactly once with the model slug + texts.
    assert mock_embed.call_count == 1
    call = mock_embed.call_args
    # Accept positional or keyword calling convention — the contract is
    # "delegates to services.memory.embedding.embed", not a specific style.
    if call.args:
        assert call.args[0] == "local/nomic-ai/nomic-embed-text-v1.5"
        # texts appears as the second positional arg or as ``input`` kwarg
        if len(call.args) >= 2:
            assert call.args[1] == ["a", "b", "c"]
        else:
            assert call.kwargs.get("input") == ["a", "b", "c"]
    else:
        assert call.kwargs.get("model") == "local/nomic-ai/nomic-embed-text-v1.5"
        assert call.kwargs.get("input") == ["a", "b", "c"]


def test_sops_module_has_no_embedding_model_embed_callsites():
    """VAL-MEMORY-008: ``sops.py`` must not retain ``.embedding_model.embed(`` calls.

    Static source check — guards against regressions that reintroduce the
    pre-migration provider-object pattern.
    """
    from muxi.runtime.formation.workflow import sops as sops_module

    source = inspect.getsource(sops_module)
    assert ".embedding_model.embed(" not in source, (
        "sops.py must not call ``.embedding_model.embed(...)`` — the migration "
        "routes embeddings through OneLLMEmbeddingAdapter + shared helper."
    )


def test_sops_module_imports_shared_embed_helper():
    """VAL-NONMEM-003 (support): sops.py imports ``embed`` from the shared helper.

    The ``OneLLMEmbeddingAdapter`` delegates to
    ``services.memory.embedding.embed`` — the import must be at module scope
    so unit tests can patch it deterministically.
    """
    from muxi.runtime.formation.workflow import sops as sops_module

    assert hasattr(
        sops_module, "embed"
    ), "sops.py must import ``embed`` from services.memory.embedding at module scope"
