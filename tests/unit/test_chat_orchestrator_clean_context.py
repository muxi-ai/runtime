"""
Tests for the clean-chat-context bundle path.

Background
----------
``ChatOrchestrator._enhance_message_with_context`` produces a
marker-formatted blob (``=== CURRENT REQUEST ===`` / ``=== USER PROFILE
===`` / ``=== CONVERSATION CONTEXT ===``) that is consumed by the
analyzer pipeline (clarification, planning, intent extraction). When
the same blob is replayed across multi-turn chat as the agent's user
turns, models with strong honesty training (Sonnet 4.6) read each
turn's ``=== CURRENT REQUEST ===`` wrapper as an isolated query and
treat the surrounding ``=== CONVERSATION CONTEXT ===`` flat blob as
metadata-not-history, which broke pure-chat behavior on simple
follow-up questions ("What about the language thing though?").

The new ``_build_clean_chat_context`` produces a structured bundle
that the agent assembles into a chat-API-shape transcript:
``[system_with_addendum, user_1, asst_1, ..., current_user]``. Buffer
memory stores ORIGINAL un-enhanced text per turn, so we can replay
those rows directly as proper role tags without parsing markers.

These tests pin:

* the bundle shape (5 expected keys with the right contents)
* buffer turns are returned in chronological order (oldest first)
* the current user message is filtered out of the buffer turns when
  buffer storage races ahead of the orchestrator
* non-user / non-assistant rows are dropped
* the agent-side ``_assemble_messages_from_clean_context`` produces
  the expected chat-API shape
* user profile + memories + file results land in the system addendum
  (NOT in the user turn)
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.overlord.chat_orchestrator import ChatOrchestrator


def _row(text: str, ts: float, role: str = "user") -> Dict[str, Any]:
    return {
        "text": text,
        "metadata": {"role": role, "timestamp": ts},
        "distance": 0.0,
        "source": "buffer",
    }


def _make_orchestrator(
    *,
    buffer_rows: List[Dict[str, Any]],
    user_synopsis: str = "",
    long_term_memories_results: Optional[List[Dict[str, Any]]] = None,
) -> ChatOrchestrator:
    orch = ChatOrchestrator.__new__(ChatOrchestrator)

    overlord = MagicMock()
    overlord.formation_config = {
        "memory": {
            "buffer": {"size": 10, "vector_search": False},
            "long_term": {"collections": ["conversations"]},
        }
    }
    overlord.is_multi_user = False
    overlord.auto_extract_user_info = False

    async def _search_buffer(
        query: str,
        k: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return list(buffer_rows)

    overlord.buffer_memory_manager = MagicMock()
    overlord.buffer_memory_manager.search_buffer_memory = AsyncMock(side_effect=_search_buffer)

    if user_synopsis:
        overlord.is_multi_user = True
        overlord.get_user_synopsis = AsyncMock(return_value=user_synopsis)
    else:
        overlord.get_user_synopsis = AsyncMock(return_value="")

    if long_term_memories_results is not None:
        overlord.long_term_memory = MagicMock()
        overlord.long_term_memory.search = AsyncMock(return_value=long_term_memories_results)
    else:
        overlord.long_term_memory = None

    orch.overlord = overlord
    return orch


@pytest.mark.asyncio
async def test_bundle_has_expected_keys_and_shape() -> None:
    rows = [
        _row("Hello, I'm Bob.", ts=100.0, role="user"),
        _row("Hi Bob! How can I help?", ts=110.0, role="assistant"),
    ]
    orch = _make_orchestrator(buffer_rows=rows)

    bundle = await orch._build_clean_chat_context(
        current_user_message="What did we talk about?",
        user_id="bob",
        session_id="s1",
    )

    assert set(bundle.keys()) == {
        "buffer_turns",
        "current_user_message",
        "user_profile_text",
        "long_term_memories",
        "file_results",
    }
    assert bundle["current_user_message"] == "What did we talk about?"
    assert bundle["file_results"] == ""


@pytest.mark.asyncio
async def test_buffer_turns_are_returned_chronologically() -> None:
    """search_buffer_memory returns most-recent-first; bundle reverses to chronological."""
    rows = [
        # Most-recent-first as stored:
        _row("Asst response 2", ts=300.0, role="assistant"),
        _row("User msg 2", ts=290.0, role="user"),
        _row("Asst response 1", ts=200.0, role="assistant"),
        _row("User msg 1", ts=150.0, role="user"),
    ]
    orch = _make_orchestrator(buffer_rows=rows)

    bundle = await orch._build_clean_chat_context(
        current_user_message="next message",
        user_id="bob",
        session_id="s1",
    )

    turns = bundle["buffer_turns"]
    assert [t["content"] for t in turns] == [
        "User msg 1",
        "Asst response 1",
        "User msg 2",
        "Asst response 2",
    ]
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]


@pytest.mark.asyncio
async def test_current_user_message_filtered_from_buffer() -> None:
    """The current turn may have raced into the buffer ahead of us; don't double-inject."""
    current = "What about the language thing?"
    rows = [
        # The current message stored ahead of us (race):
        _row(current, ts=400.0, role="user"),
        # Plus older history:
        _row("Lisbon is a solid choice.", ts=300.0, role="assistant"),
        _row("Walkable, not too touristy. Lisbon?", ts=290.0, role="user"),
    ]
    orch = _make_orchestrator(buffer_rows=rows)

    bundle = await orch._build_clean_chat_context(
        current_user_message=current,
        user_id="bob",
        session_id="s1",
    )

    turns = bundle["buffer_turns"]
    contents = [t["content"] for t in turns]
    # The current message must NOT appear in buffer turns.
    assert current not in contents
    # Older history is preserved.
    assert "Lisbon is a solid choice." in contents
    assert "Walkable, not too touristy. Lisbon?" in contents


@pytest.mark.asyncio
async def test_non_user_assistant_rows_are_dropped() -> None:
    """Buffer can contain system-emitted entries; only user/assistant turns make it in.

    ``search_buffer_memory`` returns most-recent-first; mirror that ordering
    in the stub so the orchestrator's reversal lands on chronological output.
    """
    rows = [
        _row("assistant said this", ts=130.0, role="assistant"),
        _row("workflow checkpoint", ts=120.0, role="tool"),
        _row("system ack", ts=110.0, role="system"),
        _row("user said this", ts=100.0, role="user"),
    ]
    orch = _make_orchestrator(buffer_rows=rows)

    bundle = await orch._build_clean_chat_context(
        current_user_message="next",
        user_id="bob",
        session_id="s1",
    )
    turns = bundle["buffer_turns"]
    assert [t["role"] for t in turns] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_empty_text_rows_are_dropped() -> None:
    """Most-recent-first input; orchestrator reverses to chronological."""
    rows = [
        {"metadata": {"role": "user", "timestamp": 120.0}},  # missing text key entirely
        {"text": "", "metadata": {"role": "assistant", "timestamp": 110.0}},
        _row("real message", ts=100.0, role="user"),
    ]
    orch = _make_orchestrator(buffer_rows=rows)

    bundle = await orch._build_clean_chat_context(
        current_user_message="next",
        user_id="bob",
        session_id="s1",
    )
    assert [t["content"] for t in bundle["buffer_turns"]] == ["real message"]


@pytest.mark.asyncio
async def test_user_profile_and_memories_are_returned_in_bundle() -> None:
    rows = [_row("hi", ts=100.0, role="user")]
    orch = _make_orchestrator(
        buffer_rows=rows,
        user_synopsis="Bob is a Python engineer based in Lisbon.",
        long_term_memories_results=[
            {"text": "Bob prefers tea over coffee."},
            {"text": "Bob is allergic to shellfish."},
        ],
    )

    bundle = await orch._build_clean_chat_context(
        current_user_message="recommend a restaurant",
        user_id="bob",
        session_id="s1",
    )

    assert "Bob is a Python engineer" in bundle["user_profile_text"]
    assert "tea over coffee" in bundle["long_term_memories"]
    assert "shellfish" in bundle["long_term_memories"]


@pytest.mark.asyncio
async def test_file_results_are_carried_through() -> None:
    rows = [_row("hi", ts=100.0, role="user")]
    orch = _make_orchestrator(buffer_rows=rows)

    bundle = await orch._build_clean_chat_context(
        current_user_message="summarize the doc",
        user_id="bob",
        session_id="s1",
        file_results="Document title: Q1 financials. Summary: revenue up 12%.",
    )
    assert "Q1 financials" in bundle["file_results"]


@pytest.mark.asyncio
async def test_no_buffer_returns_empty_turns_not_error() -> None:
    """No buffer manager configured (e.g., framework mode without memory) still produces a valid bundle."""
    orch = ChatOrchestrator.__new__(ChatOrchestrator)
    overlord = MagicMock()
    overlord.formation_config = {"memory": {"buffer": {"size": 10}}}
    overlord.is_multi_user = False
    overlord.long_term_memory = None
    overlord.buffer_memory_manager = None
    overlord.get_user_synopsis = AsyncMock(return_value="")
    orch.overlord = overlord

    bundle = await orch._build_clean_chat_context(
        current_user_message="hello",
        user_id="0",
        session_id=None,
    )
    assert bundle["buffer_turns"] == []
    assert bundle["current_user_message"] == "hello"


# ---------- Agent-side assembly tests ----------


class _AgentLite:
    """Minimal stand-in for Agent that only implements the assembly helper.

    The full Agent class loads the OneLLM stack at import time, which is
    expensive and not relevant to testing pure assembly logic. We
    bind-import the static helper from the real class to keep the
    contract honest.
    """

    def __init__(self) -> None:
        from muxi.runtime.formation.agents.agent import Agent

        self._fn = Agent._assemble_messages_from_clean_context

    def assemble(self, bundle: Dict[str, Any], system_message_base: str) -> List[Dict[str, Any]]:
        # Replicate `self.` calling convention without instantiating Agent
        return self._fn(self, bundle, system_message_base)


def test_assembly_produces_chat_api_shape() -> None:
    bundle = {
        "buffer_turns": [
            {"role": "user", "content": "Hey"},
            {"role": "assistant", "content": "Hi! How can I help?"},
            {"role": "user", "content": "Tell me about Lisbon."},
            {"role": "assistant", "content": "Lisbon is..."},
        ],
        "current_user_message": "What about the language?",
        "user_profile_text": "",
        "long_term_memories": "",
        "file_results": "",
    }
    msgs = _AgentLite().assemble(bundle, "You are a helpful assistant.")
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are a helpful assistant."
    assert [m["role"] for m in msgs[1:]] == ["user", "assistant", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "What about the language?"


def test_addendum_lands_in_system_not_in_user_turn() -> None:
    bundle = {
        "buffer_turns": [],
        "current_user_message": "What's up?",
        "user_profile_text": "Bob, Lisbon-based.",
        "long_term_memories": "- Bob prefers tea.",
        "file_results": "",
    }
    msgs = _AgentLite().assemble(bundle, "You are a thoughtful chat partner.")

    sys_content = msgs[0]["content"]
    assert "You are a thoughtful chat partner." in sys_content
    assert "=== USER PROFILE ===" in sys_content
    assert "Bob, Lisbon-based." in sys_content
    assert "=== RELEVANT MEMORIES ===" in sys_content
    assert "Bob prefers tea." in sys_content

    # The user message stays clean — no markers, no profile, no memories.
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "What's up?"
    assert "=== USER PROFILE ===" not in msgs[-1]["content"]
    assert "=== RELEVANT MEMORIES ===" not in msgs[-1]["content"]


def test_assembly_with_no_addendum_uses_bare_system_message() -> None:
    bundle = {
        "buffer_turns": [],
        "current_user_message": "Hello",
        "user_profile_text": "",
        "long_term_memories": "",
        "file_results": "",
    }
    msgs = _AgentLite().assemble(bundle, "You are a helpful assistant.")
    # No addendum sections whatsoever.
    assert msgs[0]["content"] == "You are a helpful assistant."
    assert "===" not in msgs[0]["content"]


def test_assembly_skips_invalid_buffer_entries() -> None:
    bundle = {
        "buffer_turns": [
            {"role": "user", "content": "good"},
            {"role": "system", "content": "bogus"},
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "good response"},
            {"role": None, "content": "headerless"},
        ],
        "current_user_message": "current",
        "user_profile_text": "",
        "long_term_memories": "",
        "file_results": "",
    }
    msgs = _AgentLite().assemble(bundle, "Sys.")
    contents = [m["content"] for m in msgs]
    assert contents == ["Sys.", "good", "good response", "current"]


def test_assembly_omits_current_user_message_when_empty() -> None:
    bundle = {
        "buffer_turns": [{"role": "user", "content": "earlier"}],
        "current_user_message": "",
        "user_profile_text": "",
        "long_term_memories": "",
        "file_results": "",
    }
    msgs = _AgentLite().assemble(bundle, "Sys.")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[-1]["content"] == "earlier"


def test_full_round_trip_no_double_history() -> None:
    """End-to-end assertion: history is in role turns ONLY, never duplicated in user msg."""
    bundle = {
        "buffer_turns": [
            {"role": "user", "content": "Tell me about Lisbon."},
            {"role": "assistant", "content": "Lisbon is great for solo travelers..."},
        ],
        "current_user_message": "What about the language?",
        "user_profile_text": "",
        "long_term_memories": "",
        "file_results": "",
    }
    msgs = _AgentLite().assemble(bundle, "Be friendly.")

    # No marker contamination of the current user turn:
    last_user = msgs[-1]
    assert last_user == {"role": "user", "content": "What about the language?"}
    # No flat-history blob inside ANY user message either:
    for m in msgs:
        if m["role"] == "user":
            assert "=== CONVERSATION CONTEXT" not in m["content"]
            assert "=== CURRENT REQUEST ===" not in m["content"]
