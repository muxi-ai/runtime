"""
Regression tests for the A2A delegation credential-clarification path.

Background
----------
When a tool invoked by an A2A-delegated agent raises a credential error,
two long-dead branches used to break the clarification flow (both only
observable in e2e logs because the direct chat path takes a different
route):

1. ``Overlord.handle_missing_credential`` imported
   ``..clarification.credential_handler`` — a module removed when the
   unified clarification system landed — so every call raised
   ``ModuleNotFoundError`` ("No module named
   'muxi.runtime.formation.clarification'"), was swallowed by the broad
   except, and returned ``None`` instead of a ClarificationRequest.

2. ``Agent.process_message`` referenced ``AmbiguousCredentialError`` in
   its tool-loop exception handler while other branches of the same
   function imported the name locally. The local imports made the name
   function-local everywhere, so the tool-loop branch raised
   ``UnboundLocalError`` ("cannot access local variable
   'AmbiguousCredentialError'") whenever it ran before a branch that
   performed the import — which is exactly what the A2A path does.

These tests pin both fixes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.datatypes.clarification import ClarificationRequest, ClarificationResponse
from muxi.runtime.formation.agents.agent import Agent
from muxi.runtime.formation.credentials import AmbiguousCredentialError, MissingCredentialError
from muxi.runtime.formation.overlord.clarification import (
    build_credential_clarification_request,
    parse_credential_clarification_response,
)
from muxi.runtime.formation.overlord.overlord import Overlord


def _make_overlord_stub() -> Overlord:
    """Minimally-wired Overlord exposing what handle_missing_credential touches."""
    overlord = Overlord.__new__(Overlord)
    overlord.clarification_config = SimpleNamespace(enabled=True)
    overlord._set_pending_clarification = MagicMock()
    return overlord


def _make_agent_stub(overlord: Overlord) -> Agent:
    """Minimally-wired Agent exposing what invoke_tool touches on the MCP path."""
    agent = object.__new__(Agent)
    agent.agent_id = "a2a-delegate"
    agent.overlord = overlord
    agent.request_timeout = None
    agent._messages = []
    agent._mcp_service = MagicMock()
    return agent


# ---------------------------------------------------------------------------
# Bug 1: phantom import in Overlord.handle_missing_credential
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_missing_credential_returns_clarification_request():
    """Must build a real ClarificationRequest — not swallow a ModuleNotFoundError
    from the long-removed formation.clarification package and return None."""
    overlord = _make_overlord_stub()

    request = await overlord.handle_missing_credential(
        service="github",
        user_id="user-1",
        context={"agent_id": "a2a-delegate", "tool_name": "github_create_issue"},
    )

    assert isinstance(request, ClarificationRequest)
    assert request.user_id == "user-1"
    assert request.tool_name == "github_create_issue"
    assert "github_credential" in request.missing_info
    assert request.clarification_plan, "expected at least one clarification question"
    assert "GitHub" in request.clarification_plan[0].question_text


@pytest.mark.asyncio
async def test_handle_missing_credential_stores_pending_for_session():
    overlord = _make_overlord_stub()

    request = await overlord.handle_missing_credential(
        service="slack",
        user_id="user-2",
        context={"session_id": "sess-42", "request_id": "req-9"},
    )

    assert isinstance(request, ClarificationRequest)
    overlord._set_pending_clarification.assert_called_once()
    session_id, pending = overlord._set_pending_clarification.call_args.args
    assert session_id == "sess-42"
    assert pending["type"] == "credential"
    assert pending["service"] == "slack"
    assert pending["user_id"] == "user-2"
    assert pending["request"] is request
    assert pending["request_id"] == "req-9"


@pytest.mark.asyncio
async def test_handle_missing_credential_returns_none_when_clarification_disabled():
    overlord = _make_overlord_stub()
    overlord.clarification_config = SimpleNamespace(enabled=False)

    request = await overlord.handle_missing_credential(service="github", user_id="user-1")

    assert request is None
    overlord._set_pending_clarification.assert_not_called()


@pytest.mark.asyncio
async def test_invoke_tool_missing_credential_triggers_overlord_handler_and_reraises():
    """The A2A seam: a delegated agent's tool raises MissingCredentialError,
    the agent must run the overlord's (now working) clarification handler and
    re-raise so the error bubbles up for the clarification flow."""
    overlord = _make_overlord_stub()
    agent = _make_agent_stub(overlord)
    agent._mcp_service.invoke_tool = AsyncMock(
        side_effect=MissingCredentialError(service="github", user_id="user-1")
    )

    handler_results = []
    real_handler = overlord.handle_missing_credential

    async def recording_handler(**kwargs):
        result = await real_handler(**kwargs)
        handler_results.append(result)
        return result

    overlord.handle_missing_credential = recording_handler

    with pytest.raises(MissingCredentialError):
        await agent.invoke_tool(
            tool_name="github_create_issue",
            parameters={"title": "hi"},
            server_id="github",
            user_id="user-1",
        )

    assert len(handler_results) == 1
    assert isinstance(handler_results[0], ClarificationRequest)


# ---------------------------------------------------------------------------
# Bug 2: AmbiguousCredentialError shadowed into a local in process_message
# ---------------------------------------------------------------------------


def test_credential_error_names_are_not_locals_in_process_message():
    """Local ``from ..credentials import ...`` statements anywhere inside
    process_message make the names function-local for the WHOLE function,
    so branches that run before the import raise UnboundLocalError. The
    names must resolve at module level instead."""
    import muxi.runtime.formation.agents.agent as agent_module

    code = Agent.process_message.__code__
    assert "AmbiguousCredentialError" not in code.co_varnames
    assert "MissingCredentialError" not in code.co_varnames
    assert agent_module.AmbiguousCredentialError is AmbiguousCredentialError
    assert agent_module.MissingCredentialError is MissingCredentialError


@pytest.mark.asyncio
async def test_invoke_tool_reraises_ambiguous_credential_error():
    """Ambiguous-credential selection must bubble up (it drives the account
    picker), not degrade into a generic tool failure."""
    overlord = _make_overlord_stub()
    agent = _make_agent_stub(overlord)
    error = AmbiguousCredentialError(
        service="github",
        user_id="user-1",
        available_credentials=["work", "personal"],
    )
    agent._mcp_service.invoke_tool = AsyncMock(side_effect=error)

    with pytest.raises(AmbiguousCredentialError):
        await agent.invoke_tool(
            tool_name="github_create_issue",
            parameters={"title": "hi"},
            server_id="github",
            user_id="user-1",
        )


# ---------------------------------------------------------------------------
# Helper coverage: build/parse round trip
# ---------------------------------------------------------------------------


def test_build_credential_clarification_request_content():
    request = build_credential_clarification_request(
        service="github",
        user_id="user-1",
        context={"tool_name": "github_create_issue"},
    )

    assert request.missing_info == ["github_credential"]
    question = request.clarification_plan[0]
    assert question.question_id == "credential_github"
    assert "github_create_issue" in question.question_text
    assert request.context["reason"] == "missing_credential"
    assert request.context["service"] == "github"


def test_parse_credential_clarification_response_structured_answer():
    response = ClarificationResponse(answers=[{"id": "credential_github", "answer": "ghp_abc123"}])

    assert parse_credential_clarification_response(response, "github") == {"token": "ghp_abc123"}


def test_parse_credential_clarification_response_raw_text_fallback():
    response = ClarificationResponse(answers=[], raw_response="sk-openai-key")

    assert parse_credential_clarification_response(response, "openai") == {
        "api_key": "sk-openai-key"
    }


def test_parse_credential_clarification_response_empty_returns_none():
    response = ClarificationResponse(answers=[], raw_response="   ")

    assert parse_credential_clarification_response(response, "github") is None


def test_parse_credential_field_name_ignores_incidental_substrings():
    """Only exact service names or explicit suffixes may pick "api_key";
    incidental substrings ("monkey" contains "key") must not."""
    monkey = ClarificationResponse(answers=[], raw_response="tok-123456")
    assert parse_credential_clarification_response(monkey, "monkey") == {"token": "tok-123456"}

    capital = ClarificationResponse(answers=[], raw_response="cap-123456")
    assert parse_credential_clarification_response(capital, "capital-api") == {
        "api_key": "cap-123456"
    }
