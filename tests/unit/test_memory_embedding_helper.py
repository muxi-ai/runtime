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
    _parse_model_slug,
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


# ---------------------------------------------------------------------------
# Slug revision parsing: ``local/<repo>:<revision>`` notation
# ---------------------------------------------------------------------------


class TestParseModelSlug:
    """Direct tests on the ``_parse_model_slug`` helper.

    The parser is the single source of truth for translating slug notation
    into an ``(model, revision)`` pair. Keeping tests direct (not via
    ``embed()``) makes regressions easy to localize.
    """

    def test_local_slug_without_revision_returns_none(self):
        assert _parse_model_slug("local/nomic-ai/nomic-embed-text-v1.5") == (
            "local/nomic-ai/nomic-embed-text-v1.5",
            None,
        )

    def test_local_slug_with_commit_sha(self):
        assert _parse_model_slug("local/nomic-ai/nomic-embed-text-v1.5:abc123def") == (
            "local/nomic-ai/nomic-embed-text-v1.5",
            "abc123def",
        )

    def test_local_slug_with_tag(self):
        assert _parse_model_slug("local/sentence-transformers/all-MiniLM-L6-v2:v1.0") == (
            "local/sentence-transformers/all-MiniLM-L6-v2",
            "v1.0",
        )

    def test_local_slug_with_branch_main_explicit(self):
        """Explicit ``:main`` is valid — same as omitting the suffix, but
        the explicit form may be preferred by config systems that always
        serialize revisions for auditability."""
        assert _parse_model_slug("local/foo/bar:main") == ("local/foo/bar", "main")

    def test_local_slug_longer_repo_path(self):
        """Repos with deeper paths still split on the first ``:`` only."""
        assert _parse_model_slug("local/foo/bar/baz/qux:rev") == (
            "local/foo/bar/baz/qux",
            "rev",
        )

    def test_cloud_slug_with_colon_passes_through(self):
        """``ollama/llama2:7b``-style cloud slugs use ``:`` for model
        variants, not revisions. The parser must not strip them."""
        assert _parse_model_slug("ollama/llama2:7b") == ("ollama/llama2:7b", None)

    def test_openai_slug_passes_through(self):
        assert _parse_model_slug("openai/text-embedding-3-small") == (
            "openai/text-embedding-3-small",
            None,
        )

    def test_local_slug_with_trailing_colon_raises(self):
        """Trailing ``:`` with no revision is rejected up front with a
        clear error rather than resolving silently to ``main`` downstream."""
        from onellm.errors import InvalidRequestError

        with pytest.raises(InvalidRequestError, match="trailing ':'"):
            _parse_model_slug("local/nomic-ai/nomic-embed-text-v1.5:")

    def test_empty_slug_raises(self):
        from onellm.errors import InvalidRequestError

        with pytest.raises(InvalidRequestError):
            _parse_model_slug("")

    def test_non_string_slug_raises(self):
        from onellm.errors import InvalidRequestError

        with pytest.raises(InvalidRequestError):
            _parse_model_slug(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Revision forwarding through ``embed()`` and ``probe_dimension()``
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_forwards_revision_from_slug():
    """A ``local/<repo>:<revision>`` slug reaches OneLLM as ``model``
    (without the suffix) + ``revision=`` kwarg. This is what makes
    reproducible-deployment pinning actually reach HuggingFace."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1] * 768]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed("local/nomic-ai/nomic-embed-text-v1.5:abc123", "x")

    _, kwargs = mock_acreate.call_args
    assert kwargs["model"] == "local/nomic-ai/nomic-embed-text-v1.5"
    assert kwargs["revision"] == "abc123"


@pytest.mark.asyncio
async def test_embed_omits_revision_when_slug_has_none():
    """A plain ``local/<repo>`` slug (no ``:``) must NOT send
    ``revision=None`` — OneLLM's default-path ("follow main") is taken
    when the kwarg is absent entirely."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1] * 768]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed("local/nomic-ai/nomic-embed-text-v1.5", "x")

    _, kwargs = mock_acreate.call_args
    assert kwargs["model"] == "local/nomic-ai/nomic-embed-text-v1.5"
    assert "revision" not in kwargs


@pytest.mark.asyncio
async def test_embed_ollama_style_colon_not_parsed_as_revision():
    """``ollama/llama2:7b`` is a model variant, not a revision. The
    slug must reach OneLLM intact; no ``revision=`` kwarg must appear."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed("ollama/llama2:7b", "x")

    _, kwargs = mock_acreate.call_args
    assert kwargs["model"] == "ollama/llama2:7b"
    assert "revision" not in kwargs


@pytest.mark.asyncio
async def test_embed_forwards_revision_alongside_task_and_dimensions():
    """Revision forwarding must not interfere with other kwargs on the
    local/* path (task, dimensions, pooling). This exercises all of them
    together to catch any kwarg-ordering bugs."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.1] * 256]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        await embed(
            "local/nomic-ai/nomic-embed-text-v1.5:sha_abc",
            "x",
            task="search_document",
            dimensions=256,
            pooling="mean",
        )

    _, kwargs = mock_acreate.call_args
    assert kwargs["model"] == "local/nomic-ai/nomic-embed-text-v1.5"
    assert kwargs["revision"] == "sha_abc"
    assert kwargs["task"] == "search_document"
    assert kwargs["dimensions"] == 256
    assert kwargs["pooling"] == "mean"


@pytest.mark.asyncio
async def test_probe_dimension_forwards_revision():
    """Dimension probe must fetch the SAME revision the subsequent real
    embeds will use — otherwise a revision with a different dim (e.g.
    v1 vs v2 of the same repo) would probe one dim and embed another."""
    mock_acreate = AsyncMock(return_value=_mock_response([[0.0] * 768]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        dim = await probe_dimension("local/nomic-ai/nomic-embed-text-v1.5:pinned_sha")

    _, kwargs = mock_acreate.call_args
    assert kwargs["model"] == "local/nomic-ai/nomic-embed-text-v1.5"
    assert kwargs["revision"] == "pinned_sha"
    assert dim == 768


@pytest.mark.asyncio
async def test_embed_trailing_colon_slug_raises_before_onellm_call():
    """A trailing-``:`` slug must fail fast in the helper — no OneLLM
    call, no HuggingFace round-trip, no silent fallback to ``main``."""
    from onellm.errors import InvalidRequestError

    mock_acreate = AsyncMock(return_value=_mock_response([[0.0]]))

    with patch("onellm.Embedding.acreate", mock_acreate):
        with pytest.raises(InvalidRequestError, match="trailing ':'"):
            await embed("local/nomic-ai/nomic-embed-text-v1.5:", "x")

    # Critical: OneLLM must not have been called.
    mock_acreate.assert_not_called()
