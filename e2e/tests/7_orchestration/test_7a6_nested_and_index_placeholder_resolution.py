"""Test 7a6: Nested-dict / list placeholder substitution + `[N]` integer
index syntax (Dev #1 v0.20260418.0 silent-failure follow-up).

Validates the two regressions reported in the v0.20260418.0 field report:

    1. Excel B2 — `{{WORKSHEET_LIST[0].id}}` was unsupported syntax. The
       parser fell through, the kind-aware fallback bound `workbookWorksheetId`
       to the Book.xlsx driveItemId, and Graph returned 404 on
       get-excel-worksheet.
    2. OneDrive move — a placeholder nested inside `parentReference: {id:
       "{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}"}` was not substituted
       because v0.20260418.0 only walked TOP-LEVEL string params. The
       literal `{{...}}` reached MS Graph which silently ignored the bogus
       parentReference and the file never moved (200 OK, no-op).

Six scenarios cover both fixes plus the recursive leftover-strip warning,
the depth cap, and the repair-plan trigger for required dict params.

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

# MS Graph `list-excel-worksheets` response — multiple worksheets each with
# a GUID-shaped id. v0.20260418.0 could not parse `{{LIST[0].id}}`, so this
# was the payload that produced the silent driveItemId substitution.
MS365_WORKSHEET_LIST_PAYLOAD: Dict[str, Any] = {
    "value": [
        {"id": "{00000000-0001-0000-0000-000000000000}", "name": "Sheet1", "position": 0},
        {"id": "{00000000-0002-0000-0000-000000000000}", "name": "Sheet2", "position": 1},
        {"id": "{00000000-0003-0000-0000-000000000000}", "name": "Sheet3", "position": 2},
    ]
}

# MS Graph `search-onedrive-files` response with a Spark Test folder result.
# v0.20260418.0 could parse the predicate but never reached it because the
# placeholder was nested inside parentReference, which the substitution
# pipeline skipped.
MS365_FOLDER_SEARCH_PAYLOAD: Dict[str, Any] = {
    "value": [
        {
            "id": "01ATTACHMENTSFOLDERID",
            "name": "Attachments",
            "folder": {"childCount": 5},
        },
        {
            "id": "01SPARKTESTFOLDERID",
            "name": "Spark Test",
            "folder": {"childCount": 0},
        },
        {
            "id": "01ARCHIVEFOLDERID",
            "name": "Archive",
            "folder": {"childCount": 200},
        },
    ]
}


def _fresh_agent() -> Agent:
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"
    return agent


def _make_results(base_key: str, payload: Any) -> Dict[str, Any]:
    return {base_key: {"success": True, "result": payload}}


def _capture_observability_events() -> List[Dict[str, Any]]:
    """Patch observability.observe to capture events for assertion."""
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


WORKSHEET_PARAM_SCHEMA = {
    "type": "object",
    "required": ["workbookWorksheetId"],
    "properties": {"workbookWorksheetId": {"type": "string"}},
}
WORKSHEET_PARAM_PROPERTIES = {"workbookWorksheetId": {"type": "string"}}

MOVE_PARAM_SCHEMA = {
    "type": "object",
    "required": ["driveItemId", "parentReference"],
    "properties": {
        "driveItemId": {"type": "string"},
        "parentReference": {"type": "object"},
    },
}
MOVE_PARAM_PROPERTIES = {
    "driveItemId": {"type": "string"},
    "parentReference": {"type": "object"},
}


def test_integer_index_resolves_first_worksheet() -> bool:
    """Tier 1 of Dev #1 v0.20260418.0 Excel B2: `{{WORKSHEET_LIST[0].id}}`
    must resolve to the first worksheet's GUID, not silently bind to a
    driveItemId via the kind-aware fallback."""
    print("\n1. `[0]` integer-index — `{{WORKSHEET_LIST[0].id}}` selects Sheet1")
    agent = _fresh_agent()
    my_results = _make_results("{{WORKSHEET_LIST}}", MS365_WORKSHEET_LIST_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"workbookWorksheetId": "{{WORKSHEET_LIST[0].id}}"},
        param_properties=WORKSHEET_PARAM_PROPERTIES,
        full_schema=WORKSHEET_PARAM_SCHEMA,
        action_description="Read range from the first worksheet of Book.xlsx",
        my_results=my_results,
        tool_name="ms365-mcp__get-excel-range",
    )
    print(f"   Resolved: {substituted}")
    expected = "{00000000-0001-0000-0000-000000000000}"
    if substituted.get("workbookWorksheetId") != expected:
        print(f"   FAIL: expected {expected!r}, got {substituted.get('workbookWorksheetId')!r}")
        return False
    print("   PASS — integer index resolved to Sheet1's GUID, not Book.xlsx's driveItemId")
    return True


def test_negative_integer_index_resolves_last_worksheet() -> bool:
    """`{{WORKSHEET_LIST[-1].id}}` must select the last worksheet."""
    print("\n2. `[-1]` negative-index — `{{WORKSHEET_LIST[-1].id}}` selects Sheet3")
    agent = _fresh_agent()
    my_results = _make_results("{{WORKSHEET_LIST}}", MS365_WORKSHEET_LIST_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"workbookWorksheetId": "{{WORKSHEET_LIST[-1].id}}"},
        param_properties=WORKSHEET_PARAM_PROPERTIES,
        full_schema=WORKSHEET_PARAM_SCHEMA,
        action_description="Read range from the last worksheet",
        my_results=my_results,
        tool_name="ms365-mcp__get-excel-range",
    )
    print(f"   Resolved: {substituted}")
    expected = "{00000000-0003-0000-0000-000000000000}"
    if substituted.get("workbookWorksheetId") != expected:
        print(f"   FAIL: expected {expected!r}, got {substituted.get('workbookWorksheetId')!r}")
        return False
    print("   PASS — negative index resolved to Sheet3 GUID")
    return True


def test_nested_dict_placeholder_substitution() -> bool:
    """Dev #1 v0.20260418.0 OneDrive: a placeholder nested inside
    `parentReference: {id: "{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}"}`
    must be substituted by the recursive nested-substitution pass — without
    it the literal placeholder string is sent to MS Graph and the move
    silently no-ops."""
    print('\n3. Nested dict — `parentReference: {id: "{{...}}"}` is substituted')
    agent = _fresh_agent()
    my_results = _make_results("{{SPARK_FOLDER_SEARCH}}", MS365_FOLDER_SEARCH_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "driveItemId": "01-source-file-id",
            "parentReference": {"id": "{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}"},
        },
        param_properties=MOVE_PARAM_PROPERTIES,
        full_schema=MOVE_PARAM_SCHEMA,
        action_description="Move the file to the Spark Test folder",
        my_results=my_results,
        tool_name="ms365-mcp__move-rename-onedrive-item",
    )
    print(f"   Resolved: {substituted}")
    parent_ref = substituted.get("parentReference")
    if not isinstance(parent_ref, dict) or parent_ref.get("id") != "01SPARKTESTFOLDERID":
        print(f"   FAIL: expected parentReference.id=01SPARKTESTFOLDERID, got {parent_ref!r}")
        return False
    if substituted.get("driveItemId") != "01-source-file-id":
        print(f"   FAIL: driveItemId mutated unexpectedly: {substituted!r}")
        return False
    print(
        "   PASS — nested predicate placeholder resolved, parentReference.id is the real folder id"
    )
    return True


def test_unresolved_nested_placeholder_emits_warning_and_drops_param() -> bool:
    """Recursive leftover stripping: a non-required top-level dict whose
    nested leaf is still a literal `{{...}}` must be DROPPED (not passed
    to MCP) AND a `placeholder.unresolved` warning event must be emitted."""
    print("\n4. Leftover-strip — nested unresolved placeholder drops parent + emits warning")
    agent = _fresh_agent()
    captured = _capture_observability_events()

    cleaned = agent._strip_leftover_placeholder_parameters(
        parameters={
            "driveItemId": "01-real-id",
            "optionalParent": {"id": "{{MISSING.id}}"},
            "subject": "OK",
        },
        required_params=["driveItemId"],
        tool_name="ms365-mcp__move-rename-onedrive-item",
    )

    print(f"   Cleaned: {cleaned}")
    if "optionalParent" in cleaned:
        print(f"   FAIL: optionalParent should have been dropped, got {cleaned!r}")
        return False
    if cleaned.get("driveItemId") != "01-real-id" or cleaned.get("subject") != "OK":
        print(f"   FAIL: untouched params got mangled: {cleaned!r}")
        return False

    warning_events = [
        evt
        for evt in captured
        if evt["data"]
        and isinstance(evt["data"], dict)
        and evt["data"].get("phase") == "placeholder.unresolved"
    ]
    if not warning_events:
        print("   FAIL: no `placeholder.unresolved` AGENT_PLANNING event emitted")
        return False
    event = warning_events[0]
    unresolved = event["data"].get("unresolved", [])
    paths = {leaf["param_path"] for leaf in unresolved if isinstance(leaf, dict)}
    if "optionalParent.id" not in paths:
        print(f"   FAIL: warning event missing optionalParent.id, got paths={paths!r}")
        return False
    print(f"   PASS — non-required parent dropped, warning paths={sorted(paths)}")
    return True


def test_required_nested_unresolved_triggers_repair_plan() -> bool:
    """`_has_resolved_required_parameter_value` must report a required dict
    with a nested unresolved placeholder leaf as unresolved, so the
    existing repair-plan machinery (in the agent execution loop) fires."""
    print("\n5. Repair-plan trigger — required dict with nested unresolved is reported missing")
    agent = _fresh_agent()
    full_schema = MOVE_PARAM_SCHEMA
    param_properties = MOVE_PARAM_PROPERTIES

    parameters = {
        "driveItemId": "01-real-id",
        "parentReference": {"id": "{{MISSING.id}}"},  # nested unresolved
    }
    unresolved = agent._get_unresolved_required_parameters(
        parameters=parameters,
        required_params=["driveItemId", "parentReference"],
        param_properties=param_properties,
        full_schema=full_schema,
    )
    print(f"   Unresolved required: {unresolved}")
    if unresolved != ["parentReference"]:
        print(f"   FAIL: expected ['parentReference'], got {unresolved!r}")
        return False
    print("   PASS — nested unresolved leaf flags the required param as missing")
    return True


def test_index_predicate_combined_with_nested_dict() -> bool:
    """Combined regression: integer index inside a nested-dict placeholder.
    This is the worst-case combination of both v0.20260418.0 bugs.

    Plan: move a file into "the first folder result" (e.g. user said
    "move it into whatever folder comes first alphabetically").
    """
    print("\n6. Combined — `[0]` integer index inside nested `parentReference: {id: ...}`")
    agent = _fresh_agent()
    my_results = _make_results("{{FOLDER_RESULTS}}", MS365_FOLDER_SEARCH_PAYLOAD)

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "driveItemId": "01-source-file-id",
            "parentReference": {"id": "{{FOLDER_RESULTS[0].id}}"},
        },
        param_properties=MOVE_PARAM_PROPERTIES,
        full_schema=MOVE_PARAM_SCHEMA,
        action_description="Move the file into the first matching folder",
        my_results=my_results,
        tool_name="ms365-mcp__move-rename-onedrive-item",
    )
    print(f"   Resolved: {substituted}")
    parent_ref = substituted.get("parentReference")
    if not isinstance(parent_ref, dict) or parent_ref.get("id") != "01ATTACHMENTSFOLDERID":
        print(f"   FAIL: expected parentReference.id=01ATTACHMENTSFOLDERID, got {parent_ref!r}")
        return False
    print("   PASS — integer index resolved inside nested dict, no literal `{{...}}` reached MCP")
    return True


async def main() -> int:
    print("=" * 70)
    print("Test 7a6: Nested + integer-index placeholder resolution")
    print("=" * 70)

    start = time.time()
    original_observe = observability.observe
    try:
        results = [
            ("integer_index_first_worksheet", test_integer_index_resolves_first_worksheet()),
            ("integer_index_negative", test_negative_integer_index_resolves_last_worksheet()),
            ("nested_dict_predicate", test_nested_dict_placeholder_substitution()),
            (
                "leftover_strip_emits_warning",
                test_unresolved_nested_placeholder_emits_warning_and_drops_param(),
            ),
            (
                "required_nested_triggers_repair",
                test_required_nested_unresolved_triggers_repair_plan(),
            ),
            ("index_inside_nested_dict", test_index_predicate_combined_with_nested_dict()),
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
        print("  - `[N]` integer-index syntax resolves positional records")
        print("  - Negative `[-N]` index resolves from the tail")
        print("  - Nested-dict placeholders substitute via recursive walk")
        print("  - Unresolved nested leaves emit `placeholder.unresolved` warning + drop parent")
        print("  - Required dict with nested unresolved triggers repair-plan flow")
        print("  - Combined `[N]` inside nested dict resolves correctly end-to-end")
        print("\n" + "=" * 70)
        print("\n### Chat transcript:\n")
        print("  User: Move the file into the Spark Test folder")
        print(
            "  Planner (today): emits "
            "`parentReference: {id: \"{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}\"}`"
        )
        print("  Runtime: recursive substitution resolves the nested predicate to 01SPARK...")
        print("  MCP: move-rename-onedrive-item({parentReference: {id: 01SPARK...}}) succeeds")
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
