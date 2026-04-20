"""
Test 7a7: Text-payload predicate filtering, embedded placeholder
substitution, and section-separator field extraction.

Regression test for the v0.20260420.0 field report traced to the Google
Calendar and Gmail MCP servers:

    A. Calendar: `{{EVENT_SEARCH[summary='Spark Test 2'].id}}` dropped
       because the predicate filter couldn't match against the text-blob
       payload the google-mcp `get_events` tool returns.
    B. Gmail: `{{DRAFT_CONTENT.body}}\\n\\nHappy Birthday!` reached MCP as
       a literal string because embedded placeholders (tokens inside a
       larger string) were not substituted, AND `.body` couldn't be
       extracted because the Gmail MCP uses `--- BODY ---` section
       separators instead of `Body: value` label lines.

Per project e2e conventions this is a standalone script (not pytest).
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation.agents.agent import Agent  # noqa: E402
from muxi.runtime.services import observability  # noqa: E402

# The exact shape google-mcp `get_events` returns (from the v0.20260420.0
# log capture). Events are serialized as bulleted lines with a quoted
# title, inline metadata, and an `ID: <event_id>` field on the same or
# following line. The payload is wrapped as `{"result": "<this text>"}`
# by the MCP protocol layer.
GOOGLE_CALENDAR_GET_EVENTS_TEXT = (
    "Successfully retrieved 3 events from calendar 'primary' for oleksandra@automaze.io:\n"
    '- "Spark Test 2" (Starts: 2026-04-21T10:00:00+03:00, Ends: 2026-04-21T10:30:00+03:00)\n'
    "  Description: No Description\n"
    "  Location: No Location\n"
    "  Attendees: None\n"
    "  ID: rnnbrh9v8lh853dkvit1d8a234 | Link: https://example.com/a\n"
    '- "Ruby Daily Sync" (Starts: 2026-04-21T12:00:00+03:00, Ends: 2026-04-21T12:30:00+03:00)\n'
    "  Description: Daily sync\n"
    "  ID: 09jdummda51b9m0fqlomnan8em | Link: https://example.com/b\n"
    '- "Emerald Daily Sync" (Starts: 2026-04-21T12:30:00+03:00, Ends: 2026-04-21T13:00:00+03:00)\n'
    "  Description: Daily sync\n"
    "  ID: _6gq3ihi46kojgba565346b9k6ksk8b9o6 | Link: https://example.com/c\n"
)

# The exact shape google-mcp `get_gmail_message_content` returns (from
# the v0.20260420.0 log capture). Labels are Subject/From/Date/To on
# `Field: value` lines, then the body lives under a `--- BODY ---`
# section separator.
GMAIL_DRAFT_CONTENT_TEXT = (
    "Retrieved 1 messages:\n\n"
    "Message ID: 19d9be86eb54a312\n"
    "Subject: Meeting tomorrow\n"
    "From: sender@example.com\n"
    "Date: Fri, 17 Apr 2026 07:46:34 -0700\n"
    "To: recipient@example.com\n"
    "Web Link: https://mail.google.com/mail/u/0/#all/19d9be86eb54a312\n"
    "\n"
    "--- BODY ---\n"
    "Hi Anna,\r\n"
    "\r\n"
    "I wanted to reach out regarding our meeting scheduled for tomorrow.\r\n"
    "\r\n"
    "Best regards\r\n"
    "\n"
)


MANAGE_EVENT_PROPS = {
    "action": {"type": "string"},
    "event_id": {"type": "string"},
    "start_time": {"type": "string"},
    "end_time": {"type": "string"},
}
MANAGE_EVENT_SCHEMA = {
    "type": "object",
    "required": ["action"],
    "properties": MANAGE_EVENT_PROPS,
}


DRAFT_GMAIL_PROPS = {
    "subject": {"type": "string"},
    "body": {"type": "string"},
    "to": {"type": "array"},
}
DRAFT_GMAIL_SCHEMA = {
    "type": "object",
    "required": ["subject", "body"],
    "properties": DRAFT_GMAIL_PROPS,
}


def _fresh_agent() -> Agent:
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"
    return agent


def _make_results(base_key: str, payload: Any) -> Dict[str, Any]:
    return {base_key: {"success": True, "result": payload}}


def _capture_observability_events() -> List[Dict[str, Any]]:
    captured: List[Dict[str, Any]] = []

    def _capture(event_type, level=None, data=None, description=""):  # type: ignore[no-untyped-def]
        captured.append(
            {
                "event_type": str(event_type),
                "level": str(level) if level is not None else None,
                "data": dict(data) if isinstance(data, dict) else data,
                "description": description,
            }
        )

    observability.observe = _capture  # type: ignore[assignment]
    return captured


def test_calendar_predicate_resolves_against_text_block_payload() -> bool:
    """Google Calendar: `{{EVENT_SEARCH[summary='Spark Test 2'].id}}` must
    resolve against the google-mcp text-blob payload and hand a real
    event_id to the next manage_event step."""
    print("\n1. Calendar — filtered placeholder resolves against text-blob payload")
    agent = _fresh_agent()
    my_results = _make_results(
        "{{EVENT_SEARCH}}",
        {"result": GOOGLE_CALENDAR_GET_EVENTS_TEXT},
    )

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "update",
            "event_id": "{{EVENT_SEARCH[summary='Spark Test 2'].id}}",
            "start_time": "2026-04-21T10:00:00+03:00",
            "end_time": "2026-04-21T10:45:00+03:00",
        },
        param_properties=MANAGE_EVENT_PROPS,
        full_schema=MANAGE_EVENT_SCHEMA,
        action_description='Reschedule event "Spark Test 2"',
        my_results=my_results,
        tool_name="google-mcp__manage_event",
    )
    print(f"   Resolved: {substituted}")

    if substituted.get("event_id") != "rnnbrh9v8lh853dkvit1d8a234":
        print(f"   FAIL: expected event_id=rnnbrh9v8lh853dkvit1d8a234, got {substituted!r}")
        return False
    print("   PASS — predicate matched Spark Test 2 block, extracted correct event_id")
    return True


def test_calendar_predicate_selects_right_event_not_first() -> bool:
    """With the predicate `summary='Ruby Daily Sync'` we must select the
    second event — NOT the first one. This verifies the predicate filter
    is actually filtering, not just falling through to a naive first-ID
    extraction."""
    print("\n2. Calendar — predicate selects NOT-first event from text-blob")
    agent = _fresh_agent()
    my_results = _make_results(
        "{{EVENT_SEARCH}}",
        {"result": GOOGLE_CALENDAR_GET_EVENTS_TEXT},
    )

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "delete",
            "event_id": "{{EVENT_SEARCH[summary='Ruby Daily Sync'].id}}",
        },
        param_properties=MANAGE_EVENT_PROPS,
        full_schema=MANAGE_EVENT_SCHEMA,
        action_description="Delete Ruby Daily Sync",
        my_results=my_results,
        tool_name="google-mcp__manage_event",
    )
    print(f"   Resolved: {substituted}")

    if substituted.get("event_id") != "09jdummda51b9m0fqlomnan8em":
        print(f"   FAIL: expected Ruby ID, got {substituted.get('event_id')!r}")
        return False
    print("   PASS — predicate routed past first event to the right Ruby block")
    return True


def test_calendar_missing_predicate_match_drops_param() -> bool:
    """A predicate that matches none of the text blocks must result in
    `event_id` being dropped (it's non-required on manage_event) AND a
    `placeholder.unresolved` warning being emitted."""
    print("\n3. Calendar — unmatched predicate drops param and emits unresolved warning")
    agent = _fresh_agent()
    captured = _capture_observability_events()

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "update",
            "event_id": "{{EVENT_SEARCH[summary='Nonexistent Event'].id}}",
        },
        param_properties=MANAGE_EVENT_PROPS,
        full_schema=MANAGE_EVENT_SCHEMA,
        action_description="Update Nonexistent Event",
        my_results=_make_results(
            "{{EVENT_SEARCH}}",
            {"result": GOOGLE_CALENDAR_GET_EVENTS_TEXT},
        ),
        tool_name="google-mcp__manage_event",
    )
    # Substitution leaves the literal token intact; the strip pass then
    # drops it and emits the warning.
    cleaned = agent._strip_leftover_placeholder_parameters(
        parameters=substituted,
        required_params=["action"],
        tool_name="google-mcp__manage_event",
    )

    print(f"   Cleaned: {cleaned}")
    if "event_id" in cleaned:
        print(f"   FAIL: event_id should have been dropped, got {cleaned!r}")
        return False

    warning = [
        evt
        for evt in captured
        if evt["data"]
        and isinstance(evt["data"], dict)
        and evt["data"].get("phase") == "placeholder.unresolved"
    ]
    if not warning:
        print("   FAIL: no placeholder.unresolved event emitted")
        return False
    print("   PASS — unmatched predicate dropped event_id and emitted warning")
    return True


def test_gmail_embedded_body_placeholder_substitutes() -> bool:
    """Gmail: `body="{{DRAFT_CONTENT.body}}\\n\\nHappy Birthday!"` must
    splice in the real draft body while preserving the `\\n\\nHappy
    Birthday!` suffix. Requires both Fix 2 (embedded placeholder scan)
    and Fix 3 (section separator extraction) to cooperate."""
    print("\n4. Gmail — embedded placeholder + section separator: body resolves end-to-end")
    agent = _fresh_agent()
    my_results = _make_results(
        "{{DRAFT_CONTENT}}",
        {"result": GMAIL_DRAFT_CONTENT_TEXT},
    )

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "subject": "{{DRAFT_CONTENT.subject}}",
            "body": "{{DRAFT_CONTENT.body}}\n\nHappy Birthday!",
            "to": ["recipient@example.com"],
        },
        param_properties=DRAFT_GMAIL_PROPS,
        full_schema=DRAFT_GMAIL_SCHEMA,
        action_description='Update draft, append "Happy Birthday!"',
        my_results=my_results,
        tool_name="google-mcp__draft_gmail_message",
    )
    print(f"   Resolved subject: {substituted.get('subject')!r}")
    print(f"   Resolved body preview: {substituted.get('body', '')[:80]!r}...")

    body = substituted.get("body", "")
    # The original body content must be present (proves Fix 3 captured
    # the `--- BODY ---` section), AND the literal suffix must remain
    # appended unchanged (proves Fix 2 only touched the placeholder
    # token and not the surrounding text).
    if "Hi Anna," not in body:
        print(f"   FAIL: original body content missing from resolved value: {body!r}")
        return False
    if "Best regards" not in body:
        print(f"   FAIL: body tail missing: {body!r}")
        return False
    if not body.rstrip().endswith("Happy Birthday!"):
        print(f"   FAIL: Happy Birthday suffix not preserved: {body!r}")
        return False
    print("   PASS — body contains the original message + the Happy Birthday suffix")
    return True


def test_gmail_unresolved_embedded_placeholder_flags_unresolved() -> bool:
    """When the draft payload has no recoverable `body` field, the
    `{{DRAFT_CONTENT.body}}` token embedded in the larger string must
    stay literal AND be flagged by the unresolved-leaf detector so the
    strip pass logs it."""
    print("\n5. Gmail — unresolved embedded token flagged by leaf detector")
    agent = _fresh_agent()

    # Payload with NO body field (subject only).
    missing_body_payload = {
        "result": "Subject: Meeting tomorrow\nFrom: sender@example.com\n",
    }
    my_results = _make_results("{{DRAFT_CONTENT}}", missing_body_payload)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "subject": "{{DRAFT_CONTENT.subject}}",
            "body": "{{DRAFT_CONTENT.body}}\n\nHappy Birthday!",
        },
        param_properties=DRAFT_GMAIL_PROPS,
        full_schema=DRAFT_GMAIL_SCHEMA,
        action_description="Update draft",
        my_results=my_results,
        tool_name="google-mcp__draft_gmail_message",
    )

    # The embedded token must remain literal (no body in payload).
    if "{{DRAFT_CONTENT.body}}" not in substituted.get("body", ""):
        print(
            "   FAIL: unresolved body token should have stayed literal, "
            f"got: {substituted.get('body')!r}"
        )
        return False

    leaves = agent._find_unresolved_placeholder_leaves(substituted.get("body"), base_path="body")
    if not leaves or not any(leaf["placeholder"] == "{{DRAFT_CONTENT.body}}" for leaf in leaves):
        print(f"   FAIL: unresolved leaf detector missed the token, got {leaves!r}")
        return False
    print("   PASS — embedded unresolved token detected for strip-pass logging")
    return True


async def main() -> int:
    print("=" * 70)
    print("Test 7a7: Text-payload predicate + embedded placeholder + section separator")
    print("=" * 70)

    start = time.time()
    original_observe = observability.observe
    try:
        results = [
            (
                "calendar_predicate_on_text_payload",
                test_calendar_predicate_resolves_against_text_block_payload(),
            ),
            (
                "calendar_predicate_routes_to_right_event",
                test_calendar_predicate_selects_right_event_not_first(),
            ),
            (
                "calendar_unmatched_predicate_drops_and_warns",
                test_calendar_missing_predicate_match_drops_param(),
            ),
            (
                "gmail_embedded_body_substitution",
                test_gmail_embedded_body_placeholder_substitutes(),
            ),
            (
                "gmail_unresolved_embedded_flagged",
                test_gmail_unresolved_embedded_placeholder_flags_unresolved(),
            ),
        ]
    finally:
        observability.observe = original_observe

    duration = time.time() - start
    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print("\n" + "=" * 70)
    print(f"Scenario results ({duration:.2f}s):")
    for name, ok in results:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {name}")

    print("\n" + "=" * 70)

    if passed == total:
        print(f"\n### Test Result:\n  SUCCESS: {passed}/{total} scenarios passed")
        print("  - Calendar: filtered placeholder resolves against text-blob payload")
        print("  - Calendar: predicate selects the correct event (not always first)")
        print("  - Calendar: unmatched predicate drops the param and emits warning")
        print("  - Gmail: embedded placeholder in body string substitutes correctly")
        print("  - Gmail: unresolved embedded token flagged for strip-pass logging")
        print("\n" + "=" * 70)
        print("\n### Chat transcript:\n")
        print('  User: reschedule event "Spark Test 2" tomorrow: 10:00 till 10:45')
        print("  Planner: emits `{{EVENT_SEARCH[summary='Spark Test 2'].id}}`")
        print("  Runtime: predicate matches the Spark Test 2 text block, resolves real event_id")
        print("  MCP: manage_event(action=update, event_id=rnnb..., start, end) succeeds")
        print("")
        print('  User: update this draft. Add "Happy Birthday!" at the end')
        print("  Planner: emits `body=\"{{DRAFT_CONTENT.body}}\\n\\nHappy Birthday!\"`")
        print("  Runtime: embedded placeholder resolved via `--- BODY ---` section extractor")
        print("  MCP: draft_gmail_message receives the real body + the appended suffix")
        return 0

    print(f"\n### Test Result:\n  FAILED: {passed}/{total} scenarios passed")
    for name, ok in results:
        if not ok:
            print(f"    - {name} did not meet invariant")
    return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
