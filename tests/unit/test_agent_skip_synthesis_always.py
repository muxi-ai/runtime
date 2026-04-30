"""Tests for the always-skip agent synthesis path.

Background
----------
``Agent._synthesize_planning_execution_response`` historically issued a
second LLM call after planning execution to weave tool results and
delegated agent prose into a final user-facing reply. That extra
~4-second LLM call is now redundant: the overlord's ``_apply_persona``
pass always runs on the way back to the user and is responsible for
absorbing structured input.

This module locks in the new contract:

1. ``_synthesize_planning_execution_response`` no longer calls an LLM.
   It delegates to ``_build_raw_response`` (deterministic).
2. ``_build_raw_response`` renders ``my_results`` and
   ``planning_response_parts`` as a structured string the persona model
   can absorb directly.
3. The pure-artifact + streaming-active fast path (separate
   optimization, see ``test_agent_skip_synthesis.py``) still takes
   priority — its tests continue to pin that contract independently.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from muxi.runtime.formation.agents.agent import Agent

# ---------------------------------------------------------------------------
# _build_raw_response — pure string formatting, no LLM
# ---------------------------------------------------------------------------


def test_build_raw_response_renders_each_result_with_placeholder() -> None:
    """Each ``my_results`` entry renders under a ``### {placeholder}`` header."""
    my_results = {
        "{{TICKET}}": {"result": "Created issue MX-42 at https://linear.app/x/MX-42"},
        "{{LIST}}": {"result": "10 items found"},
    }
    rendered = Agent._build_raw_response(my_results, [])
    assert "### {{TICKET}}" in rendered
    assert "### {{LIST}}" in rendered
    assert "Created issue MX-42 at https://linear.app/x/MX-42" in rendered
    assert "10 items found" in rendered


def test_build_raw_response_renders_delegated_responses() -> None:
    """Delegated agent prose is appended under ``### Delegated Response N``."""
    my_results = {"{{TOOL}}": {"result": "Tool output X"}}
    delegated = [
        "Agent A: I checked the Linear board and found 3 P0 issues.",
        "Agent B: GitHub MCP returned 5 open PRs awaiting review.",
    ]
    rendered = Agent._build_raw_response(my_results, delegated)
    assert "### Delegated Response 1" in rendered
    assert "Agent A: I checked the Linear board and found 3 P0 issues." in rendered
    assert "### Delegated Response 2" in rendered
    assert "Agent B: GitHub MCP returned 5 open PRs awaiting review." in rendered


def test_build_raw_response_includes_artifact_filenames() -> None:
    """Results carrying ``_artifact`` metadata surface their filename."""
    my_results = {
        "{{REPORT}}": {
            "result": "Generated the quarterly report.",
            "_artifact": {"filename": "Q3-report.pdf"},
        }
    }
    rendered = Agent._build_raw_response(my_results, [])
    assert "Generated the quarterly report." in rendered
    assert "Files Attached: Q3-report.pdf" in rendered


def test_build_raw_response_dict_result_renders_key_value_lines() -> None:
    """A dict ``result`` payload renders as ``key: value`` lines."""
    my_results = {
        "{{ISSUE}}": {
            "result": {
                "issue_number": 50,
                "url": "https://github.com/muxi-ai/runtime/issues/50",
                "title": "Welcome to MUXI",
            }
        }
    }
    rendered = Agent._build_raw_response(my_results, [])
    assert "issue_number: 50" in rendered
    assert "url: https://github.com/muxi-ai/runtime/issues/50" in rendered
    assert "title: Welcome to MUXI" in rendered
    # No raw Python dict syntax in the surface.
    assert "{'issue_number'" not in rendered


def test_build_raw_response_string_result_extracted_from_output_field() -> None:
    """When dict has only ``output`` field, that's the body source."""
    my_results = {"{{STEP}}": {"output": "Result text"}}
    rendered = Agent._build_raw_response(my_results, [])
    assert "Result text" in rendered


def test_build_raw_response_non_dict_result_stringified() -> None:
    """Non-dict results (raw string, list, etc.) are stringified."""
    my_results = {"{{STEP}}": "raw string output"}
    rendered = Agent._build_raw_response(my_results, [])
    assert "raw string output" in rendered


def test_build_raw_response_empty_string_result_with_artifact_only_emits_filename() -> None:
    """Dict with empty-string ``result`` plus an artifact must NOT emit a
    blank line under the header.

    Regression guard: the previous ``elif raw_text is not None`` branch
    appended ``str("").strip()`` (an empty string) into the section,
    leaving the persona LLM with just ``### {placeholder}`` followed by
    blank space. The fix mirrors ``_render_task_body``'s ``if body:``
    guard so empty / whitespace-only ``result`` values are skipped, and
    the artifact filename becomes the section's only body line.
    """
    my_results = {
        "{{CHART}}": {
            "result": "",
            "_artifact": {"filename": "sales.png"},
        },
    }
    rendered = Agent._build_raw_response(my_results, [])
    assert "### {{CHART}}" in rendered
    assert "Files Attached: sales.png" in rendered
    # No blank-line body between header and Files Attached.
    chart_block = rendered.split("### {{CHART}}", 1)[1]
    non_empty_body_lines = [ln for ln in chart_block.splitlines() if ln.strip()]
    assert non_empty_body_lines == ["Files Attached: sales.png"]


def test_build_raw_response_whitespace_only_result_treated_as_empty() -> None:
    """``result`` that's pure whitespace must not surface as a section
    body (parallels the non-empty-string check on the first branch)."""
    my_results = {"{{STEP}}": {"result": "   \n  "}}
    rendered = Agent._build_raw_response(my_results, [])
    assert "### {{STEP}}" in rendered
    step_block = rendered.split("### {{STEP}}", 1)[1]
    assert step_block.strip() == ""


def test_build_raw_response_empty_inputs_returns_empty_string() -> None:
    """Empty results AND empty delegations return an empty string.

    The caller then falls through to other response-building branches
    (e.g., ``has_successful_delegation`` path or final fallback prose).
    """
    rendered = Agent._build_raw_response({}, [])
    assert rendered == ""


def test_build_raw_response_skips_empty_delegated_parts() -> None:
    """Empty/None delegated entries are skipped, and the surviving
    entries are numbered contiguously from 1.

    Numbering by the original list position would produce gaps
    (``["", None, "Real"]`` → "Delegated Response 3" with no 1 or 2),
    which carries no semantic meaning and just confuses the persona
    LLM. The renderer counts only emitted parts.
    """
    my_results = {"{{TOOL}}": {"result": "X"}}
    rendered = Agent._build_raw_response(my_results, ["", None, "Real response"])  # type: ignore[list-item]
    # Only the non-empty entry surfaces, numbered 1 (not 3).
    assert "### Delegated Response 1" in rendered
    assert "### Delegated Response 2" not in rendered
    assert "### Delegated Response 3" not in rendered
    assert "Real response" in rendered


def test_build_raw_response_delegated_parts_numbered_contiguously() -> None:
    """Multiple non-empty parts interleaved with skips still produce a
    contiguous 1..N sequence."""
    rendered = Agent._build_raw_response(
        {},
        ["First", "", None, "Second", None, "Third"],  # type: ignore[list-item]
    )
    assert "### Delegated Response 1\nFirst" in rendered
    assert "### Delegated Response 2\nSecond" in rendered
    assert "### Delegated Response 3\nThird" in rendered
    assert "### Delegated Response 4" not in rendered


# ---------------------------------------------------------------------------
# _synthesize_planning_execution_response — body must not call an LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesize_planning_execution_response_does_not_call_llm() -> None:
    """The synthesis method body delegates to ``_build_raw_response``.

    We verify by giving the agent a model whose ``chat`` would raise if
    invoked — and asserting the call still returns a sensible string.
    """
    a = Agent.__new__(Agent)
    a.agent_id = "test-agent"
    a.model = SimpleNamespace(
        chat=AsyncMock(side_effect=AssertionError("model.chat must NOT be called"))
    )

    my_results = {"{{TOOL}}": {"result": "Tool output."}}
    delegated = ["Delegated reply."]

    result = await a._synthesize_planning_execution_response(
        "user request",
        my_results,
        delegated,
    )

    assert "Tool output." in (result or "")
    assert "Delegated reply." in (result or "")
    a.model.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_synthesize_planning_execution_response_empty_returns_none() -> None:
    """No tool results AND no delegations → return None.

    The caller already gates on ``my_results and not has_successful_delegation``,
    so this code path is normally unreachable, but the contract is
    explicit: empty in → ``None`` out (so ``response_content`` stays
    empty and the outer fallback branches take over).
    """
    a = Agent.__new__(Agent)
    a.agent_id = "test-agent"
    a.model = SimpleNamespace()

    result = await a._synthesize_planning_execution_response("user request", {}, [])
    assert result is None


# ---------------------------------------------------------------------------
# Body-source check — the LLM call site has been removed from source
# ---------------------------------------------------------------------------


def test_synthesize_method_body_does_not_reference_model_chat() -> None:
    """Belt-and-suspenders: the source of ``_synthesize_planning_execution_response``
    must not contain ``self.model.chat`` — proves the LLM call was
    structurally removed, not just bypassed at runtime.
    """
    source = inspect.getsource(Agent._synthesize_planning_execution_response)
    assert "self.model.chat" not in source
    assert "_build_raw_response" in source


# ---------------------------------------------------------------------------
# Pure-artifact path interaction — separate optimization stays priority
# ---------------------------------------------------------------------------


def test_pure_artifact_helper_unchanged() -> None:
    """``_is_pure_artifact_result`` and ``_build_artifact_only_response``
    keep their existing behavior — covered in detail by
    ``test_agent_skip_synthesis.py``. This test is a smoke check that
    the helpers are still accessible from the Agent class.
    """
    assert callable(Agent._is_pure_artifact_result)
    assert callable(Agent._build_artifact_only_response)
    assert Agent._is_pure_artifact_result({"step_1": {"_artifact": {"filename": "x.pdf"}}}) is True
    assert Agent._is_pure_artifact_result({}) is False
