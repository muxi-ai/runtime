"""
Tests for ``Overlord._resolve_actionability``.

Background
----------
The non-actionable fast path in ``Overlord._process_sync_chat`` skips
workflow analysis, agent selection, and tool planning, then runs
``_apply_persona`` to produce a chat-style reply. Before PR #160 that
fast path was gated by an LLM-based classifier that correctly read
short procedure triggers like "onboard me" as ACTIONABLE.

PR #160 swapped the LLM out for a local prototype-similarity classifier
(``Xenova/multilingual-e5-small`` cosine match) tuned to filter bare
social chatter ("hi", "thanks", "got it"). The new classifier is
deliberately conservative about accepting short verb-light phrases as
actionable, so terse procedure triggers landed on the wrong side of
the boundary. In the hello-muxi demo the result was:

* User says "onboard me"
* SOP ``onboarding`` matches at +1.1s
* ``_is_actionable_message`` (local classifier) returns ``False``
* Overlord takes the persona fast path, returns a chat reply
* No agent.planning, no github-mcp tool call, no workflow execution

The fix is structural: a matched SOP is by definition actionable,
so ``_resolve_actionability`` overrides the classifier verdict when
``matched_sop is not None``.

These tests pin:

1. classifier returns True, no SOP → result True (no override fires)
2. classifier returns False, no SOP → result False (legacy fast path)
3. classifier returns True with SOP match → result True (no override needed)
4. classifier returns False with SOP match → result True + observability
   event tagged ``actionability_override``
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.formation.overlord.overlord import Overlord


def _make_overlord(*, classifier_returns: bool) -> Overlord:
    """Build a bare ``Overlord`` instance just for testing the helper.

    ``Overlord.__init__`` requires a full formation engine and live
    services; we sidestep that by using ``__new__`` and then patching
    only the single async method the helper depends on.
    """
    overlord = Overlord.__new__(Overlord)
    overlord._is_actionable_message = AsyncMock(return_value=classifier_returns)  # type: ignore[method-assign]
    return overlord


class _CapturedEvents:
    """Tiny shim that records observability.observe(...) calls."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@pytest.fixture
def captured_events() -> _CapturedEvents:
    cap = _CapturedEvents()
    with patch(
        "muxi.runtime.formation.overlord.overlord.observability.observe",
        side_effect=cap,
    ):
        yield cap


@pytest.mark.asyncio
async def test_classifier_actionable_no_sop_returns_true(
    captured_events: _CapturedEvents,
) -> None:
    overlord = _make_overlord(classifier_returns=True)

    result = await overlord._resolve_actionability("create a chart", matched_sop=None)

    assert result is True
    overlord._is_actionable_message.assert_awaited_once_with("create a chart")
    # No override event fired — nothing to log.
    assert all(
        ((c.get("data") or {}).get("stage") != "actionability_override")
        for c in captured_events.calls
    )


@pytest.mark.asyncio
async def test_classifier_non_actionable_no_sop_returns_false(
    captured_events: _CapturedEvents,
) -> None:
    """Bare 'hi' / 'thanks' style chatter without an SOP MUST take the fast path."""
    overlord = _make_overlord(classifier_returns=False)

    result = await overlord._resolve_actionability("thanks", matched_sop=None)

    assert result is False
    # No SOP, no override event.
    assert all(
        ((c.get("data") or {}).get("stage") != "actionability_override")
        for c in captured_events.calls
    )


@pytest.mark.asyncio
async def test_classifier_actionable_with_sop_returns_true_no_override(
    captured_events: _CapturedEvents,
) -> None:
    """When the classifier already says actionable, the SOP path is moot — no override event."""
    overlord = _make_overlord(classifier_returns=True)

    sop = {"id": "onboarding", "name": "MUXI Onboarding"}
    result = await overlord._resolve_actionability("please onboard me to muxi", matched_sop=sop)

    assert result is True
    assert all(
        ((c.get("data") or {}).get("stage") != "actionability_override")
        for c in captured_events.calls
    )


@pytest.mark.asyncio
async def test_classifier_non_actionable_with_sop_forces_actionable(
    captured_events: _CapturedEvents,
) -> None:
    """Regression: 'onboard me' with onboarding SOP must NOT take the persona fast path."""
    overlord = _make_overlord(classifier_returns=False)

    sop: Dict[str, Any] = {"id": "onboarding", "name": "MUXI Onboarding"}
    result = await overlord._resolve_actionability("onboard me", matched_sop=sop)

    assert result is True

    # Override event fired at debug level with the right metadata.
    override_calls = [
        c
        for c in captured_events.calls
        if (c.get("data") or {}).get("stage") == "actionability_override"
    ]
    assert (
        len(override_calls) == 1
    ), "Exactly one SOP_MATCHED override event must fire when the classifier disagrees"
    data = override_calls[0]["data"]
    assert data["sop_id"] == "onboarding"
    assert data["sop_name"] == "MUXI Onboarding"
    assert data["classifier_label"] == "non_actionable"


@pytest.mark.asyncio
async def test_override_falls_back_to_id_when_name_missing(
    captured_events: _CapturedEvents,
) -> None:
    """SOPs without a friendly name still log a sane sop_name in the override event."""
    overlord = _make_overlord(classifier_returns=False)

    result = await overlord._resolve_actionability("ship it", matched_sop={"id": "deploy_pipeline"})

    assert result is True
    override_calls = [
        c
        for c in captured_events.calls
        if (c.get("data") or {}).get("stage") == "actionability_override"
    ]
    assert len(override_calls) == 1
    assert override_calls[0]["data"]["sop_name"] == "deploy_pipeline"
