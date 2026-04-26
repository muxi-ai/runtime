"""Unit tests for the agent's knowledge-handler embedding wiring.

These tests guard the post-fix invariants of
``Agent._initialize_knowledge`` in ``formation/agents/agent.py``:

  1. The embedding function passed to the knowledge handler is built
     from a ``OneLLMEmbeddingAdapter`` (i.e. routes through the shared
     ``services.memory.embedding.embed`` helper) — NOT from the agent's
     chat-model attribute.
  2. The adapter's model slug comes from
     ``working_memory.embedding_model_name`` when available, falling
     back to ``DEFAULT_EMBEDDING_MODEL`` (= ``local/nomic-ai/nomic-embed-text-v1.5``)
     when working memory is None or returns no slug.
  3. Defense-in-depth: ``LLM.generate_embeddings`` and ``LLM.embed``
     default to the runtime-wide local embedder, NOT to OpenAI. Earlier
     defaults silently coupled every embedding call to OpenAI auth and
     made formations that only configured an Anthropic chat key fail
     knowledge ingestion with "OpenAI API key is required".

The tests use static source inspection where possible to keep them fast
and free of heavyweight ``Agent`` instantiation.
"""

from __future__ import annotations

import inspect

from muxi.runtime.formation.agents import agent as agent_module
from muxi.runtime.services.llm import llm as llm_module
from muxi.runtime.services.memory.embedding import DEFAULT_EMBEDDING_MODEL


def test_default_embedding_model_is_local_nomic():
    """Belt-and-braces: the runtime-wide default embedder is the local Nomic
    slug. The agent fix and both ``LLM`` default paths rely on this constant
    pointing at an offline-safe local model."""
    assert DEFAULT_EMBEDDING_MODEL == "local/nomic-ai/nomic-embed-text-v1.5"


def test_agent_does_not_embed_via_chat_model_attribute():
    """Static guard against the regression we just fixed.

    Earlier ``_initialize_knowledge`` resolved ``embedding_fn`` via
    ``self.model.generate_embeddings`` / ``self.model.get_embeddings`` /
    ``self.model.embed`` — i.e. asked the *chat* LLM to embed. That
    coupling was wrong (chat capability and embedding capability are
    orthogonal) and dragged knowledge ingestion through
    ``LLM.generate_embeddings``'s OpenAI default. None of those
    chat-model embedding *call sites* must reappear inside
    ``_initialize_knowledge``.

    We scope the check to the method source (rather than the whole
    module) because the docstring intentionally mentions the old
    pattern to explain why it was removed.
    """
    method_source = inspect.getsource(agent_module.Agent._initialize_knowledge)
    forbidden_callsites = [
        # An assignment of ``embedding_fn`` from a chat-model attribute
        # would always look like one of these.
        "embedding_fn = self.model.generate_embeddings",
        "embedding_fn = self.model.get_embeddings",
        # The hasattr cascade used by the old code.
        'hasattr(self.model, "generate_embeddings")',
        'hasattr(self.model, "get_embeddings")',
        'hasattr(self.model, "embed")',
        # An ``await self.model.embed(...)`` call inside the method body.
        "await self.model.embed(",
    ]
    for pattern in forbidden_callsites:
        assert pattern not in method_source, (
            f"_initialize_knowledge must not embed via the chat model: "
            f"found {pattern!r}. Knowledge embedding must flow through "
            "OneLLMEmbeddingAdapter + the shared "
            "services.memory.embedding.embed helper instead."
        )


def test_agent_uses_onellm_embedding_adapter_for_knowledge():
    """The agent must construct knowledge ``embedding_fn`` from
    ``OneLLMEmbeddingAdapter``. Static source check keeps this cheap and
    deterministic."""
    source = inspect.getsource(agent_module)
    assert "OneLLMEmbeddingAdapter(" in source, (
        "agent.py must build the knowledge embedding function from "
        "OneLLMEmbeddingAdapter (mirroring SOP search) so it routes "
        "through the shared embed() helper rather than the chat LLM."
    )
    # The adapter must reach the handler — the assignment to
    # ``embedding_fn`` is the canonical wire-up point.
    assert "OneLLMEmbeddingAdapter(" in source and "generate_embeddings" in source


def test_agent_falls_back_to_default_embedding_model():
    """When ``working_memory`` is unavailable or exposes no slug, the
    agent must fall back to ``DEFAULT_EMBEDDING_MODEL`` rather than
    raising or letting a ``None`` slug reach the adapter."""
    source = inspect.getsource(agent_module)
    assert "DEFAULT_EMBEDDING_MODEL" in source, (
        "agent.py must reference DEFAULT_EMBEDDING_MODEL as the fallback "
        "slug when working memory cannot supply one."
    )


def test_llm_generate_embeddings_default_is_local_not_openai():
    """``LLM.generate_embeddings``'s default model must NOT be OpenAI.

    Static source check: the ``kwargs.pop("model", ...)`` call that
    resolves the embedding model in batch mode must use
    ``DEFAULT_EMBEDDING_MODEL`` as its fallback. Any return to a
    hardcoded ``"openai/text-embedding-3-small"`` default would
    re-introduce the silent OpenAI coupling.
    """
    source = inspect.getsource(llm_module.LLM.generate_embeddings)
    # Defense-in-depth pattern: the local-default fallback must be there.
    assert "DEFAULT_EMBEDDING_MODEL" in source, (
        "LLM.generate_embeddings must default to DEFAULT_EMBEDDING_MODEL — "
        "found no reference to it."
    )
    # And the old hardcoded OpenAI default must not be the resolved
    # value of ``kwargs.pop``. The string may legitimately appear in
    # docstrings/comments, so we only forbid it as a kwargs.pop default.
    assert 'kwargs.pop("model", "openai/' not in source, (
        "LLM.generate_embeddings must not hardcode an OpenAI embedding "
        "model as the default — formations that only configured a "
        "non-OpenAI chat key would silently fail knowledge ingestion."
    )


def test_llm_embed_singular_default_is_local_not_openai():
    """Same invariant for the single-text ``LLM.embed`` path."""
    source = inspect.getsource(llm_module.LLM.embed)
    assert "DEFAULT_EMBEDDING_MODEL" in source, "LLM.embed must default to DEFAULT_EMBEDDING_MODEL."
    assert (
        'kwargs.pop("model", "openai/' not in source
    ), "LLM.embed must not hardcode an OpenAI embedding model as default."


def _resolve_slug_like_agent(overlord) -> str:
    """Mirror of the slug-resolution block in
    ``Agent._initialize_knowledge``. Kept here verbatim so the behavioral
    tests below catch any divergence at the resolution layer."""
    working_memory = getattr(overlord, "buffer_memory", None)
    embedding_slug = None
    if working_memory is not None:
        slug_candidate = getattr(working_memory, "embedding_model_name", None)
        if isinstance(slug_candidate, str) and slug_candidate:
            embedding_slug = slug_candidate
    if not embedding_slug:
        embedding_slug = DEFAULT_EMBEDDING_MODEL
    return embedding_slug


def test_knowledge_embedding_slug_resolution_uses_working_memory_slug():
    """Behavioral: when working memory exposes an explicit embedding
    slug, the agent must use that slug verbatim — not the default and
    not the chat-model identity. Pure unit (no Agent / no I/O)."""

    class FakeWorkingMemory:
        embedding_model_name = "openai/text-embedding-3-large"

    class FakeOverlord:
        buffer_memory = FakeWorkingMemory()

    assert _resolve_slug_like_agent(FakeOverlord()) == "openai/text-embedding-3-large"


def test_knowledge_embedding_slug_resolution_falls_back_to_default():
    """Behavioral: when working memory is missing or exposes a non-string
    / empty slug, the agent must fall back to ``DEFAULT_EMBEDDING_MODEL``
    so formations without an OpenAI key keep working out of the box."""

    class OverlordNoMemory:
        buffer_memory = None

    assert _resolve_slug_like_agent(OverlordNoMemory()) == DEFAULT_EMBEDDING_MODEL

    class EmptyWM:
        embedding_model_name = ""

    class OverlordEmptySlug:
        buffer_memory = EmptyWM()

    assert _resolve_slug_like_agent(OverlordEmptySlug()) == DEFAULT_EMBEDDING_MODEL

    class NonStringWM:
        embedding_model_name = 123  # malformed mock — must be ignored

    class OverlordBadSlug:
        buffer_memory = NonStringWM()

    assert _resolve_slug_like_agent(OverlordBadSlug()) == DEFAULT_EMBEDDING_MODEL
