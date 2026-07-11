"""
Response envelope UI affordances (Response Envelope UI PRD, P1).

The response envelope gains an optional, typed ``ui`` array of
*affordances*. The runtime never renders anything: clients that
understand a widget type render it natively; clients that don't ignore
it. ``text`` always carries the fallback duty — producers MUST phrase
the response text so the interaction works without the widget.

Widgets are built exclusively by runtime producers through the builder
functions in this module — never from free-form LLM output — which is
what makes the ``action_link`` provenance rule structural: a URL can
only enter a widget through a producer that names its source
(formation config, tool result, or trigger payload).

Size discipline: widgets are clamped per-widget and per-envelope
(defaults validated by unit tests) so a misbehaving producer cannot
bloat every response.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from ..utils.fastjson import json
from ..utils.id_generator import generate_nanoid

# ===================================================================
# SIZE CLAMPS (load-validated defaults, see tests/unit/test_ui_datatypes.py)
# ===================================================================

# Maximum serialized size of a single widget (bytes). Oversized widgets
# are dropped, never truncated — a partial widget is worse than none
# because the text fallback is always complete on its own.
UI_WIDGET_MAX_BYTES = 4096

# Maximum number of widgets in one envelope.
UI_ENVELOPE_MAX_WIDGETS = 8

# Maximum combined serialized size of all widgets in one envelope (bytes).
UI_ENVELOPE_MAX_BYTES = 16384

# Maximum number of options in a single options widget.
UI_OPTIONS_MAX_ITEMS = 25


class UIProvenance(Enum):
    """Where an action_link URL came from.

    The producer records the source; the LLM may *select* among
    provenanced URLs but MUST NOT fabricate one into a widget.
    """

    FORMATION_CONFIG = "formation_config"
    TOOL_RESULT = "tool_result"
    TRIGGER_PAYLOAD = "trigger_payload"


def build_options_widget(
    prompt: str,
    options: List[Dict[str, str]],
    multi: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Build an ``options`` widget (clarification with choices — pick,
    don't type).

    Args:
        prompt: Short question the options answer.
        options: List of ``{"value": ..., "label": ...}`` dicts. Items
            missing a value are skipped; a missing label falls back to
            the value.
        multi: Whether multiple options may be selected (P1: always False).

    Returns:
        Widget dict with a runtime-assigned ``id`` (for the reply
        path), or None when no usable options remain.
    """
    normalized = []
    for option in options[:UI_OPTIONS_MAX_ITEMS]:
        value = option.get("value")
        if value is None or value == "":
            continue
        normalized.append({"value": value, "label": option.get("label") or value})

    if not normalized:
        return None

    return {
        "type": "options",
        "id": f"ui_{generate_nanoid()}",
        "prompt": prompt,
        "options": normalized,
        "multi": multi,
    }


def build_action_link_widget(
    label: str,
    url: str,
    source: UIProvenance,
    hint: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build an ``action_link`` widget (send the user somewhere external —
    credential portal, OAuth consent, dashboard).

    The ``source`` argument is mandatory and must be a
    :class:`UIProvenance` member — this is the structural enforcement
    of the provenance rule. ``source_ref`` names the concrete origin
    (e.g. ``links.github`` or a tool name) and is recorded on the
    ``ui.emitted`` observability event by the producer, not on the
    wire widget.

    Returns:
        Widget dict, or None when the URL fails basic validation
        (only http/https URLs are accepted).
    """
    if not isinstance(source, UIProvenance):
        raise ValueError(
            "action_link widgets require provenance: pass a UIProvenance member "
            "identifying where the URL came from (formation config, tool result, "
            "or trigger payload)."
        )

    if not url or not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None

    widget: Dict[str, Any] = {
        "type": "action_link",
        "id": f"ui_{generate_nanoid()}",
        "label": label,
        "url": url,
    }
    if hint:
        widget["hint"] = hint
    return widget


def clamp_ui(widgets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enforce per-widget and per-envelope size caps.

    Oversized widgets are dropped (the text fallback is always complete
    on its own); the envelope keeps at most ``UI_ENVELOPE_MAX_WIDGETS``
    widgets and ``UI_ENVELOPE_MAX_BYTES`` combined serialized bytes.
    """
    clamped: List[Dict[str, Any]] = []
    total_bytes = 0

    for widget in widgets:
        if not widget:
            continue
        if len(clamped) >= UI_ENVELOPE_MAX_WIDGETS:
            break
        try:
            widget_bytes = len(json.dumps(widget).encode("utf-8"))
        except (TypeError, ValueError):
            continue
        if widget_bytes > UI_WIDGET_MAX_BYTES:
            continue
        if total_bytes + widget_bytes > UI_ENVELOPE_MAX_BYTES:
            break
        clamped.append(widget)
        total_bytes += widget_bytes

    return clamped


def resolve_ui_response(
    ui_response: Optional[Dict[str, Any]],
    widget_id: Optional[str],
    option_values: Optional[List[str]],
) -> Optional[str]:
    """
    Resolve a ``ui_response`` hint against a clarification-produced
    options widget recorded in this conversation's pending state.

    Returns the pinned value when the hint's ``id`` matches the widget
    that asked the question AND the value is one of the offered
    options; otherwise None (unknown/stale id → the hint is ignored
    and the message stands alone). The runtime stays stateless: the id
    resolves against conversation state that already exists, never a
    server-side widget store.
    """
    if not ui_response or not widget_id or not option_values:
        return None
    if ui_response.get("id") != widget_id:
        return None
    value = ui_response.get("value")
    if value in option_values:
        return value
    return None
