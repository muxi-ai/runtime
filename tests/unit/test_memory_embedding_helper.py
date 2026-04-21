"""Unit tests for the shared embedding helper (``services/memory/embedding.py``).

These tests exercise the helper in isolation by patching
``onellm.Embedding.acreate``. Mock return values use ``types.SimpleNamespace``
to mimic OneLLM's ``EmbeddingResponse`` dataclass, which exposes its
fields via attribute access (``resp.data[0].embedding``) and explicitly
does NOT support ``__getitem__``.

Coverage targets (see ``validation-contract.md``):
  * VAL-HELPER-001 / 002 — module exists; constants as specified
  * VAL-HELPER-003     — shape of return value
  * VAL-HELPER-004     — ``dimensions`` kwarg forwarded
  * VAL-HELPER-005     — ``task`` kwarg forwarded for local models
  * VAL-HELPER-006     — dataclass attribute access (SimpleNamespace mock)
  * VAL-HELPER-009     — empty / whitespace-only input behavior
  * VAL-HELPER-011     — ``task=None`` (omitted) path works
  * VAL-HELPER-012     — ``task`` stripped for non-``local/*`` models
  * VAL-HELPER-013     — ``pooling`` forwarded when provided
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.services.memory.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    embed,
    probe_dimension,
)


def _mock_response(vectors: list[list[float]]) -> types.SimpleNamespace:
    """Build a SimpleNamespace that mimics an EmbeddingResponse dataclass.

    The returned object intentionally has no ``__getitem__`` — any attempt
    to index it (``resp["data"]``) must raise ``TypeError``. This guards
    against a regression to dict-style access.
    """

    return types.SimpleNamespace(
        object="list",
        data=[types.SimpleNamespace(embedding=vec, index=i) for i, vec in enumerate(vectors)],
        model="mock",
        usage=None,
    )


def test_default_model_is_nomic_v15():
    """VAL-HELPER-002: default model slug uses the Apache-2.0 Nomic v1.5 repo id."""
    assert DEFAULT_EMBEDDING_MODEL == "local/nomic-ai/nomic-embed-text-v1.5"


@pytest.mark.asyncio
async def test_embed_returns_list_of_vectors_for_single_input():
    """VAL-HELPER-003: a single-string input returns a 1-element list of vectors."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1, 0.2, 0.3]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        result = await embed(DEFAULT_EMBEDDING_MODEL, "hello world")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == [0.1, 0.2, 0.3]
    # Confirm OneLLM received a list (we normalize str -> [str])
    _, kwargs = mock_acreate.call_args
    assert kwargs["input"] == ["hello world"]


@pytest.mark.asyncio
async def test_embed_returns_list_of_vectors_for_batch_input():
    """VAL-HELPER-003: a batch input returns a list of the same length."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1], [0.2], [0.3]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        result = await embed(DEFAULT_EMBEDDING_MODEL, ["a", "b", "c"])

    assert len(result) == 3
    assert result == [[0.1], [0.2], [0.3]]
    _, kwargs = mock_acreate.call_args
    assert kwargs["input"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_embed_passes_dimensions_kwarg():
    """VAL-HELPER-004: ``dimensions`` is forwarded to ``onellm.Embedding.acreate``."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.0] * 256]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed(DEFAULT_EMBEDDING_MODEL, "x", dimensions=256)

    _, kwargs = mock_acreate.call_args
    assert kwargs["dimensions"] == 256


@pytest.mark.asyncio
async def test_embed_passes_task_kwarg():
    """VAL-HELPER-005: ``task`` is forwarded when the model is a ``local/*`` slug."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed(DEFAULT_EMBEDDING_MODEL, "x", task="search_document")

    _, kwargs = mock_acreate.call_args
    assert kwargs.get("task") == "search_document"


@pytest.mark.asyncio
async def test_embed_uses_dataclass_attribute_access():
    """VAL-HELPER-006: the helper must use attribute access, not ``__getitem__``.

    We return a SimpleNamespace (no ``__getitem__``); any subscript attempt
    will raise ``TypeError``. This test fails loudly if the implementation
    regresses to ``resp["data"][0]["embedding"]``.
    """

    class NoSubscript(types.SimpleNamespace):
        def __getitem__(self, _key):
            raise TypeError("EmbeddingResponse is a dataclass; use attribute access")

    response = NoSubscript(
        object="list",
        data=[NoSubscript(embedding=[0.1, 0.2], index=0)],
        model="mock",
        usage=None,
    )
    mock_acreate = AsyncMock(return_value=response)

    with patch("onellm.Embedding.acreate", mock_acreate):
        result = await embed(DEFAULT_EMBEDDING_MODEL, "x")

    assert result == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_embed_empty_string_behavior():
    """VAL-HELPER-009: empty string raises ``InvalidRequestError``.

    The helper validates up-front and raises — it does not silently emit a
    zero-vector. Documented in the module docstring.
    """
    from onellm.errors import InvalidRequestError

    # No mock needed — the helper must short-circuit before reaching OneLLM.
    with pytest.raises(InvalidRequestError):
        await embed(DEFAULT_EMBEDDING_MODEL, "")


@pytest.mark.asyncio
async def test_embed_whitespace_only_behavior():
    """VAL-HELPER-009: whitespace-only input raises ``InvalidRequestError``."""
    from onellm.errors import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        await embed(DEFAULT_EMBEDDING_MODEL, "   \t\n ")


@pytest.mark.asyncio
async def test_embed_task_none_path():
    """VAL-HELPER-011: omitting ``task`` works — no synthesized default."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.5]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed(DEFAULT_EMBEDDING_MODEL, "x")

    _, kwargs = mock_acreate.call_args
    # The helper must NOT synthesize a task kwarg when caller omitted it.
    assert "task" not in kwargs


@pytest.mark.asyncio
async def test_embed_strips_task_for_cloud_models():
    """VAL-HELPER-012: ``task`` is stripped for cloud provider slugs.

    Policy (documented in module docstring): the helper strips the ``task``
    kwarg when the model slug does NOT start with ``local/``. This prevents
    the ``task`` prefix from leaking into OpenAI / Cohere / Anthropic
    outbound requests (they would not recognize it).
    """
    mock_acreate = AsyncMock(return_value=_mock_response([[0.9]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed("openai/text-embedding-3-small", "x", task="search_document")

    _, kwargs = mock_acreate.call_args
    assert "task" not in kwargs
    # Other kwargs pass through normally
    assert kwargs["model"] == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_embed_passes_pooling_kwarg():
    """VAL-HELPER-013: ``pooling`` is forwarded when the caller provides it."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.0]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed(DEFAULT_EMBEDDING_MODEL, "x", pooling="cls")

    _, kwargs = mock_acreate.call_args
    assert kwargs.get("pooling") == "cls"


@pytest.mark.asyncio
async def test_probe_dimension_returns_length_of_first_embedding():
    """``probe_dimension`` issues a single embed call and returns ``len(vec)``."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.0] * 768]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        dim = await probe_dimension(DEFAULT_EMBEDDING_MODEL)

    assert dim == 768
    assert mock_acreate.await_count == 1
