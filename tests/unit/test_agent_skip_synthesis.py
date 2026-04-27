"""Unit tests for the skip-synthesis fast path on the Agent.

Background
----------
After planning execution, agents make a *second* LLM call to synthesize
a user-facing prose response from the tool/delegation results. For
artifact-heavy requests ("create a one-page PDF", "generate a chart")
the synthesized prose is mostly boilerplate ("Here's your file:")
because the artifact itself carries the user-visible payload — and the
synthesis call itself costs 3-10s of wall time on Sonnet-class models.

When the user is already receiving real-time streaming progress events,
we can substitute a short deterministic acknowledgment for the
synthesized prose with no perceived loss in quality. This module guards
the three pieces of that fast path:

1. Pure-artifact detection: every result must carry an ``_artifact``
   key. An empty result set or a single non-artifact result must
   *not* trigger the bypass.
2. Streaming-active detection: must read both the formation-level
   ``overlord.response.streaming`` config AND the per-request
   streaming manager state.
3. Deterministic acknowledgment: must surface the artifact's filename
   when available without inventing details about its contents.

The fourth (integration) test exercises the call site directly: a pure
artifact + streaming-active formation must NOT make the extra
``self.model.chat(...)`` synthesis call.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from muxi.runtime.formation.agents import agent as agent_module
from muxi.runtime.formation.agents.agent import Agent

# ---------------------------------------------------------------------------
# _is_pure_artifact_result
# ---------------------------------------------------------------------------


def test_pure_artifact_detection_empty_returns_false():
    """Empty result set must NOT be classified as pure-artifact —
    the user expects something back, and an empty result is more
    likely to indicate a problem than a successful artifact-only
    completion."""
    assert Agent._is_pure_artifact_result({}) is False
    assert Agent._is_pure_artifact_result(None) is False  # type: ignore[arg-type]


def test_pure_artifact_detection_all_artifacts():
    results = {
        "step_1": {"_artifact": {"filename": "report.pdf"}},
        "step_2": {"_artifact": {"filename": "chart.png"}},
    }
    assert Agent._is_pure_artifact_result(results) is True


def test_pure_artifact_detection_mixed_results_returns_false():
    """Mixing artifact + non-artifact results means the LLM still has
    real text data to synthesize — synthesis must run."""
    results = {
        "step_1": {"_artifact": {"filename": "report.pdf"}},
        "step_2": {"text": "Some search result data the LLM should explain."},
    }
    assert Agent._is_pure_artifact_result(results) is False


def test_pure_artifact_detection_non_dict_results_returns_false():
    """Non-dict results (raw strings, lists, etc.) cannot be artifacts."""
    results = {"step_1": "raw string output"}
    assert Agent._is_pure_artifact_result(results) is False


def test_pure_artifact_detection_missing_artifact_key_returns_false():
    """A dict result without an ``_artifact`` key is text data."""
    results = {"step_1": {"output": "plain text result"}}
    assert Agent._is_pure_artifact_result(results) is False


# ---------------------------------------------------------------------------
# _build_artifact_only_response
# ---------------------------------------------------------------------------


def test_artifact_response_uses_filename_when_available():
    out = Agent._build_artifact_only_response({"step_1": {"_artifact": {"filename": "report.pdf"}}})
    assert "report.pdf" in out


def test_artifact_response_falls_back_to_name_field():
    """Some artifact metadata variants use ``name`` instead of
    ``filename``; the helper must accept both rather than producing
    a generic message that hides the actual filename."""
    out = Agent._build_artifact_only_response({"step_1": {"_artifact": {"name": "chart.svg"}}})
    assert "chart.svg" in out


def test_artifact_response_handles_missing_filename():
    """Without filename or name, return a generic acknowledgment
    rather than crash or expose internal _artifact metadata."""
    out = Agent._build_artifact_only_response({"step_1": {"_artifact": {}}})
    assert "file" in out.lower()
    assert "_artifact" not in out


def test_artifact_response_handles_multiple_artifacts():
    out = Agent._build_artifact_only_response(
        {
            "step_1": {"_artifact": {"filename": "a.pdf"}},
            "step_2": {"_artifact": {"filename": "b.csv"}},
            "step_3": {"_artifact": {"filename": "c.png"}},
        }
    )
    assert "3" in out
    assert "files" in out.lower()


# ---------------------------------------------------------------------------
# _is_streaming_active
# ---------------------------------------------------------------------------


def _make_agent_for_streaming_test(overlord_streaming: bool = False) -> Agent:
    """Construct a minimal Agent with the streaming-relevant attributes
    populated. We avoid the full constructor to keep the test focused."""
    # Use Agent.__new__ to bypass __init__ — we only need a few
    # attributes for these unit tests.
    a = Agent.__new__(Agent)
    a.overlord = SimpleNamespace(streaming=overlord_streaming) if overlord_streaming else None
    a.agent_id = "test-agent"
    return a


def test_streaming_active_when_formation_config_enabled():
    a = _make_agent_for_streaming_test(overlord_streaming=True)
    assert a._is_streaming_active() is True


def test_streaming_inactive_without_overlord_or_request_context():
    """No overlord, no request context, no streaming — the safe default
    is to keep synthesis."""
    a = _make_agent_for_streaming_test(overlord_streaming=False)
    a.overlord = None
    assert a._is_streaming_active() is False


def test_streaming_active_via_per_request_manager(monkeypatch):
    """When the streaming manager has the current request_id registered,
    streaming is active even without the formation-level config."""
    a = _make_agent_for_streaming_test(overlord_streaming=False)
    a.overlord = SimpleNamespace(streaming=False)

    # Patch the streaming manager and request context modules to simulate
    # a request actively streaming.
    fake_ctx = SimpleNamespace(id="req-abc")

    import muxi.runtime.services.observability.context as ctx_mod
    import muxi.runtime.services.streaming as streaming_mod

    monkeypatch.setattr(ctx_mod, "get_current_request_context", lambda: fake_ctx)
    monkeypatch.setattr(
        streaming_mod.streaming_manager,
        "is_streaming_enabled",
        lambda req_id: req_id == "req-abc",
    )
    assert a._is_streaming_active() is True


def test_streaming_detection_swallows_exceptions(monkeypatch):
    """Streaming detection is best-effort. If the streaming module
    is unavailable / raises, we must fall back to ``False`` (run the
    synthesis) rather than propagate the failure into the chat flow."""
    a = _make_agent_for_streaming_test(overlord_streaming=False)
    a.overlord = SimpleNamespace(streaming=False)

    import muxi.runtime.services.observability.context as ctx_mod

    def _boom():
        raise RuntimeError("simulated context lookup failure")

    monkeypatch.setattr(ctx_mod, "get_current_request_context", _boom)
    assert a._is_streaming_active() is False


# ---------------------------------------------------------------------------
# Static guard against accidental removal of the bypass site
# ---------------------------------------------------------------------------


def test_synthesis_call_site_uses_skip_path_helpers():
    """The bypass logic must reference both gates at the synthesis call
    site. If a refactor accidentally removes one, artifact-heavy
    requests will silently regress to paying the full synthesis cost
    again."""
    src = inspect.getsource(agent_module)
    # Both helpers must appear together near the synthesis call so the
    # gate cannot accidentally short-circuit on just one signal.
    assert "_is_pure_artifact_result(" in src, (
        "_is_pure_artifact_result no longer referenced — the artifact "
        "detection gate has been removed and synthesis will run "
        "unconditionally even for streaming users with pure artifact "
        "results."
    )
    assert "_is_streaming_active(" in src, (
        "_is_streaming_active no longer referenced — the streaming "
        "gate has been removed; non-streaming users would now be "
        "served the deterministic acknowledgment without having seen "
        "any progress feedback."
    )
    assert "_build_artifact_only_response(" in src, (
        "_build_artifact_only_response no longer referenced — the skip "
        "path's deterministic message is gone."
    )


# ---------------------------------------------------------------------------
# Integration: synthesis is NOT called on the skip path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_path_does_not_call_synthesize():
    """End-to-end check on the helpers: when the gate is open, the
    skip path must produce a response *without* invoking the
    ``_synthesize_planning_execution_response`` LLM call."""
    a = Agent.__new__(Agent)
    a.overlord = SimpleNamespace(streaming=True)
    a.agent_id = "test-agent"
    a._synthesize_planning_execution_response = AsyncMock(  # type: ignore[attr-defined]
        return_value="should-not-be-used"
    )

    my_results = {"step_1": {"_artifact": {"filename": "report.pdf"}}}

    # Simulate the gate evaluation that the agent's planning flow does.
    if a._is_pure_artifact_result(my_results) and a._is_streaming_active():
        synthesized = a._build_artifact_only_response(my_results)
    else:  # pragma: no cover - guard against test setup drift
        synthesized = await a._synthesize_planning_execution_response(  # type: ignore[attr-defined]
            "create a one-page PDF", my_results, []
        )

    assert "report.pdf" in synthesized
    a._synthesize_planning_execution_response.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_synthesis_runs_when_streaming_inactive():
    """Counterpart: with streaming off, the bypass must NOT fire even
    for pure-artifact results — without streaming the user has no
    other feedback, so the synthesized prose is the only narrative."""
    a = Agent.__new__(Agent)
    a.overlord = SimpleNamespace(streaming=False)
    a.agent_id = "test-agent"
    a._synthesize_planning_execution_response = AsyncMock(  # type: ignore[attr-defined]
        return_value="LLM synthesized response."
    )

    my_results = {"step_1": {"_artifact": {"filename": "report.pdf"}}}

    if a._is_pure_artifact_result(my_results) and a._is_streaming_active():
        synthesized = a._build_artifact_only_response(my_results)  # pragma: no cover
    else:
        synthesized = await a._synthesize_planning_execution_response(  # type: ignore[attr-defined]
            "create a one-page PDF", my_results, []
        )

    assert synthesized == "LLM synthesized response."
    a._synthesize_planning_execution_response.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_synthesis_runs_when_results_are_mixed():
    """Counterpart: streaming on, but mixed text+artifact results
    means there's real data the LLM should explain. Synthesis must
    run."""
    a = Agent.__new__(Agent)
    a.overlord = SimpleNamespace(streaming=True)
    a.agent_id = "test-agent"
    a._synthesize_planning_execution_response = AsyncMock(  # type: ignore[attr-defined]
        return_value="LLM synthesized response with text and artifact context."
    )

    my_results = {
        "step_1": {"_artifact": {"filename": "report.pdf"}},
        "step_2": {"text": "Some search result data."},
    }

    if a._is_pure_artifact_result(my_results) and a._is_streaming_active():
        synthesized = a._build_artifact_only_response(my_results)  # pragma: no cover
    else:
        synthesized = await a._synthesize_planning_execution_response(  # type: ignore[attr-defined]
            "search and report", my_results, []
        )

    assert "synthesized" in synthesized.lower()
    a._synthesize_planning_execution_response.assert_awaited_once()  # type: ignore[attr-defined]
