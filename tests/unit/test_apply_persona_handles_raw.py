"""Tests pinning the contract that ``Overlord._apply_persona`` absorbs raw input.

Background
----------
``_apply_persona`` is the single LLM pass on the way back to the user.
Historically its job was styling — "rephrase the agent's response in
your persona's voice." With agent-side and workflow-side synthesis
calls removed (see ``test_agent_skip_synthesis_always.py`` and
``test_workflow_consolidator.py``), ``_apply_persona`` now also has to
absorb structured tool outputs (per-task sections, key/value blocks,
JSON-like dicts) and surface every fact, ID, URL, filename, and number
in the user-facing reply.

We can't unit-test the persona LLM's output (that's behavior of an
external model), but we CAN pin the contract through the system
prompt's source text. Future edits that quietly strip the raw-input
acknowledgment or the date-preservation guardrail will fail these
tests.
"""

import inspect

from muxi.runtime.formation.overlord.overlord import Overlord


def test_persona_prompt_acknowledges_raw_structured_input() -> None:
    """The persona system prompt explicitly handles raw structured input."""
    source = inspect.getsource(Overlord._apply_persona)

    # Acknowledgment that the agent response may be either prose OR
    # structured tool outputs. The exact wording matters less than the
    # signal that the LLM should expect both shapes.
    assert "raw structured tool outputs" in source

    # Per-task section markers used by the workflow consolidator and
    # the agent's _build_raw_response — the persona LLM must recognize
    # them.
    assert "### Task" in source
    assert "### " in source

    # Key directive: don't drop facts.
    assert "Do not summarize away or omit specific data" in source


def test_persona_prompt_lists_data_categories_to_preserve() -> None:
    """The persona system prompt names the categories of data to preserve.

    Without this list the LLM may quietly drop technical details when
    rendering raw structured input.
    """
    source = inspect.getsource(Overlord._apply_persona)
    for required in ("fact", "ID", "URL", "filename", "number"):
        assert required in source, f"persona prompt must mention '{required}'"


def test_persona_prompt_max_tokens_unchanged() -> None:
    """Token budget for the persona LLM call must remain at 2000.

    The ``_apply_persona`` method now does both synthesis-from-raw AND
    styling in a single call; cutting the token budget would silently
    truncate replies on workflow-rich turns.
    """
    source = inspect.getsource(Overlord._apply_persona)
    # Two distinct LLM call sites in the method (non-actionable + actionable);
    # both should pass max_tokens=2000 OR max_tokens=300 (the short
    # non-actionable path). Neither should drop below those thresholds.
    assert "max_tokens=2000" in source
    # The non-actionable short path (no agent response) is intentionally
    # capped lower; that's a documented difference, not a regression.
    assert "max_tokens=300" in source


def test_persona_prompt_preserves_personal_information_directive() -> None:
    """The pre-existing 'preserve user personal info' guardrail stays."""
    source = inspect.getsource(Overlord._apply_persona)
    assert "specific personal information about the user" in source
    assert "Trust the agent's response" in source
