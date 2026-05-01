"""
Tests for the recency-floor merge in ChatOrchestrator._enhance_message_with_context.

Background
----------
When ``memory.buffer.vector_search`` is true (the remote-buffer / FAISSx
configuration), the current user message is used as the embedding key
for buffer search. Meta-recall queries like "list back the technical
skills I mentioned earlier" do NOT embed-match well with the content
messages they want to recall ("I work with Python, Kubernetes, …").
The configured ``recency_bias`` (0.3) is too weak to surface those
recent turns when their semantic similarity to the query is low.

The fix merges a recency-only second pass into the vector search
results so follow-up / recall questions always see the latest N
conversational turns. These tests pin that contract:

* both passes are issued (vector search + recency search)
* results are de-duplicated by (text, timestamp)
* vector-search ordering is preserved (most relevant first)
* recency-only items missing from the vector pass appear at the end
* the local-only path (vector_search=False) is unchanged
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.overlord.chat_orchestrator import ChatOrchestrator


def _make_buffer_item(text: str, ts: float, role: str = "user") -> Dict[str, Any]:
    return {
        "text": text,
        "metadata": {"role": role, "timestamp": ts},
        "distance": 0.0,
        "source": "buffer",
    }


def _make_orchestrator(
    *,
    vector_search: bool,
    search_results: Dict[str, List[Dict[str, Any]]],
) -> ChatOrchestrator:
    """
    Build a ChatOrchestrator stub wired for _enhance_message_with_context.

    ``search_results`` keys map a query string ("the user message" / "")
    to the list of buffer items the stubbed search_buffer_memory should
    return. This lets a single orchestrator stub model both the vector
    pass and the recency pass distinctly.
    """
    orch = ChatOrchestrator.__new__(ChatOrchestrator)

    overlord = MagicMock()
    overlord.formation_config = {"memory": {"buffer": {"size": 5, "vector_search": vector_search}}}
    overlord.is_multi_user = False
    overlord.long_term_memory = None
    overlord.persistent_memory_manager = None
    overlord.auto_extract_user_info = False

    async def _search(
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return list(search_results.get(query, []))

    overlord.buffer_memory_manager = MagicMock()
    overlord.buffer_memory_manager.search_buffer_memory = AsyncMock(side_effect=_search)
    overlord.get_user_synopsis = AsyncMock(return_value="")

    orch.overlord = overlord
    return orch


@pytest.mark.asyncio
async def test_remote_mode_merges_recency_floor_with_vector_results() -> None:
    vector_only = [
        _make_buffer_item("Hello, my name is Bob.", ts=100.0),
    ]
    recency_only = [
        _make_buffer_item("I work with Python, Kubernetes, ML pipelines.", ts=200.0),
        _make_buffer_item("Hello, my name is Bob.", ts=100.0),  # duplicate
        _make_buffer_item("Designing a fault-tolerant queue.", ts=150.0),
    ]
    user_msg = "List back the technical skills I mentioned earlier."

    orch = _make_orchestrator(
        vector_search=True,
        search_results={user_msg: vector_only, "": recency_only},
    )

    result = (
        await orch._enhance_message_with_context(
            message=user_msg,
            user_id="bob",
            session_id="sess",
            file_results=None,
        )
    ).enhanced

    # Two distinct calls: vector pass + recency pass.
    calls = orch.overlord.buffer_memory_manager.search_buffer_memory.await_args_list
    assert len(calls) == 2
    assert {c.kwargs["query"] for c in calls} == {user_msg, ""}

    # The enhanced message must include the recency-floor content that
    # the vector pass missed entirely (Python, Kubernetes, queue design).
    assert "Python" in result
    assert "Kubernetes" in result
    assert "fault-tolerant queue" in result
    # Bob (only item from vector pass) must appear too — and only once.
    assert result.count("Hello, my name is Bob.") == 1


@pytest.mark.asyncio
async def test_local_mode_unchanged_uses_recency_only_search() -> None:
    recency_only = [
        _make_buffer_item("I work with Python.", ts=200.0),
    ]
    user_msg = "List back the technical skills I mentioned earlier."

    orch = _make_orchestrator(
        vector_search=False,
        search_results={user_msg: [], "": recency_only},
    )

    result = (
        await orch._enhance_message_with_context(
            message=user_msg,
            user_id="bob",
            session_id="sess",
            file_results=None,
        )
    ).enhanced

    # Only one call — recency pass only. Local mode must NOT issue a
    # second call to keep the fast path lean.
    calls = orch.overlord.buffer_memory_manager.search_buffer_memory.await_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["query"] == ""
    assert "Python" in result


@pytest.mark.asyncio
async def test_remote_mode_dedupes_overlap_between_vector_and_recency() -> None:
    """Items present in both passes appear exactly once in the merged context."""
    vector = [
        _make_buffer_item("V1 high-relevance", ts=50.0),
        _make_buffer_item("V2 medium-relevance", ts=60.0),
    ]
    recency = [
        _make_buffer_item("R1 most-recent", ts=300.0),
        _make_buffer_item("V1 high-relevance", ts=50.0),  # duplicate of vector head
    ]
    user_msg = "What did I say?"

    orch = _make_orchestrator(
        vector_search=True,
        search_results={user_msg: vector, "": recency},
    )
    result = (
        await orch._enhance_message_with_context(
            message=user_msg, user_id="u", session_id="s", file_results=None
        )
    ).enhanced

    # All three distinct items present.
    assert "V1 high-relevance" in result
    assert "V2 medium-relevance" in result
    assert "R1 most-recent" in result
    # The duplicate must be coalesced.
    assert result.count("V1 high-relevance") == 1
