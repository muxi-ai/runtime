"""
Tests for concurrent profile-memory fetching in
ChatOrchestrator._enhance_message_with_context.

Background
----------
For profile-recall requests ("what do you know about me"), the
orchestrator fetches facts from ~5 profile collections via
``long_term_memory.list_memories``. These queries are independent, so
they are issued concurrently with ``asyncio.gather`` instead of being
awaited sequentially. These tests pin that contract:

* all profile collections are queried, and concurrently (not one at
  a time)
* results are processed in the original collection order regardless
  of completion order (gather preserves input ordering)
* a failure in any collection query keeps the previous all-or-nothing
  behavior: no profile facts, falling back to the standard long-term
  memory search
"""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.overlord.chat_orchestrator import ChatOrchestrator
from muxi.runtime.formation.prompts.loader import PromptLoader

PROFILE_COLLECTIONS = [
    "user_identity",
    "relationships",
    "work_projects",
    "preferences",
    "activities",
]


def _make_orchestrator(list_memories_side_effect) -> ChatOrchestrator:
    """Build a ChatOrchestrator stub wired for the profile-recall path."""
    orch = ChatOrchestrator.__new__(ChatOrchestrator)

    overlord = MagicMock()
    overlord.formation_config = {"memory": {"buffer": {"size": 5, "vector_search": False}}}
    overlord.is_multi_user = False
    overlord.auto_extract_user_info = False
    overlord.get_user_synopsis = AsyncMock(return_value="")

    overlord.long_term_memory = MagicMock(spec=["list_memories"])
    overlord.long_term_memory.list_memories = AsyncMock(side_effect=list_memories_side_effect)

    overlord.persistent_memory_manager = MagicMock()
    overlord.persistent_memory_manager.search_long_term_memory = AsyncMock(return_value=[])

    async def _search(
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return []

    overlord.buffer_memory_manager = MagicMock()
    overlord.buffer_memory_manager.search_buffer_memory = AsyncMock(side_effect=_search)

    orch.overlord = overlord
    return orch


@pytest.fixture(autouse=True)
def _stub_prompt_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    # The RELEVANT MEMORIES branch loads a protocol prompt; the loader is
    # not initialized in unit tests, so fall back to the inline protocol.
    monkeypatch.setattr(PromptLoader, "get", MagicMock(side_effect=KeyError("not loaded")))


@pytest.mark.asyncio
async def test_profile_collections_queried_concurrently_and_in_order() -> None:
    in_flight = 0
    max_in_flight = 0

    async def _list_memories(limit: int, collection: str, external_user_id: str):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        # Yield so all gathered coroutines can start before any finishes.
        # Reverse-staggered sleeps make later collections complete first,
        # proving result ordering comes from gather, not completion order.
        delay = (len(PROFILE_COLLECTIONS) - PROFILE_COLLECTIONS.index(collection)) * 0.01
        await asyncio.sleep(delay)
        in_flight -= 1
        return [{"text": f"{collection} fact"}]

    orch = _make_orchestrator(_list_memories)

    result = (
        await orch._enhance_message_with_context(
            message="What do you know about me?",
            user_id="bob",
            session_id="sess",
            file_results=None,
        )
    ).enhanced

    # All collections were queried.
    calls = orch.overlord.long_term_memory.list_memories.await_args_list
    assert {c.kwargs["collection"] for c in calls} == set(PROFILE_COLLECTIONS)
    assert all(c.kwargs["external_user_id"] == "bob" for c in calls)

    # Queries ran concurrently, not sequentially awaited one at a time.
    assert max_in_flight == len(PROFILE_COLLECTIONS)

    # Facts appear in collection order despite reverse completion order.
    assert "=== RELEVANT MEMORIES ===" in result
    positions = [result.index(f"- {collection} fact") for collection in PROFILE_COLLECTIONS]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_profile_fetch_failure_yields_no_facts_and_falls_back() -> None:
    async def _list_memories(limit: int, collection: str, external_user_id: str):
        if collection == "work_projects":
            raise RuntimeError("collection unavailable")
        return [{"text": f"{collection} fact"}]

    orch = _make_orchestrator(_list_memories)

    result = (
        await orch._enhance_message_with_context(
            message="What do you know about me?",
            user_id="bob",
            session_id="sess",
            file_results=None,
        )
    ).enhanced

    # All-or-nothing: no partial profile facts leak into the message.
    assert "user_identity fact" not in result
    assert "=== RELEVANT MEMORIES ===" not in result

    # With no synopsis and no profile facts, the orchestrator falls back
    # to the standard long-term memory search.
    orch.overlord.persistent_memory_manager.search_long_term_memory.assert_awaited_once()
