#!/usr/bin/env python3
"""Test 7a5: Placeholder predicate resolution and action-description auto-inference.

Validates the two fixes shipped in v0.20260418.0 against realistic MS365 Graph
API response shapes, covering all three resolution tiers that today's runtime
exposes for dotted placeholder references against multi-record payloads:

    1. Explicit predicate (highest precedence):
         `{{FILE_LIST[name='Book.xlsx'].id}}` — the LLM tells us which record.
    2. Auto-inferred predicate (from action_description):
         `{{FILE_LIST.id}}` with action "...to find Book.xlsx" — the runtime
         cross-references the step description.
    3. Legacy first-match fallback:
         `{{FILE_LIST.id}}` with no named resource anywhere — first record wins,
         original behavior preserved for plans that don't rely on named context.

The test runs the REAL `_substitute_step_parameter_placeholders` pipeline
end-to-end (parser -> predicate -> extraction -> observability emission) on a
payload shaped exactly like the one that produced the Excel "picks wrong
record" regression in the Dev #1 bug report (Attachments folder returned
first from list-folder-files instead of Book.xlsx).

Per project e2e conventions this is a standalone script (not pytest). It
exercises Agent internals directly without an LLM or live MCP because the
fix is purely in the runtime-side placeholder pipeline — an LLM-driven flow
would be non-deterministic for this specific code path.
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


# MS365 Graph API `list-folder-files` response shape reproduced from the
# actual bug report. The Attachments folder lands first (alphabetical order
# from Graph), which is what caused `{{FILE_LIST.id}}` to resolve to the
# folder id instead of the workbook id in v0.20260417.x.
MS365_LIST_FOLDER_FILES_PAYLOAD: Dict[str, Any] = {
    "value": [
        {
            "id": "01SA7QZQ7HKJH6YEQPZNEY2JV3H7LXCTZU",
            "name": "Attachments",
            "folder": {"childCount": 3},
            "parentReference": {"driveId": "b!drive-id"},
        },
        {
            "id": "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5",
            "name": "Book.xlsx",
            "file": {
                "mimeType": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            },
            "parentReference": {"driveId": "b!drive-id"},
        },
        {
            "id": "01SA7QZQZZZZZZZZZZZZZZZZZZZZZZZZ",
            "name": "Notes.docx",
            "file": {
                "mimeType": (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                )
            },
            "parentReference": {"driveId": "b!drive-id"},
        },
    ]
}

# Graph API `list-sharepoint-sites` response shape — uses `displayName` as the
# human name field instead of `name`, ensuring the auto-inference helper
# picks the correct variant.
MS365_LIST_SITES_PAYLOAD: Dict[str, Any] = {
    "value": [
        {"id": "site-a", "displayName": "Engineering", "webUrl": "https://e.example"},
        {"id": "site-b", "displayName": "Marketing", "webUrl": "https://m.example"},
        {"id": "site-c", "displayName": "Sales", "webUrl": "https://s.example"},
    ]
}


def _fresh_agent() -> Agent:
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"
    return agent


def _make_results(base_key: str, payload: Any) -> Dict[str, Any]:
    """Wrap a payload in the planning-result envelope the substitution pipeline expects."""
    return {base_key: {"success": True, "result": payload}}


def _capture_observability_events() -> List[Dict[str, Any]]:
    """Swap observability.observe for a buffered capturer while still returning
    the real emit signature. Returns the list for assertion access.

    The production observe() is a fire-and-forget background thread that is
    hard to inspect from tests; patching at the attribute level lets us see
    exactly what the auto-inference path emits.
    """
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


STRING_PARAM_SCHEMA = {
    "type": "object",
    "required": ["driveItemId"],
    "properties": {"driveItemId": {"type": "string"}},
}
STRING_PARAM_PROPERTIES = {"driveItemId": {"type": "string"}}

ARRAY_PARAM_SCHEMA = {
    "type": "object",
    "required": ["ids"],
    "properties": {"ids": {"type": "array", "items": {"type": "string"}}},
}
ARRAY_PARAM_PROPERTIES = {"ids": {"type": "array", "items": {"type": "string"}}}


def test_explicit_predicate_picks_named_record() -> bool:
    """Tier 1: LLM writes `{{FILE_LIST[name='Book.xlsx'].id}}` — resolves to
    the Book.xlsx record's id deterministically."""
    print("\n1. Explicit predicate path — `{{FILE_LIST[name='Book.xlsx'].id}}`")
    agent = _fresh_agent()
    my_results = _make_results("{{FILE_LIST}}", MS365_LIST_FOLDER_FILES_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST[name='Book.xlsx'].id}}"},
        param_properties=STRING_PARAM_PROPERTIES,
        full_schema=STRING_PARAM_SCHEMA,
        action_description="List all worksheet names in the spreadsheet",
        my_results=my_results,
        tool_name="list-excel-worksheets",
    )
    print(f"   Resolved: {substituted}")
    if substituted.get("driveItemId") != "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5":
        print(f"   FAIL: expected Book.xlsx id, got {substituted!r}")
        return False
    print("   PASS — explicit predicate picked the workbook id, not the folder id")
    return True


def test_auto_inference_from_action_description() -> bool:
    """Tier 2: LLM writes `{{FILE_LIST.id}}` but action mentions Book.xlsx —
    runtime auto-infers `{name: 'Book.xlsx'}` and resolves correctly."""
    print("\n2. Auto-inferred predicate path — action mentions `Book.xlsx`")
    agent = _fresh_agent()
    my_results = _make_results("{{FILE_LIST}}", MS365_LIST_FOLDER_FILES_PAYLOAD)
    captured = _capture_observability_events()

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST.id}}"},
        param_properties=STRING_PARAM_PROPERTIES,
        full_schema=STRING_PARAM_SCHEMA,
        action_description="List files in the root folder to find Book.xlsx",
        my_results=my_results,
        tool_name="list-excel-worksheets",
    )
    print(f"   Resolved: {substituted}")
    if substituted.get("driveItemId") != "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5":
        print(f"   FAIL: expected Book.xlsx id, got {substituted!r}")
        return False

    auto_events = [
        evt
        for evt in captured
        if evt["data"] and evt["data"].get("inferred_predicate") is not None
    ]
    if not auto_events:
        print("   FAIL: no AGENT_PLANNING observability event emitted for auto-inference")
        return False
    event = auto_events[0]
    if event["data"]["inferred_predicate"] != {"name": "Book.xlsx"}:
        print(
            "   FAIL: observability event predicate mismatch — "
            f"expected {{'name': 'Book.xlsx'}}, got {event['data']['inferred_predicate']!r}"
        )
        return False

    print(
        "   PASS — auto-inference resolved Book.xlsx AND emitted AGENT_PLANNING event "
        f"with inferred_predicate={event['data']['inferred_predicate']}"
    )
    return True


def test_auto_inference_respects_displayname_variant() -> bool:
    """Tier 2 variant: records use `displayName` instead of `name` — the
    synthesized predicate must use the same field variant so downstream
    matching succeeds."""
    print("\n3. Auto-inferred predicate adapts to `displayName` records")
    agent = _fresh_agent()
    my_results = _make_results("{{SITES}}", MS365_LIST_SITES_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{SITES.id}}"},
        param_properties=STRING_PARAM_PROPERTIES,
        full_schema=STRING_PARAM_SCHEMA,
        action_description="Open the 'Marketing' workspace to list its documents",
        my_results=my_results,
        tool_name="list-site-documents",
    )
    print(f"   Resolved: {substituted}")
    if substituted.get("driveItemId") != "site-b":
        print(f"   FAIL: expected Marketing site id, got {substituted!r}")
        return False
    print("   PASS — auto-inference used `displayName` variant, picked Marketing site")
    return True


def test_legacy_fallback_without_named_resource() -> bool:
    """Tier 3: action_description doesn't name a resource — fall back to the
    legacy first-match behavior (critical for backward compat with plans
    that don't lean on named-resource context)."""
    print("\n4. Legacy fallback — no named resource in action description")
    agent = _fresh_agent()
    my_results = _make_results("{{FILE_LIST}}", MS365_LIST_FOLDER_FILES_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST.id}}"},
        param_properties=STRING_PARAM_PROPERTIES,
        full_schema=STRING_PARAM_SCHEMA,
        action_description="Pass the first result id to the next step",
        my_results=my_results,
        tool_name="generic-consumer",
    )
    print(f"   Resolved: {substituted}")
    if substituted.get("driveItemId") != "01SA7QZQ7HKJH6YEQPZNEY2JV3H7LXCTZU":
        print(f"   FAIL: expected Attachments id (first record), got {substituted!r}")
        return False
    print("   PASS — legacy first-match preserved when no named resource in action")
    return True


def test_explicit_predicate_beats_auto_inference() -> bool:
    """Precedence: when the LLM provides `[name='X']`, auto-inference MUST
    NOT override it even if the action_description would synthesize
    something different."""
    print("\n5. Precedence — explicit predicate beats auto-inference")
    agent = _fresh_agent()
    my_results = _make_results("{{FILE_LIST}}", MS365_LIST_FOLDER_FILES_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST[name='Notes.docx'].id}}"},
        param_properties=STRING_PARAM_PROPERTIES,
        full_schema=STRING_PARAM_SCHEMA,
        # Action mentions Book.xlsx, but explicit predicate says Notes.docx.
        action_description="Read the sheets from Book.xlsx and summarize them",
        my_results=my_results,
        tool_name="open-document",
    )
    print(f"   Resolved: {substituted}")
    if substituted.get("driveItemId") != "01SA7QZQZZZZZZZZZZZZZZZZZZZZZZZZ":
        print(f"   FAIL: expected Notes.docx id, got {substituted!r}")
        return False
    print("   PASS — explicit `[name='Notes.docx']` won over action-derived inference")
    return True


def test_predicate_filters_array_parameter() -> bool:
    """Array-typed parameters: the predicate path must filter records FIRST,
    then collect the field across only the matching subset — otherwise a
    `Delete({{FILE_LIST[name='Notes.docx'].id}})` bulk operation would
    collect every id and wipe the whole folder."""
    print("\n6. Array-typed parameter — predicate restricts to matching records")
    agent = _fresh_agent()
    my_results = _make_results("{{FILE_LIST}}", MS365_LIST_FOLDER_FILES_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"ids": "{{FILE_LIST[name='Notes.docx'].id}}"},
        param_properties=ARRAY_PARAM_PROPERTIES,
        full_schema=ARRAY_PARAM_SCHEMA,
        action_description="Delete the requested files",
        my_results=my_results,
        tool_name="delete-items",
    )
    print(f"   Resolved: {substituted}")
    expected = ["01SA7QZQZZZZZZZZZZZZZZZZZZZZZZZZ"]
    if substituted.get("ids") != expected:
        print(f"   FAIL: expected {expected!r}, got {substituted!r}")
        return False
    print("   PASS — array extraction honored predicate, returned only the matching id")
    return True


def test_auto_inference_returns_none_when_named_resource_absent() -> bool:
    """Guard — when action mentions a resource that is NOT in the prior step's
    payload, auto-inference MUST decline (no synthetic predicate emitted).
    The resolution then falls back to legacy first-match behavior, matching
    the pre-v0.20260418 semantics."""
    print("\n7. Guard — named resource absent from payload skips auto-inference")
    agent = _fresh_agent()
    my_results = _make_results("{{FILE_LIST}}", MS365_LIST_FOLDER_FILES_PAYLOAD)
    captured = _capture_observability_events()

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST.id}}"},
        param_properties=STRING_PARAM_PROPERTIES,
        full_schema=STRING_PARAM_SCHEMA,
        # The payload does NOT contain a record named Spreadsheet.xlsx.
        action_description="Locate Spreadsheet.xlsx in the drive",
        my_results=my_results,
        tool_name="list-excel-worksheets",
    )
    print(f"   Resolved: {substituted}")
    auto_events = [
        evt
        for evt in captured
        if evt["data"] and evt["data"].get("inferred_predicate") is not None
    ]
    if auto_events:
        print(f"   FAIL: auto-inference fired for a name not in payload: {auto_events[0]!r}")
        return False
    print("   PASS — auto-inference declined; no AGENT_PLANNING event emitted")
    return True


async def main() -> int:
    print("=" * 70)
    print("Test 7a5: Placeholder predicate & auto-inference resolution")
    print("=" * 70)

    start = time.time()
    original_observe = observability.observe
    try:
        results = [
            ("explicit_predicate", test_explicit_predicate_picks_named_record()),
            ("auto_inference_from_action", test_auto_inference_from_action_description()),
            ("auto_inference_displayname", test_auto_inference_respects_displayname_variant()),
            ("legacy_fallback", test_legacy_fallback_without_named_resource()),
            ("explicit_beats_auto", test_explicit_predicate_beats_auto_inference()),
            ("array_predicate", test_predicate_filters_array_parameter()),
            ("auto_inference_guard", test_auto_inference_returns_none_when_named_resource_absent()),
        ]
    finally:
        # Restore the real observe so later tests in the same process (if any)
        # see the production implementation.
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
        print("  - Explicit predicate syntax resolves named records deterministically")
        print("  - Auto-inference from action_description bridges legacy plans")
        print("  - Field variants (`name`/`displayName`) are both honored")
        print("  - Legacy first-match behavior preserved when no named resource")
        print("  - Explicit predicate always wins over auto-inference")
        print("  - Array parameters respect predicate filtering")
        print("  - Auto-inference declines when named resource not in payload")
        print("\n" + "=" * 70)
        print("\n### Chat transcript:\n")
        print("  User: List all worksheets in Book.xlsx from OneDrive")
        print(
            "  Planner (today): emits `driveItemId={{FILE_LIST.id}}` with action "
            '"... to find Book.xlsx"'
        )
        print(
            "  Runtime: auto-infers {name: 'Book.xlsx'} predicate, resolves to the "
            "workbook id (not the Attachments folder)"
        )
        print("  MCP: list-excel-worksheets(driveItemId=01SA7QZQZWMLF...) succeeds")
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
