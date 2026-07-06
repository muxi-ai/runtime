"""Regression tests for session scoping in knowledge search.

Knowledge chunks are stored in working memory without a session_id
(knowledge is agent-scoped, not session-scoped), but the handler used to
forward the caller's session_id into the vector search. Working memory
applies session_id as a hard filter, so every session-scoped knowledge
search silently returned zero results. These tests pin the contract:
the knowledge leg is never session-filtered, while the conversational
memory leg in search_unified keeps its session scoping.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.agents.knowledge.handler import (
    DOCUMENT_NAMESPACE,
    KnowledgeHandler,
)

DIM = 8


def _make_working_memory_mock() -> MagicMock:
    wm = MagicMock()
    wm.add_with_embedding = AsyncMock()
    wm.search = AsyncMock(
        return_value=[
            {
                "text": "MUXI offers three pricing plans.",
                "score": 0.92,
                "metadata": {"document_id": "doc-1", "source": "pricing.md"},
            }
        ]
    )
    wm.get_items_by_metadata = MagicMock(return_value=[])
    wm.remove_by_metadata = MagicMock(return_value=0)
    return wm


def _make_handler() -> KnowledgeHandler:
    handler = KnowledgeHandler(
        agent_id_or_sources="test-agent",
        formation_id="test-formation",
        embedding_dimension=DIM,
        working_memory=_make_working_memory_mock(),
        auto_inject_knowledge=False,
    )
    handler._generate_embeddings_fn = AsyncMock(return_value=[[0.1] * DIM])
    return handler


@pytest.mark.asyncio
async def test_knowledge_search_is_not_session_filtered():
    handler = _make_handler()

    results = await handler.search(query="What pricing plans does MUXI offer?", top_k=3)

    assert len(results) == 1
    search_kwargs = handler.working_memory.search.await_args.kwargs
    assert search_kwargs["namespace"] == DOCUMENT_NAMESPACE
    assert "session_id" not in search_kwargs


@pytest.mark.asyncio
async def test_unified_search_scopes_only_the_memory_leg():
    handler = _make_handler()

    results = await handler.search_unified(
        query="What pricing plans does MUXI offer?",
        top_k=3,
        session_id="session-123",
    )

    calls = handler.working_memory.search.await_args_list
    knowledge_calls = [c for c in calls if c.kwargs.get("namespace") == DOCUMENT_NAMESPACE]
    memory_calls = [c for c in calls if c.kwargs.get("namespace") != DOCUMENT_NAMESPACE]
    assert len(knowledge_calls) == 1
    assert len(memory_calls) == 1

    # The regression: a session-scoped call must still surface knowledge
    assert "session_id" not in knowledge_calls[0].kwargs
    assert results["knowledge"], "session-scoped unified search returned no knowledge results"

    # Conversational memory stays session-scoped
    assert memory_calls[0].kwargs["session_id"] == "session-123"
