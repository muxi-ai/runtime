"""Focused tests for agent planning helper guardrails."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.formation.agents.agent import Agent
from muxi.runtime.services import observability


def test_a2a_tasks_only_bypass_planning_when_no_tools_are_available():
    agent = object.__new__(Agent)

    assert agent._should_bypass_planning(is_a2a_task=True, tools=[]) is True
    assert agent._should_bypass_planning(is_a2a_task=True, tools=[{"function": {}}]) is False
    assert agent._should_bypass_planning(is_a2a_task=False, tools=[]) is False


# ---------------------------------------------------------------------------
# v0.20260416.3 regression tests
# ---------------------------------------------------------------------------


def test_is_sentinel_placeholder_value_matches_llm_invented_tokens():
    """Dev #1 Excel: the planner emits 'auto-injected' etc. when it expects
    the runtime to inject a required parameter.  These values must be
    treated as unresolved so MCP server defaults can overwrite them."""
    assert Agent._is_sentinel_placeholder_value("auto-injected") is True
    assert Agent._is_sentinel_placeholder_value("AUTO_INJECTED") is True
    assert Agent._is_sentinel_placeholder_value("from_server") is True
    assert Agent._is_sentinel_placeholder_value("from-context") is True
    assert Agent._is_sentinel_placeholder_value("server_default") is True
    assert Agent._is_sentinel_placeholder_value("<to-be-injected>") is True
    assert Agent._is_sentinel_placeholder_value("to_be_provided") is True
    # Real values must not trigger.
    assert Agent._is_sentinel_placeholder_value("b!actual-drive-id-value") is False
    assert Agent._is_sentinel_placeholder_value("primary") is False
    assert Agent._is_sentinel_placeholder_value("") is False
    assert Agent._is_sentinel_placeholder_value(None) is False


def test_merge_parameter_candidates_overrides_sentinel_placeholder_values():
    """Regression for v0.20260416.2 Dev #1 Excel driveId bug: when the LLM
    emits `{"driveId": "auto-injected"}`, the real value from MCP server
    defaults must win in _merge_parameter_candidates."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    merged = agent._merge_parameter_candidates(
        current_parameters={"driveId": "auto-injected"},
        candidate_parameters={"driveId": "b!real-drive-id"},
        param_properties={"driveId": {"type": "string"}},
        full_schema={
            "type": "object",
            "required": ["driveId"],
            "properties": {"driveId": {"type": "string"}},
        },
    )

    assert merged["driveId"] == "b!real-drive-id"


def test_get_unresolved_required_parameters_flags_sentinel_placeholder_values():
    """Sentinel values must count as unresolved so the inference / server
    default pipeline gets a chance to replace them."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    unresolved = agent._get_unresolved_required_parameters(
        parameters={"driveId": "auto-injected"},
        required_params=["driveId"],
        param_properties={"driveId": {"type": "string"}},
        full_schema={
            "required": ["driveId"],
            "properties": {"driveId": {"type": "string"}},
        },
    )
    assert unresolved == ["driveId"]


def test_substitute_step_parameter_placeholders_strips_dot_field_suffix():
    """Regression for BUG-3: `{{SPARK_EVENT.event_id}}` must be resolved by
    stripping the `.event_id` suffix, looking up `{{SPARK_EVENT}}`, and
    extracting the `event_id` field from that step's payload."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    my_results = {
        "{{SPARK_EVENT}}": {
            "status": "success",
            "result": {
                "structured_content": {
                    "events": [
                        {
                            "event_id": "rl5p13b7jgd570rlph28stpaug",
                            "summary": "Spark Test",
                            "start_time": "2026-04-17T14:00:00+03:00",
                        }
                    ]
                },
            },
        }
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "update",
            "event_id": "{{SPARK_EVENT.event_id}}",
            "start_time": "2026-04-17T15:00:00+03:00",
        },
        param_properties={
            "event_id": {"type": "string"},
            "action": {"type": "string"},
            "start_time": {"type": "string"},
        },
        full_schema={},
        action_description="Update Spark Test event",
        my_results=my_results,
        tool_name="google-mcp__manage_event",
    )

    assert substituted["event_id"] == "rl5p13b7jgd570rlph28stpaug"
    assert substituted["action"] == "update"


def test_parse_placeholder_reference_splits_dotted_forms():
    """Unit coverage for the dotted placeholder parser."""
    base, field, predicate = Agent._parse_placeholder_reference("{{SPARK_EVENT.event_id}}")
    assert base == "{{SPARK_EVENT}}"
    assert field == "event_id"
    assert predicate is None

    base, field, predicate = Agent._parse_placeholder_reference("{{SPARK_EVENT}}")
    assert base == "{{SPARK_EVENT}}"
    assert field is None
    assert predicate is None

    base, field, predicate = Agent._parse_placeholder_reference("{{FOO.bar.baz}}")
    # Only a single-level field hint is supported.
    assert base == "{{FOO.bar.baz}}"
    assert field is None
    assert predicate is None


# ---------------------------------------------------------------------------
# v0.20260418.0 predicate-filter placeholder prototype
# ---------------------------------------------------------------------------


def test_parse_placeholder_reference_supports_quoted_string_predicate():
    """{{FILE_LIST[name='Book.xlsx'].id}} must split into base/field/predicate.

    This is the core shape that fixes the Excel "picks wrong record" bug:
    the LLM now has a deterministic way to say "the Book.xlsx record" when
    a prior step returned many records.
    """
    base, field, predicate = Agent._parse_placeholder_reference(
        "{{FILE_LIST[name='Book.xlsx'].id}}"
    )
    assert base == "{{FILE_LIST}}"
    assert field == "id"
    assert predicate == {"name": "Book.xlsx"}

    base, field, predicate = Agent._parse_placeholder_reference('{{FILE_LIST[name="Book.xlsx"]}}')
    assert base == "{{FILE_LIST}}"
    assert field is None
    assert predicate == {"name": "Book.xlsx"}


def test_parse_placeholder_predicate_accepts_all_scalar_value_types():
    """Predicate values may be quoted strings, bools, numbers, or bare words."""
    assert Agent._parse_placeholder_predicate("[name='Book.xlsx']") == {"name": "Book.xlsx"}
    assert Agent._parse_placeholder_predicate('[name="Book.xlsx"]') == {"name": "Book.xlsx"}
    assert Agent._parse_placeholder_predicate("[isFolder=true]") == {"isFolder": True}
    assert Agent._parse_placeholder_predicate("[isFolder=false]") == {"isFolder": False}
    assert Agent._parse_placeholder_predicate("[priority=1]") == {"priority": 1}
    assert Agent._parse_placeholder_predicate("[score=1.5]") == {"score": 1.5}
    assert Agent._parse_placeholder_predicate("[folder=null]") == {"folder": None}
    # Bare identifier value (for enum-like tags).
    assert Agent._parse_placeholder_predicate("[kind=file]") == {"kind": "file"}
    # Malformed forms must return None so the runtime can refuse substitution.
    assert Agent._parse_placeholder_predicate("[=missingkey]") is None
    assert Agent._parse_placeholder_predicate("[nokey]") is None
    assert Agent._parse_placeholder_predicate("[]") is None
    assert Agent._parse_placeholder_predicate("[bad key=1]") is None


def test_parse_placeholder_reference_rejects_malformed_predicate():
    """Malformed predicate degrades to legacy behavior so we don't silently
    pass a broken filter through to the record walker."""
    placeholder = "{{FILE_LIST[==].id}}"
    base, field, predicate = Agent._parse_placeholder_reference(placeholder)
    assert base == placeholder
    assert field is None
    assert predicate is None


def test_record_matches_predicate_normalizes_field_names_and_string_case():
    """Key variations (display_name vs Name vs name) and case differences on
    string values should not prevent a match — real Graph API payloads mix
    all three on the same record set."""
    record = {"Name": "Book.xlsx", "id": "abc123", "isFolder": False}
    assert Agent._record_matches_predicate(record, {"name": "Book.xlsx"}) is True
    assert Agent._record_matches_predicate(record, {"name": "book.xlsx"}) is True
    assert Agent._record_matches_predicate(record, {"name": "Other.xlsx"}) is False

    # Display-name style variant.
    record_display = {"displayName": "Quarterly Report", "id": "def456"}
    assert (
        Agent._record_matches_predicate(record_display, {"display_name": "Quarterly Report"})
        is True
    )
    assert (
        Agent._record_matches_predicate(record_display, {"displayname": "Quarterly Report"}) is True
    )

    # Boolean and numeric predicates.
    assert Agent._record_matches_predicate(record, {"isFolder": False}) is True
    assert Agent._record_matches_predicate(record, {"isFolder": True}) is False

    # Numeric coercion: integer predicate vs string value.
    assert Agent._record_matches_predicate({"priority": "42"}, {"priority": 42}) is True

    # None predicate matches absent/null fields.
    assert Agent._record_matches_predicate({"folder": None}, {"folder": None}) is True
    assert Agent._record_matches_predicate({"name": "x"}, {"folder": None}) is True
    assert Agent._record_matches_predicate({"folder": {"childCount": 0}}, {"folder": None}) is False


def test_extract_field_with_predicate_picks_correct_record_from_list():
    """Excel scenario (Dev #1 Failure Mode 1): list-folder-files returns
    [Attachments folder, Book.xlsx, ...]; without a predicate the extractor
    resolves .id to the first record (Attachments). With a name predicate,
    it must resolve to Book.xlsx."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = {
        "value": [
            {
                "id": "01SA7QZQ7HKJH6YEQPZNEY2JV3H7LXCTZU",
                "name": "Attachments",
                "folder": {"childCount": 3},
            },
            {
                "id": "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5",
                "name": "Book.xlsx",
                "file": {
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                },
            },
            {
                "id": "01SA7QZQZZZZZZZZZZZZZZZZZZZZZZZZ",
                "name": "Notes.docx",
                "file": {
                    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                },
            },
        ],
    }

    # No predicate — legacy behavior picks the first id (the folder).
    assert agent._extract_field_from_result_payload(payload, "id") == (
        "01SA7QZQ7HKJH6YEQPZNEY2JV3H7LXCTZU"
    )

    # With predicate — picks the Book.xlsx record's id.
    assert (
        agent._extract_field_from_result_payload(payload, "id", predicate={"name": "Book.xlsx"})
        == "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5"
    )

    # Predicate matches nothing → None.
    assert (
        agent._extract_field_from_result_payload(payload, "id", predicate={"name": "Missing.xlsx"})
        is None
    )

    # Predicate with no field requested → returns the matched record itself.
    match = agent._extract_field_from_result_payload(payload, None, predicate={"name": "Book.xlsx"})
    assert isinstance(match, dict)
    assert match["id"] == "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5"


def test_extract_field_with_predicate_skips_text_fallback():
    """Predicate mode must not scan free-text chunks — text payloads can't
    honor a structural predicate reliably (no per-record boundaries)."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = "- Name: Book.xlsx\n  ID: text-only-id\n"
    # Without predicate the text fallback locates the id.
    assert agent._extract_field_from_result_payload(payload, "id") == "text-only-id"
    # With predicate we must return None rather than guessing.
    assert (
        agent._extract_field_from_result_payload(payload, "id", predicate={"name": "Book.xlsx"})
        is None
    )


def test_filter_records_by_predicate_collects_all_matches():
    payload = {
        "items": [
            {"kind": "file", "name": "a.txt"},
            {"kind": "folder", "name": "docs"},
            {"kind": "file", "name": "b.txt"},
        ]
    }
    matches = Agent._filter_records_by_predicate(payload, {"kind": "file"}, collect_all=True)
    assert [record["name"] for record in matches] == ["a.txt", "b.txt"]


def test_substitute_step_parameter_placeholders_uses_predicate():
    """End-to-end: the placeholder substitution pipeline must honor the
    predicate when resolving `{{FILE_LIST[name='Book.xlsx'].id}}` against
    a prior step's payload."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{FILE_LIST}}": {
            "success": True,
            "result": {
                "value": [
                    {"id": "folder-id", "name": "Attachments", "folder": {}},
                    {"id": "workbook-id", "name": "Book.xlsx", "file": {}},
                ]
            },
        },
    }

    parameters = {"driveItemId": "{{FILE_LIST[name='Book.xlsx'].id}}"}
    param_properties = {"driveItemId": {"type": "string"}}
    full_schema = {
        "type": "object",
        "required": ["driveItemId"],
        "properties": {"driveItemId": {"type": "string"}},
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters=parameters,
        param_properties=param_properties,
        full_schema=full_schema,
        action_description="List all worksheets in Book.xlsx",
        my_results=my_results,
        tool_name="list-excel-worksheets",
    )
    assert substituted["driveItemId"] == "workbook-id"


# ---------------------------------------------------------------------------
# v0.20260418.0 Option 2 — auto-inferred name predicate from action
# ---------------------------------------------------------------------------


def test_extract_named_resource_from_action_prefers_quoted_strings():
    """Quoted/backticked references beat incidental filenames elsewhere."""
    # Double-quote wins over a filename further in the text.
    assert (
        Agent._extract_named_resource_from_action(
            'Open the "Quarterly Report" workbook, not Book.xlsx'
        )
        == "Quarterly Report"
    )
    # Single-quote resolves.
    assert (
        Agent._extract_named_resource_from_action("Find the event titled 'Team Standup'")
        == "Team Standup"
    )
    # Backtick-wrapped markdown span.
    assert (
        Agent._extract_named_resource_from_action("Open `Book.xlsx` from the root folder")
        == "Book.xlsx"
    )


def test_extract_named_resource_from_action_detects_unquoted_filenames():
    """Unquoted filenames with a recognized extension qualify as named resources."""
    assert (
        Agent._extract_named_resource_from_action("List files in the root folder to find Book.xlsx")
        == "Book.xlsx"
    )
    assert (
        Agent._extract_named_resource_from_action("Open quarterly-report.pdf for review")
        == "quarterly-report.pdf"
    )


def test_extract_named_resource_from_action_ignores_prose_without_markers():
    """Bare capitalized words must NOT qualify — too many false positives."""
    assert Agent._extract_named_resource_from_action("List all worksheets in the workbook") is None
    assert Agent._extract_named_resource_from_action("Get the root folder ID") is None
    assert Agent._extract_named_resource_from_action("") is None
    assert Agent._extract_named_resource_from_action(None) is None


def test_infer_auto_name_predicate_fires_for_ambiguous_multi_record_payload():
    """Dev #1 Excel scenario: action mentions Book.xlsx and the payload has
    multiple named records — auto-infer a ``{name: 'Book.xlsx'}`` predicate."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = {
        "value": [
            {"id": "folder-id", "name": "Attachments", "folder": {}},
            {"id": "workbook-id", "name": "Book.xlsx", "file": {}},
            {"id": "doc-id", "name": "Notes.docx", "file": {}},
        ]
    }
    inferred = agent._infer_auto_name_predicate(
        payload=payload,
        action_description="List files in the root folder to find Book.xlsx",
    )
    assert inferred == {"name": "Book.xlsx"}


def test_infer_auto_name_predicate_returns_none_without_ambiguity():
    """Single-record payloads don't need disambiguation."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = {"id": "only-record", "name": "Book.xlsx", "file": {}}
    assert (
        agent._infer_auto_name_predicate(
            payload=payload,
            action_description="Fetch Book.xlsx metadata",
        )
        is None
    )


def test_infer_auto_name_predicate_returns_none_when_named_resource_not_in_payload():
    """The guard prevents silently applying a predicate against a name the
    prior step never actually returned."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = {
        "value": [
            {"id": "f1", "name": "Attachments"},
            {"id": "f2", "name": "Notes.docx"},
        ]
    }
    assert (
        agent._infer_auto_name_predicate(
            payload=payload,
            action_description="List files to find Book.xlsx",
        )
        is None
    )


def test_infer_auto_name_predicate_adapts_to_displayname_field():
    """When records use ``displayName`` instead of ``name``, the synthesized
    predicate must use the same variant so downstream matching succeeds."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = {
        "value": [
            {"id": "a", "displayName": "Engineering"},
            {"id": "b", "displayName": "Marketing"},
        ]
    }
    inferred = agent._infer_auto_name_predicate(
        payload=payload,
        action_description="Open the 'Marketing' workspace",
    )
    assert inferred == {"displayName": "Marketing"}


def test_substitute_placeholders_auto_applies_predicate_from_action():
    """End-to-end: the Excel bug scenario without the LLM using the new
    predicate syntax — the runtime should still resolve to Book.xlsx by
    cross-referencing the action description."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{FILE_LIST}}": {
            "success": True,
            "result": {
                "value": [
                    {"id": "folder-id", "name": "Attachments", "folder": {}},
                    {"id": "workbook-id", "name": "Book.xlsx", "file": {}},
                ]
            },
        },
    }
    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST.id}}"},
        param_properties={"driveItemId": {"type": "string"}},
        full_schema={
            "type": "object",
            "required": ["driveItemId"],
            "properties": {"driveItemId": {"type": "string"}},
        },
        action_description="List all worksheet names in Book.xlsx",
        my_results=my_results,
        tool_name="list-excel-worksheets",
    )
    assert substituted["driveItemId"] == "workbook-id"


def test_substitute_placeholders_respects_explicit_predicate_over_auto():
    """When the LLM provides an explicit predicate, we must not override it
    with an auto-inferred one (LLM intent wins, even if action_description
    would synthesize something different)."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{FILE_LIST}}": {
            "success": True,
            "result": {
                "value": [
                    {"id": "attach-id", "name": "Attachments", "folder": {}},
                    {"id": "book-id", "name": "Book.xlsx", "file": {}},
                    {"id": "notes-id", "name": "Notes.docx", "file": {}},
                ]
            },
        },
    }
    # Action mentions Book.xlsx, but LLM explicitly asked for Notes.docx.
    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST[name='Notes.docx'].id}}"},
        param_properties={"driveItemId": {"type": "string"}},
        full_schema={
            "type": "object",
            "required": ["driveItemId"],
            "properties": {"driveItemId": {"type": "string"}},
        },
        action_description="Read sheets from Book.xlsx first",
        my_results=my_results,
        tool_name="open-document",
    )
    assert substituted["driveItemId"] == "notes-id"


def test_substitute_placeholders_falls_back_to_legacy_without_named_resource():
    """When action_description has no quoted/filename-extension token, the
    auto-predicate must NOT fire — preserves legacy behavior for plans that
    don't lean on named-resource context."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{FILE_LIST}}": {
            "success": True,
            "result": {
                "value": [
                    {"id": "first-id", "name": "Alpha"},
                    {"id": "second-id", "name": "Beta"},
                ]
            },
        },
    }
    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveItemId": "{{FILE_LIST.id}}"},
        param_properties={"driveItemId": {"type": "string"}},
        full_schema={
            "type": "object",
            "required": ["driveItemId"],
            "properties": {"driveItemId": {"type": "string"}},
        },
        action_description="Pass the first result id to the next step",
        my_results=my_results,
        tool_name="open-document",
    )
    # Falls back to the first record's id — legacy behavior preserved.
    assert substituted["driveItemId"] == "first-id"


def test_resolve_parameter_from_result_payload_does_not_return_whole_payload():
    """Regression for BUG-4: when a hallucinated param (not in the tool
    schema) can't be resolved from any record field, we must return None
    instead of the entire payload object — otherwise the whole result dict
    gets passed to MCP and fails pydantic validation."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    payload = {
        "result": "Successfully listed 2 calendars for oleksandra.bondaruk@automaze.io...",
    }

    # `user_google_email` is NOT in the manage_event schema, so param_def is {}.
    resolved = agent._resolve_parameter_from_result_payload(
        param_name="user_google_email",
        payload=payload,
        param_properties={},
        full_schema={},
        action_description="Create meeting with attendees",
        tool_name="google-mcp__manage_event",
    )

    assert resolved is None


def test_resolve_parameter_from_result_payload_still_returns_scalar_for_scalar_schema():
    """The tightened fallback must still work for legitimate scalar params
    whose schema is known."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    resolved = agent._resolve_parameter_from_result_payload(
        param_name="channel_id",
        payload="C0123456",  # scalar payload, string schema
        param_properties={"channel_id": {"type": "string"}},
        full_schema={"properties": {"channel_id": {"type": "string"}}},
        action_description="Send message to channel",
        tool_name="slack-mcp__send_message",
    )

    assert resolved == "C0123456"


def test_planning_response_synthesis_prompt_preserves_exact_dates_from_results():
    agent = object.__new__(Agent)
    my_results = {
        "{MAIL_OUTPUT}": {
            "result": {
                "content": "Spark Devs group welcome — Received today at 5:16 PM.",
                "structured_content": {
                    "messages": [
                        {
                            "subject": "You've joined the Spark Devs group",
                            "receivedDateTime": "2026-03-23T17:16:44Z",
                        }
                    ]
                },
            },
            "status": "success",
        }
    }

    prompt = agent._build_planning_response_synthesis_prompt(
        "Do I have any emails?", my_results, []
    )

    assert "2026-03-23T17:16:44Z" in prompt
    assert "Preserve explicit dates, weekdays, times, and time ranges exactly as given." in prompt
    assert "Do not turn absolute dates into relative words like 'today' or 'recently'" in prompt


def test_finalize_execution_plan_strips_delegate_steps_when_delegation_is_disabled():
    agent = object.__new__(Agent)
    plan = {
        "steps": [
            {
                "action": "Get current user profile",
                "tool_name": "ms365__get-current-user",
                "can_i_do_this": False,
                "delegation_prompt": "Ask ms365-assistant for the current user profile",
            }
        ]
    }

    finalized = agent._finalize_execution_plan(
        plan, {"ms365__get-current-user"}, allow_delegation=False
    )

    assert finalized["delegate_steps"] == []
    assert finalized["my_steps"][0]["tool_name"] == "ms365__get-current-user"


def test_finalize_execution_plan_prefers_local_tools_over_delegation():
    agent = object.__new__(Agent)
    plan = {
        "steps": [
            {
                "action": "List all worksheets in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
                "can_i_do_this": False,
                "capability_needed": "Excel worksheet listing",
                "delegation_prompt": "Find and list all worksheets in Book.xlsx",
            }
        ]
    }

    finalized = agent._finalize_execution_plan(
        plan, {"ms365-mcp__list-excel-worksheets"}, allow_delegation=True
    )

    assert finalized["steps"][0]["can_i_do_this"] is True
    assert finalized["delegate_steps"] == []
    assert finalized["my_steps"][0]["tool_name"] == "ms365-mcp__list-excel-worksheets"


def test_finalize_execution_plan_preserves_step_parameters():
    agent = object.__new__(Agent)
    plan = {
        "steps": [
            {
                "action": "Find workbook in folder",
                "tool_name": "ms365__list-folder-files",
                "can_i_do_this": True,
                "parameters": {"driveId": "drive-123", "searchQuery": "Book.xlsx"},
                "output_placeholder": "{{FILE_LOOKUP}}",
            }
        ]
    }

    finalized = agent._finalize_execution_plan(
        plan, {"ms365__list-folder-files"}, allow_delegation=False
    )

    assert finalized["my_steps"][0]["parameters"] == {
        "driveId": "drive-123",
        "searchQuery": "Book.xlsx",
    }


def test_finalize_execution_plan_preserves_parameters_from_llm_my_steps():
    """The LLM emits parameters in the separate my_steps block (per the planning
    prompt template). _finalize_execution_plan rebuilds my_steps from steps and
    must pull parameters out of the LLM's my_steps entry keyed by tool_name.
    Regression for v0.20260416.0 Bug #1 (planning strips all tool parameters)."""
    agent = object.__new__(Agent)
    # This mirrors the exact shape produced by the planning LLM.  "steps" has
    # no parameters field; "my_steps" has the full parameter set.
    plan = {
        "steps": [
            {
                "step_number": 1,
                "action": "Retrieve tomorrow's events from Google Calendar",
                "capability_needed": "Google Calendar access",
                "tool_name": "google-mcp__get_events",
                "can_i_do_this": True,
                "data_needed": "none",
                "output_placeholder": "{{TOMORROW_EVENTS}}",
            }
        ],
        "my_steps": [
            {
                "action": "Get events from Google Calendar for tomorrow",
                "tool_name": "google-mcp__get_events",
                "parameters": {
                    "calendar_id": "primary",
                    "time_min": "2026-04-17T00:00:00+03:00",
                    "time_max": "2026-04-17T23:59:59+03:00",
                    "detailed": True,
                },
                "output_placeholder": "{{TOMORROW_EVENTS}}",
            }
        ],
        "delegate_steps": [],
        "data_flow": "Fetch tomorrow's calendar events.",
    }

    finalized = agent._finalize_execution_plan(
        plan, {"google-mcp__get_events"}, allow_delegation=False
    )

    assert len(finalized["my_steps"]) == 1
    assert finalized["my_steps"][0]["parameters"] == {
        "calendar_id": "primary",
        "time_min": "2026-04-17T00:00:00+03:00",
        "time_max": "2026-04-17T23:59:59+03:00",
        "detailed": True,
    }


def test_finalize_execution_plan_preserves_parameters_across_repeated_tool_use():
    """When the same tool is used in multiple planned steps, parameters must be
    matched by position within the tool's queue so each step keeps its own
    params (not shared or swapped)."""
    agent = object.__new__(Agent)
    plan = {
        "steps": [
            {
                "step_number": 1,
                "action": "Create morning event",
                "tool_name": "google-mcp__manage_event",
                "can_i_do_this": True,
                "output_placeholder": "{{EVENT_A}}",
            },
            {
                "step_number": 2,
                "action": "Create afternoon event",
                "tool_name": "google-mcp__manage_event",
                "can_i_do_this": True,
                "output_placeholder": "{{EVENT_B}}",
            },
        ],
        "my_steps": [
            {
                "action": "Create morning event",
                "tool_name": "google-mcp__manage_event",
                "parameters": {
                    "action": "create",
                    "summary": "Morning Standup",
                    "start_time": "2026-04-17T09:00:00+03:00",
                    "end_time": "2026-04-17T09:30:00+03:00",
                },
                "output_placeholder": "{{EVENT_A}}",
            },
            {
                "action": "Create afternoon event",
                "tool_name": "google-mcp__manage_event",
                "parameters": {
                    "action": "create",
                    "summary": "Design Review",
                    "start_time": "2026-04-17T14:00:00+03:00",
                    "end_time": "2026-04-17T15:00:00+03:00",
                },
                "output_placeholder": "{{EVENT_B}}",
            },
        ],
        "delegate_steps": [],
        "data_flow": "Create two events back to back.",
    }

    finalized = agent._finalize_execution_plan(
        plan, {"google-mcp__manage_event"}, allow_delegation=False
    )

    assert len(finalized["my_steps"]) == 2
    assert finalized["my_steps"][0]["parameters"]["summary"] == "Morning Standup"
    assert finalized["my_steps"][1]["parameters"]["summary"] == "Design Review"


def test_finalize_execution_plan_preserves_my_steps_when_steps_is_empty():
    """Regression for v0.20260426.0 Bug #1: 'create a one-page pdf about muxi'.

    Some LLMs (notably Haiku) interpret the planning prompt's
    "ALL steps MUST go in my_steps" line literally and emit
    ``{"steps": [], "my_steps": [...]}`` — populating my_steps with the
    actual actions but leaving the canonical ``steps`` array empty.

    Before the fix, ``_finalize_execution_plan`` rebuilt my_steps by
    iterating ``plan["steps"]``, which produced an empty list and
    silently overwrote the LLM's actual actions. The agent then went on
    to generate a narrative response describing the work it never
    performed (no ``tool.invoked`` events fired, no artifact returned).

    After the fix, when ``steps`` is empty but ``my_steps`` has at least
    one entry with a known tool name, ``my_steps`` is treated as the
    canonical action list — params and placeholders are kept verbatim,
    unknown tools are dropped to avoid downstream "tool not found"
    errors, and the rebuilt list reaches the executor unchanged.
    """
    agent = object.__new__(Agent)

    plan = {
        "steps": [],
        "my_steps": [
            {
                "action": "Activate file-generation skill",
                "tool_name": "activate_skill",
                "parameters": {"skill_name": "file-generation"},
                "output_placeholder": "{{SKILL_ACTIVATED}}",
            },
            {
                "action": "Generate one-page PDF about MUXI",
                "tool_name": "generate_file",
                "parameters": {
                    "code": "from reportlab.lib.pagesizes import letter\n# ...",
                },
                "output_placeholder": "{{PDF}}",
            },
            # An unknown tool the LLM hallucinated — must be dropped, not
            # passed to the executor where it would error out.
            {
                "action": "Hallucinated step",
                "tool_name": "nonexistent_tool",
                "parameters": {},
                "output_placeholder": "{{IGNORED}}",
            },
        ],
        "delegate_steps": [],
        "data_flow": "Activate skill → generate PDF",
    }

    available = {"activate_skill", "generate_file"}

    finalized = agent._finalize_execution_plan(plan, available, allow_delegation=False)

    # The two valid actions must be preserved verbatim — same order, same
    # parameters, same placeholders.
    assert len(finalized["my_steps"]) == 2

    first, second = finalized["my_steps"]
    assert first["tool_name"] == "activate_skill"
    assert first["parameters"] == {"skill_name": "file-generation"}
    assert first["output_placeholder"] == "{{SKILL_ACTIVATED}}"

    assert second["tool_name"] == "generate_file"
    assert second["parameters"]["code"].startswith("from reportlab")
    assert second["output_placeholder"] == "{{PDF}}"

    # The hallucinated tool must NOT have leaked through.
    rebuilt_tools = {s["tool_name"] for s in finalized["my_steps"]}
    assert "nonexistent_tool" not in rebuilt_tools


def test_finalize_execution_plan_does_not_invent_my_steps_when_both_empty():
    """When both ``steps`` and ``my_steps`` are empty (the LLM legitimately
    determined no tools are needed), the finalizer must NOT manufacture
    actions out of thin air. Empty plan in → empty plan out."""
    agent = object.__new__(Agent)

    plan = {
        "steps": [],
        "my_steps": [],
        "delegate_steps": [],
        "data_flow": "Direct response - no tools needed",
    }

    finalized = agent._finalize_execution_plan(
        plan, {"some_tool", "another_tool"}, allow_delegation=False
    )

    assert finalized["my_steps"] == []
    assert finalized.get("delegate_steps") == []


def test_finalize_execution_plan_steps_authoritative_when_both_populated():
    """Existing contract is preserved: when ``steps`` is populated, it
    remains canonical and we keep using it to rebuild ``my_steps``
    (matching parameters from the LLM's my_steps by tool name). Only the
    ``steps:[]`` / ``my_steps:[...]`` *recovery path* is new."""
    agent = object.__new__(Agent)

    plan = {
        "steps": [
            {
                "step_number": 1,
                "action": "Read config",
                "tool_name": "fs__read_file",
                "can_i_do_this": True,
                "output_placeholder": "{{CONFIG}}",
            }
        ],
        "my_steps": [
            {
                "action": "Read config",
                "tool_name": "fs__read_file",
                "parameters": {"path": "/etc/muxi/config.yaml"},
                "output_placeholder": "{{CONFIG}}",
            },
            # An extra entry only present in my_steps that's NOT in steps
            # must NOT smuggle into the rebuilt plan when steps is the
            # canonical list — that's the existing contract.
            {
                "action": "Sneaky extra action",
                "tool_name": "fs__write_file",
                "parameters": {"path": "/tmp/x", "content": "hi"},
                "output_placeholder": "{{IGNORED}}",
            },
        ],
        "delegate_steps": [],
        "data_flow": "Read the file.",
    }

    finalized = agent._finalize_execution_plan(
        plan, {"fs__read_file", "fs__write_file"}, allow_delegation=False
    )

    assert len(finalized["my_steps"]) == 1
    assert finalized["my_steps"][0]["tool_name"] == "fs__read_file"
    assert finalized["my_steps"][0]["parameters"] == {"path": "/etc/muxi/config.yaml"}
    # Sneaky extra didn't smuggle in.
    rebuilt_tools = {s["tool_name"] for s in finalized["my_steps"]}
    assert "fs__write_file" not in rebuilt_tools


@pytest.mark.asyncio
async def test_plan_before_execution_injects_current_date_into_planning_prompt():
    """Regression for v0.20260416.0 Bug #2: the planning LLM never sees the
    current date.  The planner must be able to resolve 'today' / 'tomorrow'
    into concrete dates without the user manually providing them."""
    agent = object.__new__(Agent)
    agent.name = "Test Agent"
    agent.agent_id = "test-agent"
    agent.overlord = None
    agent.system_message = None
    agent.model = SimpleNamespace(
        chat=AsyncMock(
            return_value=(
                '{"steps":[],"my_steps":[],"delegate_steps":[],'
                '"data_flow":"Direct response - no tools needed"}'
            )
        )
    )

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
        patch("muxi.runtime.formation.prompts.loader.PromptLoader.get", return_value=""),
    ):
        await agent._plan_before_execution(
            "what are my events for tomorrow?",
            available_tools=[],
            allow_delegation=False,
        )

    planning_messages = agent.model.chat.call_args.args[0]
    planning_prompt = planning_messages[1]["content"]
    assert "## Current date/time:" in planning_prompt
    assert "It is now" in planning_prompt
    # Must instruct the planner to resolve relative references.
    assert "tomorrow" in planning_prompt.lower() or "relative" in planning_prompt.lower()


def test_extract_current_request_text_preserves_context_lines_when_requested():
    message = (
        "=== CURRENT REQUEST ===\n"
        "User: What sheets do I have in Book.xlsx?\n"
        "[Context: driveId = drive-123. Use this directly.]\n\n"
        "=== RECENT CONVERSATION ===\n"
        "User: Hi"
    )

    assert Agent._extract_current_request_text(message) == "What sheets do I have in Book.xlsx?"
    assert Agent._extract_current_request_text(message, include_context_lines=True) == (
        "What sheets do I have in Book.xlsx?\n" "[Context: driveId = drive-123. Use this directly.]"
    )


def test_extract_explicit_parameter_values_from_text_ignores_placeholder_values():
    resolved = Agent._extract_explicit_parameter_values_from_text(
        "[Context: driveId = {{DRIVE_ID}}. Use this directly.]",
        ["driveId"],
    )

    assert resolved == {}


@pytest.mark.asyncio
async def test_plan_before_execution_includes_required_params_in_prompt():
    agent = object.__new__(Agent)
    agent.name = "Test Agent"
    agent.agent_id = "test-agent"
    agent.overlord = None
    agent.model = SimpleNamespace(
        chat=AsyncMock(
            return_value='{"steps":[],"my_steps":[],"delegate_steps":[],"data_flow":"Direct response - no tools needed"}'
        )
    )

    available_tools = [
        {
            "function": {
                "name": "ms365-mcp__list-excel-worksheets",
                "description": "List all worksheets in an Excel workbook.",
                "parameters": {
                    "type": "object",
                    "required": ["driveId", "driveItemId"],
                    "properties": {
                        "driveId": {"type": "string"},
                        "driveItemId": {"type": "string"},
                    },
                },
            }
        }
    ]

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
        patch("muxi.runtime.formation.prompts.loader.PromptLoader.get", return_value=""),
    ):
        await agent._plan_before_execution(
            "What sheets do I have in Book.xlsx?",
            available_tools=available_tools,
            allow_delegation=False,
        )

    planning_messages = agent.model.chat.call_args.args[0]
    planning_prompt = planning_messages[1]["content"]
    assert "Required params: driveId, driveItemId." in planning_prompt


@pytest.mark.asyncio
async def test_plan_before_execution_includes_agent_instructions_and_context():
    agent = object.__new__(Agent)
    agent.name = "Test Agent"
    agent.agent_id = "test-agent"
    agent.system_message = "driveId is known. NEVER call list-drives."
    agent.overlord = None
    agent.model = SimpleNamespace(
        chat=AsyncMock(
            return_value='{"steps":[],"my_steps":[],"delegate_steps":[],"data_flow":"Direct response - no tools needed"}'
        )
    )

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
        patch("muxi.runtime.formation.prompts.loader.PromptLoader.get", return_value=""),
    ):
        await agent._plan_before_execution(
            "What sheets do I have in Book.xlsx?\n[Context: driveId = drive-123]",
            available_tools=[],
            allow_delegation=False,
        )

    planning_messages = agent.model.chat.call_args.args[0]
    planning_prompt = planning_messages[1]["content"]
    assert "NEVER call list-drives" in planning_prompt
    assert "[Context: driveId = drive-123]" in planning_prompt


@pytest.mark.asyncio
async def test_infer_tool_parameters_rejects_blank_required_string_values():
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent.model = SimpleNamespace(
        chat=AsyncMock(return_value='{"driveId":"drive-123","driveItemId":""}')
    )

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        parameters = await agent._infer_tool_parameters(
            tool_name="ms365-mcp__list-excel-worksheets",
            required_params=["driveId", "driveItemId"],
            param_properties={
                "driveId": {"type": "string", "description": "The drive id"},
                "driveItemId": {"type": "string", "description": "The drive item id"},
            },
            full_schema={
                "type": "object",
                "properties": {
                    "driveId": {"type": "string", "description": "The drive id"},
                    "driveItemId": {"type": "string", "description": "The drive item id"},
                },
                "required": ["driveId", "driveItemId"],
            },
            action_description="List worksheets in the workbook",
            user_request="What sheets do I have in Book.xlsx?",
        )

    assert parameters == {}


def test_is_tool_execution_error_detects_mcp_error_shapes():
    agent = object.__new__(Agent)

    assert agent._is_tool_execution_error({"status": "error", "error": "boom"}) is True
    assert (
        agent._is_tool_execution_error(
            {"status": "success", "result": {"isError": True, "content": "nope"}}
        )
        is True
    )
    assert (
        agent._is_tool_execution_error(
            {"status": "success", "result": {"isError": False, "content": "ok"}}
        )
        is False
    )


def test_has_resolved_required_parameter_value_rejects_placeholder_strings():
    agent = object.__new__(Agent)
    param_def = {"type": "string"}

    assert agent._has_resolved_required_parameter_value("{{ROOT_FOLDER_ID}}", param_def) is False
    assert agent._has_resolved_required_parameter_value("<<ROOT_FOLDER_ID>>", param_def) is False
    assert agent._has_resolved_required_parameter_value("{ROOT_FOLDER_ID}", param_def) is False
    assert agent._has_resolved_required_parameter_value("drive-123", param_def) is True


@pytest.mark.asyncio
async def test_invoke_tool_logs_success_false_for_mcp_error_result():
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent.overlord = None
    agent.request_timeout = 30
    agent._messages = []
    agent._mcp_service = SimpleNamespace(
        invoke_tool=AsyncMock(
            return_value={
                "status": "error",
                "result": {
                    "isError": True,
                    "content": '{"error":"Microsoft Graph API error: 404 Not Found"}',
                },
            }
        )
    )

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe") as observe,
    ):
        result = await agent.invoke_tool(
            tool_name="list-excel-worksheets",
            parameters={"driveId": "drive-123", "driveItemId": ""},
            server_id="ms365-mcp",
            user_id="tester",
        )

    assert result["status"] == "error"
    completion_events = [
        call.kwargs
        for call in observe.call_args_list
        if call.kwargs.get("event_type") == observability.ConversationEvents.MCP_TOOL_CALL_COMPLETED
    ]
    assert completion_events
    assert completion_events[-1]["data"]["success"] is False


@pytest.mark.asyncio
async def test_process_message_executes_parameter_free_planned_tool_without_unbound_defaults():
    """Parameter-free planned MCP steps should not crash before invoke_tool runs."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"
    agent.name = "MS365 Assistant"
    agent.model = SimpleNamespace()
    agent.system_message = "You are a helpful assistant."
    agent._messages = []
    agent._knowledge_config = None
    agent._mcp_service = SimpleNamespace(
        server_configs={"ms365-mcp": {"parameters": {"userId": "me"}}}
    )
    agent.overlord = SimpleNamespace(
        mcp_service=SimpleNamespace(
            get_tool_registry=lambda _agent_id: {
                "ms365-mcp": {
                    "list-mail-messages": {
                        "description": "List mail messages from the mailbox.",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                }
            }
        )
    )
    agent.invoke_tool = AsyncMock(return_value={"status": "success", "result": "[]"})
    agent._plan_before_execution = AsyncMock(
        return_value={
            "steps": [
                {
                    "step_number": 1,
                    "action": "List mail messages in the mailbox",
                    "tool_name": "ms365-mcp__list-mail-messages",
                    "can_i_do_this": True,
                    "output_placeholder": "{{EMAIL_LIST}}",
                }
            ],
            "my_steps": [
                {
                    "action": "List mail messages in the mailbox",
                    "tool_name": "ms365-mcp__list-mail-messages",
                    "parameters": {},
                    "output_placeholder": "{{EMAIL_LIST}}",
                }
            ],
            "delegate_steps": [],
            "data_flow": "List mailbox contents and summarize the result.",
        }
    )
    agent._synthesize_planning_execution_response = AsyncMock(
        return_value="You have messages in your mailbox."
    )
    agent._check_cancellation = AsyncMock()

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
    ):
        response = await agent.process_message(
            "Do I have any emails?",
            user_id="tester",
            session_id="sess_123",
            request_id="req_123",
        )

    assert response.content == "You have messages in your mailbox."
    agent.invoke_tool.assert_awaited_once_with(
        tool_name="list-mail-messages",
        parameters={},
        server_id="ms365-mcp",
        user_id="tester",
    )


@pytest.mark.asyncio
async def test_process_message_blocks_unresolved_nonrequired_placeholder_before_execution():
    """Planner-authored placeholder dependencies must block execution even
    when the tool schema marks the parameter optional."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"
    agent.name = "Google Assistant"
    agent.model = SimpleNamespace()
    agent.system_message = "You are a helpful assistant."
    agent._messages = []
    agent._knowledge_config = None
    agent._mcp_service = SimpleNamespace(server_configs={})
    agent.overlord = SimpleNamespace(
        mcp_service=SimpleNamespace(
            get_tool_registry=lambda _agent_id: {
                "google-mcp": {
                    "manage_event": {
                        "description": "Update or delete a calendar event.",
                        "inputSchema": {
                            "type": "object",
                            "required": ["action"],
                            "properties": {
                                "action": {"type": "string"},
                                "event_id": {"type": "string"},
                                "start_time": {"type": "string"},
                                "end_time": {"type": "string"},
                            },
                        },
                    }
                }
            }
        )
    )
    agent.invoke_tool = AsyncMock(return_value={"status": "success", "result": "should-not-run"})
    agent._plan_before_execution = AsyncMock(
        return_value={
            "steps": [
                {
                    "step_number": 1,
                    "action": "Reschedule Spark Test 2",
                    "tool_name": "google-mcp__manage_event",
                    "can_i_do_this": True,
                    "output_placeholder": "{{UPDATE_RESULT}}",
                }
            ],
            "my_steps": [
                {
                    "action": "Reschedule Spark Test 2",
                    "tool_name": "google-mcp__manage_event",
                    "parameters": {
                        "action": "update",
                        "event_id": "{{EVENT_SEARCH[summary='Spark Test 2'].id}}",
                        "start_time": "2026-04-22T10:00:00+03:00",
                        "end_time": "2026-04-22T10:45:00+03:00",
                    },
                    "output_placeholder": "{{UPDATE_RESULT}}",
                }
            ],
            "delegate_steps": [],
            "data_flow": "Update the event after resolving its id.",
        }
    )
    agent._repair_execution_plan_for_missing_parameters = AsyncMock(return_value=None)
    agent._synthesize_planning_execution_response = AsyncMock(return_value="Blocked placeholder.")
    agent._check_cancellation = AsyncMock()

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
    ):
        response = await agent.process_message(
            "Reschedule Spark Test 2 to tomorrow at 10:00.",
            user_id="tester",
            session_id="sess_123",
            request_id="req_123",
        )

    assert response.content == "Blocked placeholder."
    agent.invoke_tool.assert_not_awaited()
    agent._repair_execution_plan_for_missing_parameters.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_message_blocks_unknown_schema_params_before_execution():
    """Unknown planner params must trigger repair instead of being sent to MCP."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"
    agent.name = "Google Assistant"
    agent.model = SimpleNamespace()
    agent.system_message = "You are a helpful assistant."
    agent._messages = []
    agent._knowledge_config = None
    agent._mcp_service = SimpleNamespace(server_configs={})
    agent.overlord = SimpleNamespace(
        mcp_service=SimpleNamespace(
            get_tool_registry=lambda _agent_id: {
                "google-mcp": {
                    "manage_gmail_filter": {
                        "description": "Create or delete Gmail filters.",
                        "inputSchema": {
                            "type": "object",
                            "required": ["action"],
                            "properties": {
                                "action": {"type": "string"},
                                "criteria": {"type": "object"},
                            },
                        },
                    }
                }
            }
        )
    )
    agent.invoke_tool = AsyncMock(return_value={"status": "success", "result": "should-not-run"})
    agent._plan_before_execution = AsyncMock(
        return_value={
            "steps": [
                {
                    "step_number": 1,
                    "action": "Create Gmail filter",
                    "tool_name": "google-mcp__manage_gmail_filter",
                    "can_i_do_this": True,
                    "output_placeholder": "{{FILTER_RESULT}}",
                }
            ],
            "my_steps": [
                {
                    "action": "Create Gmail filter",
                    "tool_name": "google-mcp__manage_gmail_filter",
                    "parameters": {
                        "action": "create",
                        "criteria": {"from": "bondaruk.aleksandra92@gmail.com"},
                        "actions": {"addLabelIds": ["muxi-test"]},
                    },
                    "output_placeholder": "{{FILTER_RESULT}}",
                }
            ],
            "delegate_steps": [],
            "data_flow": "Create filter directly.",
        }
    )
    agent._repair_execution_plan_for_validation_failure = AsyncMock(return_value=None)
    agent._synthesize_planning_execution_response = AsyncMock(return_value="Blocked validation.")
    agent._check_cancellation = AsyncMock()

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
    ):
        response = await agent.process_message(
            "Create a Gmail filter for emails from bondaruk.aleksandra92@gmail.com.",
            user_id="tester",
            session_id="sess_123",
            request_id="req_123",
        )

    assert response.content == "Blocked validation."
    agent.invoke_tool.assert_not_awaited()
    agent._repair_execution_plan_for_validation_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_execution_plan_replans_with_missing_parameter_feedback():
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    repaired_plan = {
        "steps": [
            {
                "action": "Find Book.xlsx in the drive",
                "tool_name": "ms365-mcp__list-folder-files",
                "can_i_do_this": True,
            },
            {
                "action": "List worksheets in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
                "can_i_do_this": True,
            },
        ],
        "my_steps": [
            {
                "action": "Find Book.xlsx in the drive",
                "tool_name": "ms365-mcp__list-folder-files",
            },
            {
                "action": "List worksheets in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
            },
        ],
        "delegate_steps": [],
        "data_flow": "Lookup workbook, then list worksheets",
    }
    agent._plan_before_execution = AsyncMock(return_value=repaired_plan)

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._repair_execution_plan_for_missing_parameters(
            user_message="What sheets do I have in Book.xlsx?",
            available_tools=[],
            allow_delegation=False,
            failed_step={
                "action": "List worksheets in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
            },
            tool_name="ms365-mcp__list-excel-worksheets",
            unresolved_params=["driveItemId"],
            current_plan={
                "my_steps": [
                    {
                        "action": "List worksheets in Book.xlsx",
                        "tool_name": "ms365-mcp__list-excel-worksheets",
                    }
                ]
            },
            my_results={},
        )

    assert result == repaired_plan
    call_kwargs = agent._plan_before_execution.call_args.kwargs
    assert "driveItemId" in call_kwargs["replanning_feedback"]
    assert "Revise the plan" in call_kwargs["replanning_feedback"]


def test_summarize_planning_result_preserves_matching_record_from_large_payload():
    agent = object.__new__(Agent)
    large_payload = {
        "value": [
            {
                "id": f"attachment-{idx}",
                "name": f"Attachment-{idx}",
                "description": "x" * 200,
            }
            for idx in range(20)
        ]
        + [
            {
                "id": "book-item-123",
                "name": "Book.xlsx",
                "parentReference": {"driveId": "drive-123", "id": "root-456"},
                "webUrl": "https://example.com/Book.xlsx",
            }
        ]
    }
    result = {
        "status": "success",
        "result": {
            "content": [{"type": "text", "text": json.dumps(large_payload)}],
            "structuredContent": None,
            "isError": False,
        },
    }

    summary = agent._summarize_planning_result(
        result,
        context_hint="What sheets do I have in Book.xlsx?",
        limit=220,
    )

    assert "Book.xlsx" in summary
    assert "book-item-123" in summary


def test_extract_structured_planning_result_payload_prefers_top_level_structured_content():
    agent = object.__new__(Agent)

    payload = agent._extract_structured_planning_result_payload(
        {
            "status": "success",
            "output": '{"driveId":"wrong-drive"}',
            "structuredContent": {"driveId": "drive-123"},
        }
    )

    assert payload == {"driveId": "drive-123"}


def test_resolve_parameters_from_context_uses_matching_record_ids():
    agent = object.__new__(Agent)
    file_lookup_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "attachment-1",
                                    "name": "Attachments",
                                    "parentReference": {
                                        "driveId": "drive-123",
                                        "id": "root-456",
                                    },
                                },
                                {
                                    "id": "book-item-123",
                                    "name": "Book.xlsx",
                                    "parentReference": {
                                        "driveId": "drive-123",
                                        "id": "root-456",
                                    },
                                },
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    parameters = agent._resolve_parameters_from_context(
        required_params=["driveId", "driveItemId"],
        param_properties={
            "driveId": {"type": "string"},
            "driveItemId": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "properties": {
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
            },
            "required": ["driveId", "driveItemId"],
        },
        action_description="List all worksheets in Book.xlsx",
        user_request="What sheets do I have in Book.xlsx?\n[Context: driveId = drive-123]",
        my_results={"{{FILES_LIST}}": file_lookup_result},
    )

    assert parameters == {"driveId": "drive-123", "driveItemId": "book-item-123"}


def test_resolve_parameters_from_context_does_not_use_root_folder_id_for_workbook_step():
    agent = object.__new__(Agent)
    drive_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "drive-123",
                                    "name": "OneDrive",
                                    "driveType": "business",
                                }
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }
    root_item_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "id": "root-456",
                            "name": "root",
                            "folder": {"childCount": 2},
                            "root": {},
                            "parentReference": {"driveId": "drive-123"},
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    parameters = agent._resolve_parameters_from_context(
        required_params=["driveId", "driveItemId"],
        param_properties={
            "driveId": {"type": "string"},
            "driveItemId": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "properties": {
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
            },
            "required": ["driveId", "driveItemId"],
        },
        tool_name="ms365-mcp__list-excel-worksheets",
        action_description="List all worksheets in Book.xlsx",
        user_request="What sheets do I have in Book.xlsx?",
        my_results={"{{DRIVES}}": drive_result, "{{ROOT_ITEM}}": root_item_result},
    )

    assert parameters == {"driveId": "drive-123"}


def test_resolve_parameters_from_context_prefers_runtime_context_over_request_text():
    agent = object.__new__(Agent)

    parameters = agent._resolve_parameters_from_context(
        required_params=["driveId"],
        param_properties={"driveId": {"type": "string"}},
        full_schema={
            "type": "object",
            "properties": {"driveId": {"type": "string"}},
            "required": ["driveId"],
        },
        tool_name="ms365-mcp__list-excel-worksheets",
        action_description="List all worksheets in Book.xlsx",
        user_request="What sheets do I have in Book.xlsx?\n[Context: driveId = stale-drive]",
        my_results={},
        runtime_context={"driveId": "drive-123"},
    )

    assert parameters == {"driveId": "drive-123"}


def test_resolve_parameters_from_context_ignores_failed_results():
    agent = object.__new__(Agent)
    failed_lookup_result = {
        "status": "error",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "wrong-item-999",
                                    "name": "Book.xlsx",
                                    "parentReference": {"driveId": "wrong-drive-999"},
                                }
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": True,
        },
    }
    success_lookup_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "book-item-123",
                                    "name": "Book.xlsx",
                                    "parentReference": {"driveId": "drive-123"},
                                }
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    parameters = agent._resolve_parameters_from_context(
        required_params=["driveId", "driveItemId"],
        param_properties={
            "driveId": {"type": "string"},
            "driveItemId": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "properties": {
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
            },
            "required": ["driveId", "driveItemId"],
        },
        tool_name="ms365-mcp__list-excel-worksheets",
        action_description="List all worksheets in Book.xlsx",
        user_request="What sheets do I have in Book.xlsx?",
        my_results={
            "{{FAILED_LOOKUP}}": failed_lookup_result,
            "{{SUCCESS_LOOKUP}}": success_lookup_result,
        },
    )

    assert parameters == {"driveId": "drive-123", "driveItemId": "book-item-123"}


def test_build_parameter_inference_context_includes_only_successful_results():
    agent = object.__new__(Agent)
    success_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"value": [{"id": "book-item-123", "name": "Book.xlsx"}]}),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }
    failed_result = {
        "status": "error",
        "error": "lookup failed",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"value": [{"id": "wrong-item-999", "name": "Book.xlsx"}]}),
                }
            ],
            "structuredContent": None,
            "isError": True,
        },
    }

    context = agent._build_parameter_inference_context(
        user_request="What sheets do I have in Book.xlsx?",
        action_description="List all worksheets in Book.xlsx",
        my_results={"{{FAILED}}": failed_result, "{{SUCCESS}}": success_result},
        required_params=["driveId", "driveItemId"],
    )

    assert "Previous tool result ({{SUCCESS}}):" in context
    assert "Previous tool result ({{FAILED}}):" not in context
    assert "wrong-item-999" not in context


def test_substitute_step_parameter_placeholders_resolves_successful_results():
    agent = object.__new__(Agent)
    drives_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "drive-123",
                                    "name": "OneDrive",
                                    "driveType": "business",
                                }
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }
    file_lookup_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "book-item-123",
                                    "name": "Book.xlsx",
                                    "parentReference": {"driveId": "drive-123"},
                                }
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"driveId": "{{DRIVES}}", "driveItemId": "{{FILES_LIST}}"},
        param_properties={
            "driveId": {"type": "string"},
            "driveItemId": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "properties": {
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
            },
        },
        action_description="List all worksheets in Book.xlsx",
        my_results={"{{DRIVES}}": drives_result, "{{FILES_LIST}}": file_lookup_result},
        tool_name="ms365-mcp__list-excel-worksheets",
    )

    assert substituted == {"driveId": "drive-123", "driveItemId": "book-item-123"}


def test_merge_parameter_candidates_overrides_unresolved_placeholder_values_only():
    agent = object.__new__(Agent)

    merged = agent._merge_parameter_candidates(
        current_parameters={
            "driveId": "{{DRIVES}}",
            "driveItemId": "{{ROOT_ITEM}}",
            "sheetName": "Summary",
        },
        candidate_parameters={
            "driveId": "drive-123",
            "driveItemId": "book-item-123",
            "sheetName": "Sheet1",
        },
        param_properties={
            "driveId": {"type": "string"},
            "driveItemId": {"type": "string"},
            "sheetName": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "properties": {
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
                "sheetName": {"type": "string"},
            },
        },
    )

    assert merged == {
        "driveId": "drive-123",
        "driveItemId": "book-item-123",
        "sheetName": "Summary",
    }


@pytest.mark.asyncio
async def test_repair_execution_plan_accepts_meaningful_same_tool_chain_changes():
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    current_plan = {
        "my_steps": [
            {
                "action": "List worksheets in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
                "parameters": {},
                "output_placeholder": "{{WORKSHEETS}}",
            }
        ],
        "delegate_steps": [],
        "data_flow": "Old flow",
    }
    repaired_plan = {
        "my_steps": [
            {
                "action": "List worksheets in Book.xlsx after confirming the workbook lookup",
                "tool_name": "ms365-mcp__list-excel-worksheets",
                "parameters": {},
                "output_placeholder": "{{WORKSHEETS}}",
            }
        ],
        "delegate_steps": [],
        "data_flow": "New flow with explicit identifier sourcing",
    }
    agent._plan_before_execution = AsyncMock(return_value=repaired_plan)

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._repair_execution_plan_for_missing_parameters(
            user_message="What sheets do I have in Book.xlsx?",
            available_tools=[],
            allow_delegation=False,
            failed_step=current_plan["my_steps"][0],
            tool_name="ms365-mcp__list-excel-worksheets",
            unresolved_params=["driveItemId"],
            current_plan=current_plan,
            my_results={},
        )

    assert result == repaired_plan


@pytest.mark.asyncio
async def test_repair_execution_plan_adds_auto_discovery_step_when_replan_has_no_change():
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent._mcp_service = None
    current_plan = {
        "steps": [
            {
                "action": "Find the drive",
                "tool_name": "ms365-mcp__list-drives",
                "can_i_do_this": True,
                "output_placeholder": "{{DRIVES}}",
            },
            {
                "action": "Get the root folder for the drive",
                "tool_name": "ms365-mcp__get-drive-root-item",
                "can_i_do_this": True,
                "output_placeholder": "{{ROOT_ITEM}}",
            },
            {
                "action": "List all worksheets (sheets) in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
                "can_i_do_this": True,
                "output_placeholder": "{{WORKSHEETS}}",
            },
        ],
        "my_steps": [
            {
                "action": "Find the drive",
                "tool_name": "ms365-mcp__list-drives",
                "parameters": {},
                "output_placeholder": "{{DRIVES}}",
            },
            {
                "action": "Get the root folder for the drive",
                "tool_name": "ms365-mcp__get-drive-root-item",
                "parameters": {},
                "output_placeholder": "{{ROOT_ITEM}}",
            },
            {
                "action": "List all worksheets (sheets) in Book.xlsx",
                "tool_name": "ms365-mcp__list-excel-worksheets",
                "parameters": {},
                "output_placeholder": "{{WORKSHEETS}}",
            },
        ],
        "delegate_steps": [],
        "data_flow": "Get the drive, then the root folder, then list worksheets.",
    }
    agent._plan_before_execution = AsyncMock(return_value=current_plan)

    available_tools = [
        {
            "function": {
                "name": "ms365-mcp__list-folder-files",
                "description": "List files in a folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "driveId": {"type": "string"},
                        "driveItemId": {"type": "string"},
                        "searchQuery": {"type": "string"},
                    },
                    "required": ["driveId", "driveItemId"],
                },
            }
        },
        {
            "function": {
                "name": "ms365-mcp__search-sharepoint-sites",
                "description": "Search SharePoint sites.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
    ]
    drives_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "drive-123",
                                    "name": "OneDrive",
                                    "driveType": "business",
                                }
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }
    root_item_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "id": "root-456",
                            "name": "root",
                            "folder": {"childCount": 2},
                            "root": {},
                            "parentReference": {"driveId": "drive-123"},
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._repair_execution_plan_for_missing_parameters(
            user_message="What sheets do I have in Book.xlsx?\n[Context: driveId = drive-123]",
            available_tools=available_tools,
            allow_delegation=False,
            failed_step=current_plan["my_steps"][-1],
            tool_name="ms365-mcp__list-excel-worksheets",
            unresolved_params=["driveItemId"],
            current_plan=current_plan,
            my_results={"{{DRIVES}}": drives_result, "{{ROOT_ITEM}}": root_item_result},
        )

    assert result is not None
    tool_names = [step["tool_name"] for step in result["my_steps"]]
    assert tool_names == [
        "ms365-mcp__list-drives",
        "ms365-mcp__get-drive-root-item",
        "ms365-mcp__list-folder-files",
        "ms365-mcp__list-excel-worksheets",
    ]
    assert result["my_steps"][2]["parameters"] == {
        "driveId": "drive-123",
        "driveItemId": "root-456",
        "searchQuery": "Book.xlsx",
    }


# ---------------------------------------------------------------------------
# Auto-discovery server affinity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_discovery_prefers_same_server_over_cross_server_candidate():
    """A cross-server tool (todo-helper-mcp) must not be chosen as a discovery
    step when a same-server candidate (ms365-mcp) is available."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"
    agent._mcp_service = None

    current_plan = {
        "my_steps": [
            {
                "action": "List mail messages",
                "tool_name": "ms365-mcp__list-mail-messages",
                "parameters": {},
                "output_placeholder": "{{EMAIL_LIST}}",
            }
        ],
        "delegate_steps": [],
        "data_flow": "List mailbox contents.",
    }
    # Simulate replan returning the same plan (triggers auto-discovery)
    agent._plan_before_execution = AsyncMock(return_value=current_plan)

    available_tools = [
        {
            "function": {
                "name": "ms365-mcp__list-mail-messages",
                "description": "List mail messages from the mailbox.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "ms365-mcp__list-mail-folders",
                "description": "List mail folders in the user's mailbox.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "todo-helper-mcp__get-default-list-id",
                "description": "Get the default task list ID for the user.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
    ]

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._repair_execution_plan_for_missing_parameters(
            user_message="Do I have any emails?",
            available_tools=available_tools,
            allow_delegation=False,
            failed_step=current_plan["my_steps"][0],
            tool_name="ms365-mcp__list-mail-messages",
            unresolved_params=["folderId"],
            current_plan=current_plan,
            my_results={},
        )

    assert result is not None
    inserted_tools = [step["tool_name"] for step in result["my_steps"]]
    assert "todo-helper-mcp__get-default-list-id" not in inserted_tools
    assert any(
        t.startswith("ms365-mcp__") for t in inserted_tools if t != "ms365-mcp__list-mail-messages"
    )


# ---------------------------------------------------------------------------
# v0.20260416.4 -- domain affinity in repair-tool selection
# ---------------------------------------------------------------------------


def test_get_tool_domain_tags_classifies_unambiguous_tokens():
    """Each unambiguous token must map to exactly one domain."""
    assert Agent._get_tool_domain_tags("ms365-mcp__get-drive-root-item") == frozenset({"drive"})
    assert Agent._get_tool_domain_tags("ms365-mcp__list-mail-folders") == frozenset({"mail"})
    assert Agent._get_tool_domain_tags("ms365-mcp__search-sharepoint-sites") == frozenset(
        {"sharepoint"}
    )
    assert Agent._get_tool_domain_tags("ms365-mcp__list-calendar-events") == frozenset({"calendar"})
    assert Agent._get_tool_domain_tags("todo-helper-mcp__get-default-list-id") == frozenset(
        {"task"}
    )
    assert Agent._get_tool_domain_tags("ms365-mcp__get-excel-workbook-worksheet-data") == frozenset(
        {"drive"}
    )


def test_get_tool_domain_tags_returns_empty_for_ambiguous_names():
    """Names that only contain ambiguous tokens must stay untagged so they
    do not incur a cross-domain penalty."""
    assert Agent._get_tool_domain_tags("generic-mcp__list-items") == frozenset()
    assert Agent._get_tool_domain_tags("ms365-mcp__get-item") == frozenset()
    assert Agent._get_tool_domain_tags("") == frozenset()


@pytest.mark.asyncio
async def test_auto_discovery_rejects_cross_domain_same_server_candidate():
    """Regression for v0.20260416.2 Dev #1 Excel: a ``drive`` failure must
    not pick ``list-mail-folders`` or ``search-sharepoint-sites`` as a
    repair candidate, even though both live on the same ms365-mcp server."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"
    agent._mcp_service = None

    current_plan = {
        "my_steps": [
            {
                "action": "Read the Excel workbook in OneDrive root",
                "tool_name": "ms365-mcp__get-drive-root-item",
                "parameters": {},
                "output_placeholder": "{{ROOT_ITEM}}",
            }
        ],
        "delegate_steps": [],
        "data_flow": "Locate the workbook.",
    }
    agent._plan_before_execution = AsyncMock(return_value=current_plan)

    available_tools = [
        {
            "function": {
                "name": "ms365-mcp__get-drive-root-item",
                "description": "Get the root item of a OneDrive.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "ms365-mcp__list-mail-folders",
                "description": "List mail folders in the user's mailbox.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "ms365-mcp__search-sharepoint-sites",
                "description": "Search SharePoint sites.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "ms365-mcp__list-drives",
                "description": "List available OneDrive drives for the user.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
    ]

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._repair_execution_plan_for_missing_parameters(
            user_message="Open my Excel workbook in OneDrive",
            available_tools=available_tools,
            allow_delegation=False,
            failed_step=current_plan["my_steps"][0],
            tool_name="ms365-mcp__get-drive-root-item",
            unresolved_params=["driveId"],
            current_plan=current_plan,
            my_results={},
        )

    assert result is not None
    inserted_tools = [step["tool_name"] for step in result["my_steps"]]
    # Cross-domain candidates must be excluded.
    assert "ms365-mcp__list-mail-folders" not in inserted_tools
    assert "ms365-mcp__search-sharepoint-sites" not in inserted_tools
    # The drive-domain candidate must win.
    assert "ms365-mcp__list-drives" in inserted_tools


@pytest.mark.asyncio
async def test_auto_discovery_prefers_same_domain_same_server_candidate():
    """When multiple same-server candidates exist, the one that shares a
    resource domain with the failed tool must win on score."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"
    agent._mcp_service = None

    current_plan = {
        "my_steps": [
            {
                "action": "Update calendar event",
                "tool_name": "ms365-mcp__update-calendar-event",
                "parameters": {},
                "output_placeholder": "{{EVENT_UPDATE}}",
            }
        ],
        "delegate_steps": [],
        "data_flow": "Edit event.",
    }
    agent._plan_before_execution = AsyncMock(return_value=current_plan)

    available_tools = [
        {
            "function": {
                "name": "ms365-mcp__update-calendar-event",
                "description": "Update a calendar event.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "ms365-mcp__list-calendar-events",
                "description": "List calendar events.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
        {
            "function": {
                "name": "ms365-mcp__list-mail-folders",
                "description": "List mail folders.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        },
    ]

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._repair_execution_plan_for_missing_parameters(
            user_message="Move my 3pm meeting to 4pm",
            available_tools=available_tools,
            allow_delegation=False,
            failed_step=current_plan["my_steps"][0],
            tool_name="ms365-mcp__update-calendar-event",
            unresolved_params=["eventId"],
            current_plan=current_plan,
            my_results={},
        )

    assert result is not None
    inserted_tools = [step["tool_name"] for step in result["my_steps"]]
    # The calendar-domain sibling wins; the mail sibling is rejected.
    assert "ms365-mcp__list-calendar-events" in inserted_tools
    assert "ms365-mcp__list-mail-folders" not in inserted_tools


# ---------------------------------------------------------------------------
# _validate_inferred_parameters_against_results
# ---------------------------------------------------------------------------


def test_validate_inferred_drops_folder_id_used_as_file_param():
    """When results contain only folders, an inferred driveItemId that matches
    a folder record must be dropped for a file-expecting tool."""
    agent = object.__new__(Agent)
    root_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "id": "root-folder-001",
                            "name": "root",
                            "folder": {"childCount": 3},
                            "root": {},
                            "parentReference": {
                                "driveId": "b!drive-xyz",
                            },
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }
    folder_listing_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "folder-meetings",
                                    "name": "Meetings",
                                    "folder": {"childCount": 0},
                                },
                                {
                                    "id": "folder-recordings",
                                    "name": "Recordings",
                                    "folder": {"childCount": 0},
                                },
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        validated = agent._validate_inferred_parameters_against_results(
            inferred_parameters={
                "driveId": "b!drive-xyz",
                "driveItemId": "root-folder-001",
            },
            my_results={
                "{{ROOT}}": root_result,
                "{{FILES}}": folder_listing_result,
            },
            param_properties={
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
            },
            full_schema={
                "type": "object",
                "properties": {
                    "driveId": {"type": "string"},
                    "driveItemId": {"type": "string"},
                },
                "required": ["driveId", "driveItemId"],
            },
            tool_name="ms365-mcp__list-excel-worksheets",
            action_description="List all worksheets in Book.xlsx",
        )

    assert "driveId" in validated, "driveId is generic and should be kept"
    assert (
        "driveItemId" not in validated
    ), "driveItemId should be dropped — root-folder-001 only appears in folder/root records"


def test_validate_inferred_keeps_file_id_when_file_record_exists():
    """When results contain a file record matching the inferred ID, it should be kept."""
    agent = object.__new__(Agent)
    file_listing_result = {
        "status": "success",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "value": [
                                {
                                    "id": "book-item-123",
                                    "name": "Book.xlsx",
                                    "file": {"mimeType": "application/vnd.openxmlformats"},
                                    "parentReference": {"driveId": "drive-abc"},
                                },
                                {
                                    "id": "folder-meetings",
                                    "name": "Meetings",
                                    "folder": {"childCount": 0},
                                },
                            ]
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": False,
        },
    }

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        validated = agent._validate_inferred_parameters_against_results(
            inferred_parameters={
                "driveId": "drive-abc",
                "driveItemId": "book-item-123",
            },
            my_results={"{{FILES}}": file_listing_result},
            param_properties={
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
            },
            full_schema={
                "type": "object",
                "properties": {
                    "driveId": {"type": "string"},
                    "driveItemId": {"type": "string"},
                },
                "required": ["driveId", "driveItemId"],
            },
            tool_name="ms365-mcp__list-excel-worksheets",
            action_description="List all worksheets in Book.xlsx",
        )

    assert validated == {"driveId": "drive-abc", "driveItemId": "book-item-123"}


def test_validate_inferred_ignores_failed_results():
    """Failed results should not be considered when validating inferred params."""
    agent = object.__new__(Agent)
    failed_result = {
        "status": "error",
        "error": "401 Unauthorized",
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "id": "ghost-item-999",
                            "name": "Book.xlsx",
                            "file": {"mimeType": "application/vnd.openxmlformats"},
                        }
                    ),
                }
            ],
            "structuredContent": None,
            "isError": True,
        },
    }

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        validated = agent._validate_inferred_parameters_against_results(
            inferred_parameters={"driveItemId": "ghost-item-999"},
            my_results={"{{FAILED}}": failed_result},
            param_properties={"driveItemId": {"type": "string"}},
            full_schema={
                "type": "object",
                "properties": {"driveItemId": {"type": "string"}},
                "required": ["driveItemId"],
            },
            tool_name="ms365-mcp__list-excel-worksheets",
            action_description="List worksheets in Book.xlsx",
        )

    assert "driveItemId" not in validated


def test_validate_inferred_passes_through_generic_params():
    """Params with generic expected_kind (e.g. searchQuery) should not be filtered."""
    agent = object.__new__(Agent)

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        validated = agent._validate_inferred_parameters_against_results(
            inferred_parameters={"searchQuery": "Book.xlsx", "top": "10"},
            my_results={},
            param_properties={
                "searchQuery": {"type": "string"},
                "top": {"type": "string"},
            },
            full_schema={
                "type": "object",
                "properties": {
                    "searchQuery": {"type": "string"},
                    "top": {"type": "string"},
                },
            },
            tool_name="ms365-mcp__list-folder-files",
            action_description="List files in root folder",
        )

    assert validated == {"searchQuery": "Book.xlsx", "top": "10"}


# ---------------------------------------------------------------------------
# Planning JSON extraction robustness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_before_execution_extracts_json_from_prose_preamble():
    """Sonnet 4 (old) wraps the JSON plan in prose. The parser must still extract it."""
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent.name = "Test Agent"
    agent.system_message = ""
    agent.overlord = None

    raw_response = (
        "Looking at your request, I need to find the file.\n\n```json\n"
        '{\n  "steps": [{"step_number": 1, "action": "Get root folder", '
        '"tool_name": "ms365-mcp__get-drive-root-item", "can_i_do_this": true}],\n'
        '  "data_flow": "step-by-step"\n}\n```'
    )

    mock_response = SimpleNamespace(content=raw_response)
    agent.model = AsyncMock()
    agent.model.chat = AsyncMock(return_value=mock_response)

    tools = [{"function": {"name": "ms365-mcp__get-drive-root-item", "description": "Get root"}}]

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
        patch("muxi.runtime.formation.prompts.loader.PromptLoader.get", return_value=""),
    ):
        plan = await agent._plan_before_execution("What sheets?", tools)

    assert len(plan.get("my_steps", [])) >= 1
    assert plan["my_steps"][0]["tool_name"] == "ms365-mcp__get-drive-root-item"


@pytest.mark.asyncio
async def test_plan_before_execution_extracts_json_without_code_fence():
    """Model returns prose then bare JSON (no code fence). Parser must find the { ... }."""
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent.name = "Test Agent"
    agent.system_message = ""
    agent.overlord = None

    raw_response = (
        "Here is my plan:\n\n"
        '{"steps": [{"step_number": 1, "action": "List files", '
        '"tool_name": "ms365-mcp__list-folder-files", "can_i_do_this": true}], '
        '"data_flow": "direct"}'
    )

    mock_response = SimpleNamespace(content=raw_response)
    agent.model = AsyncMock()
    agent.model.chat = AsyncMock(return_value=mock_response)

    tools = [{"function": {"name": "ms365-mcp__list-folder-files", "description": "List files"}}]

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
        patch("muxi.runtime.formation.prompts.loader.PromptLoader.get", return_value=""),
    ):
        plan = await agent._plan_before_execution("Find Book.xlsx", tools)

    assert len(plan.get("my_steps", [])) >= 1


@pytest.mark.asyncio
async def test_plan_before_execution_sets_max_tokens():
    """Planning LLM call must set explicit max_tokens to avoid truncation."""
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent.name = "Test Agent"
    agent.system_message = ""
    agent.overlord = None

    plan_json = '{"steps": [{"action": "test", "can_i_do_this": true, "tool_name": "t"}]}'
    mock_response = SimpleNamespace(content=plan_json)
    agent.model = AsyncMock()
    agent.model.chat = AsyncMock(return_value=mock_response)

    tools = [{"function": {"name": "t", "description": "test"}}]

    with (
        patch("muxi.runtime.formation.agents.agent.streaming.stream"),
        patch("muxi.runtime.formation.agents.agent.observability.observe"),
        patch("muxi.runtime.formation.prompts.loader.PromptLoader.get", return_value=""),
    ):
        await agent._plan_before_execution("test", tools)

    call_kwargs = agent.model.chat.call_args
    assert call_kwargs.kwargs.get("max_tokens") == 16384


# ---------------------------------------------------------------------------
# Alias extraction for worksheet / section / channel / plan IDs
# ---------------------------------------------------------------------------


def test_alias_extraction_resolves_worksheetid_from_record():
    """workbookWorksheetId must be extracted from a worksheet record's 'id' field."""
    agent = object.__new__(Agent)
    worksheet_record = {
        "id": "{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}",
        "name": "Sheet1",
        "position": 0,
        "visibility": "Visible",
    }
    value = agent._extract_alias_value_from_record(
        "workbookWorksheetId", worksheet_record, "generic"
    )
    assert value == "{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}"


def test_alias_extraction_resolves_planid_from_record():
    """planId must be extracted from a planner record's 'id' field."""
    agent = object.__new__(Agent)
    plan_record = {"id": "plan-abc-123", "title": "Sprint 42"}
    value = agent._extract_alias_value_from_record("planId", plan_record, "generic")
    assert value == "plan-abc-123"


def test_alias_extraction_resolves_channelid_from_record():
    """channelId must be extracted from a Teams channel record's 'id' field."""
    agent = object.__new__(Agent)
    channel_record = {"id": "19:abc@thread.tacv2", "displayName": "General"}
    value = agent._extract_alias_value_from_record("channelId", channel_record, "generic")
    assert value == "19:abc@thread.tacv2"


def test_alias_extraction_resolves_snake_case_channel_id():
    """channel_id (snake_case) must also be extracted via underscore normalization."""
    agent = object.__new__(Agent)
    channel_record = {"id": "C08SZKB16UF", "name": "social"}
    value = agent._extract_alias_value_from_record("channel_id", channel_record, "generic")
    assert value == "C08SZKB16UF"


def test_resolve_context_prefers_most_recent_step_result():
    """When multiple prior steps have records with 'id', the most recent step's record wins."""
    agent = object.__new__(Agent)
    agent.agent_id = "test"
    agent.overlord = None

    file_result = {
        "result": json.dumps(
            {"id": "01SA7QZQZWMLF7VGIIMNAILZA3424C3AL5", "name": "Book.xlsx", "file": {}}
        ),
        "status": "success",
    }
    worksheet_result = {
        "result": json.dumps(
            {
                "value": [
                    {
                        "id": "{00000000-0001-0000-0000-000000000000}",
                        "name": "Sheet1",
                        "position": 0,
                        "visibility": "Visible",
                    }
                ]
            }
        ),
        "status": "success",
    }

    with patch.object(observability, "observe"):
        resolved = agent._resolve_parameters_from_context(
            required_params=["workbookWorksheetId"],
            param_properties={"workbookWorksheetId": {"type": "string"}},
            full_schema={
                "type": "object",
                "properties": {"workbookWorksheetId": {"type": "string"}},
            },
            tool_name="ms365-mcp__get-excel-range",
            action_description="Read cell A1 from Sheet1",
            user_request="What's in cell A1 of Sheet1?",
            my_results={
                "step_2_list_files": file_result,
                "step_3_list_worksheets": worksheet_result,
            },
        )

    # Must get worksheet GUID, NOT driveItemId
    assert resolved.get("workbookWorksheetId") == "{00000000-0001-0000-0000-000000000000}"


def test_resolve_parameters_from_context_binds_worksheetid():
    """Full context resolution must bind workbookWorksheetId from list-excel-worksheets result."""
    agent = object.__new__(Agent)
    agent.agent_id = "test"
    agent.overlord = None

    worksheet_result = {
        "result": json.dumps(
            {
                "value": [
                    {
                        "id": "{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}",
                        "name": "Sheet1",
                        "position": 0,
                        "visibility": "Visible",
                    },
                    {
                        "id": "{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}",
                        "name": "Table 2",
                        "position": 1,
                        "visibility": "Visible",
                    },
                ]
            }
        ),
        "status": "success",
    }

    with patch.object(observability, "observe"):
        resolved = agent._resolve_parameters_from_context(
            required_params=["driveId", "driveItemId", "workbookWorksheetId", "address"],
            param_properties={
                "driveId": {"type": "string"},
                "driveItemId": {"type": "string"},
                "workbookWorksheetId": {"type": "string"},
                "address": {"type": "string"},
            },
            full_schema={
                "type": "object",
                "properties": {
                    "driveId": {"type": "string"},
                    "driveItemId": {"type": "string"},
                    "workbookWorksheetId": {"type": "string"},
                    "address": {"type": "string"},
                },
            },
            tool_name="ms365-mcp__get-excel-range",
            action_description="Read cell A1 from Sheet1",
            user_request="What's in cell A1 of Sheet1 in Book.xlsx?",
            my_results={
                "step_3_list_worksheets": worksheet_result,
            },
        )

    assert resolved.get("workbookWorksheetId") == "{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}"


# ---------------------------------------------------------------------------
# Placeholder detection: GUID exemption
# ---------------------------------------------------------------------------


def test_guid_in_braces_is_not_placeholder():
    """Real GUIDs in braces must not be treated as placeholders."""
    assert not Agent._is_placeholder_like_value("{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}")
    assert not Agent._is_placeholder_like_value("{00000000-0001-0000-0000-000000000000}")
    assert not Agent._is_placeholder_like_value("{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}")


def test_placeholder_patterns_still_detected():
    """Planning placeholders must still be detected after the GUID exemption."""
    assert Agent._is_placeholder_like_value("{{ROOT_FOLDER_ID}}")
    assert Agent._is_placeholder_like_value("${{secrets.KEY}}")
    assert Agent._is_placeholder_like_value("<<DRIVE_ITEM_ID>>")
    assert Agent._is_placeholder_like_value("{ROOT_FOLDER_ID}")
    assert Agent._is_placeholder_like_value("{WORKSHEET_ID}")


def test_guid_passes_nonempty_candidate_check():
    """A GUID-in-braces must be accepted as a nonempty parameter candidate."""
    assert Agent._is_nonempty_parameter_candidate("{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}")
    assert not Agent._is_nonempty_parameter_candidate("{ROOT_FOLDER_ID}")


# ---------------------------------------------------------------------------
# Result payload extraction: string 'result' field parsing
# ---------------------------------------------------------------------------


def test_extract_structured_payload_parses_string_result_field():
    """When result dict has a JSON string in 'result', it must be parsed."""
    agent = object.__new__(Agent)
    raw_result = {
        "result": json.dumps({"value": [{"id": "abc-123", "name": "Sheet1"}]}),
        "status": "success",
    }
    payload = agent._extract_structured_planning_result_payload(raw_result)
    assert isinstance(payload, dict)
    assert "value" in payload
    assert payload["value"][0]["id"] == "abc-123"


def test_extract_structured_payload_parses_string_result_array():
    """When result dict has a JSON array string in 'result', it must be parsed."""
    agent = object.__new__(Agent)
    raw_result = {
        "result": json.dumps([{"id": "item-1"}, {"id": "item-2"}]),
        "status": "success",
    }
    payload = agent._extract_structured_planning_result_payload(raw_result)
    assert isinstance(payload, list)
    assert len(payload) == 2


def test_extract_structured_payload_returns_plain_string_result():
    """When result dict has a non-JSON string in 'result', return it as-is."""
    agent = object.__new__(Agent)
    raw_result = {"result": "Operation completed successfully", "status": "success"}
    payload = agent._extract_structured_planning_result_payload(raw_result)
    assert payload == "Operation completed successfully"


# ---------------------------------------------------------------------------
# Preventive: exact-key match normalizes camelCase <-> snake_case
# ---------------------------------------------------------------------------


def test_exact_key_match_normalizes_snake_case():
    """A record with snake_case key 'channel_id' must match param 'channelId' exactly."""
    agent = object.__new__(Agent)
    record = {"channel_id": "C08SZKB16UF", "name": "social"}
    val = agent._resolve_parameter_from_records("channelId", [], [record])
    assert val == "C08SZKB16UF"


def test_exact_key_match_normalizes_camel_to_snake():
    """A record with camelCase key 'channelId' must match param 'channel_id' exactly."""
    agent = object.__new__(Agent)
    record = {"channelId": "C08SZKB16UF", "name": "social"}
    val = agent._resolve_parameter_from_records("channel_id", [], [record])
    assert val == "C08SZKB16UF"


def test_exact_key_match_normalizes_drive_item_id():
    """Record 'drive_item_id' must match param 'driveItemId'."""
    agent = object.__new__(Agent)
    record = {"drive_item_id": "01SA7QZQ...", "name": "file.txt"}
    val = agent._resolve_parameter_from_records("driveItemId", [], [record])
    assert val == "01SA7QZQ..."


# ---------------------------------------------------------------------------
# Preventive: explicit text extraction matches both casings
# ---------------------------------------------------------------------------


def test_explicit_text_extracts_snake_case_param():
    """'channel_id = C123' in text should resolve param 'channelId'."""
    resolved = Agent._extract_explicit_parameter_values_from_text(
        "[Context: channel_id = C08SZKB16UF]", ["channelId"]
    )
    assert resolved.get("channelId") == "C08SZKB16UF"


def test_explicit_text_extracts_camel_case_param():
    """'channelId = C123' in text should resolve param 'channel_id'."""
    resolved = Agent._extract_explicit_parameter_values_from_text(
        "[Context: channelId = C08SZKB16UF]", ["channel_id"]
    )
    assert resolved.get("channel_id") == "C08SZKB16UF"


# ---------------------------------------------------------------------------
# Preventive: context hints match snake_case fields
# ---------------------------------------------------------------------------


def test_context_hints_match_display_name_field():
    """Record with 'display_name' field should match context hints."""
    record = {"id": "123", "display_name": "General"}
    assert Agent._record_matches_context_hints(record, ["General"])


def test_context_hints_match_channel_name_field():
    """Record with 'channel_name' field should match context hints."""
    record = {"id": "C123", "channel_name": "social"}
    assert Agent._record_matches_context_hints(record, ["social"])


def test_extract_context_hints_captures_hashtag_resource_name():
    """Hashtag-prefixed resource names should be extracted generically."""
    hints = Agent._extract_context_hints("Show me the last 10 messages in #social")
    assert "social" in hints
    assert "#social" in hints


# ---------------------------------------------------------------------------
# Preventive: compact record preserves snake_case keys
# ---------------------------------------------------------------------------


def test_compact_record_preserves_snake_case_keys():
    """_compact_planning_record must retain snake_case variants of common fields."""
    record = {
        "id": "abc",
        "display_name": "My Channel",
        "channel_id": "C123",
        "channel_name": "general",
        "position": 0,
        "visibility": "Visible",
        "description": "Team channel",
        "type": "standard",
        "status": "active",
        "irrelevant_field": "should_be_dropped",
    }
    compact = Agent._compact_planning_record(record)
    assert compact["id"] == "abc"
    assert compact["display_name"] == "My Channel"
    assert compact["channel_id"] == "C123"
    assert compact["channel_name"] == "general"
    assert compact["position"] == 0
    assert compact["visibility"] == "Visible"
    assert compact["description"] == "Team channel"
    assert compact["type"] == "standard"
    assert compact["status"] == "active"
    assert "irrelevant_field" not in compact


# ---------------------------------------------------------------------------
# Preventive: multi-step resolution with mixed casing MCPs
# ---------------------------------------------------------------------------


def test_resolve_context_with_snake_case_mcp_records():
    """Full context resolution must work when MCP returns snake_case keys."""
    agent = object.__new__(Agent)
    agent.agent_id = "test"
    agent.overlord = None

    channels_result = {
        "result": json.dumps(
            {
                "channels": [
                    {"id": "C08SZKAV4KH", "name": "all-spark", "num_members": 4},
                    {"id": "C08SZKB16UF", "name": "social", "num_members": 4},
                    {"id": "C08TABCDEF", "name": "general", "num_members": 12},
                ]
            }
        ),
        "status": "success",
    }

    with patch.object(observability, "observe"):
        resolved = agent._resolve_parameters_from_context(
            required_params=["channel_id"],
            param_properties={"channel_id": {"type": "string"}},
            full_schema={"type": "object", "properties": {"channel_id": {"type": "string"}}},
            tool_name="slack-mcp__slack_get_channel_history",
            action_description="Get history for #social",
            user_request="Show me the last 10 messages in #social",
            my_results={"step_1_list_channels": channels_result},
        )

    assert resolved.get("channel_id") == "C08SZKB16UF"


def test_mcp_default_param_names_include_only_nonempty_defaults():
    """Only non-empty MCP server defaults should count as default-backed params."""
    agent = object.__new__(Agent)
    agent._mcp_service = SimpleNamespace(
        server_configs={
            "ms365-mcp": {
                "parameters": {
                    "driveId": "${{ user.credentials.MS365_DRIVE_ID }}",
                    "driveItemId": "",
                    "siteId": None,
                }
            }
        }
    )

    assert agent._get_mcp_default_param_names("ms365-mcp") == {"driveId"}


def test_filter_unresolved_params_backed_by_server_defaults():
    """MCP-backed defaults must not be treated as unresolved during planning."""
    unresolved = Agent._filter_unresolved_params_backed_by_server_defaults(
        ["driveId", "workbookWorksheetId"],
        {"driveId"},
    )

    assert unresolved == ["workbookWorksheetId"]


def test_validate_tool_parameters_allows_server_default_backed_required_params():
    """Schema validation should allow required params that MCP defaults will inject."""
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"

    is_valid, error = agent._validate_tool_parameters(
        parameters={},
        tool_schema={
            "parameters": {
                "type": "object",
                "required": ["driveId"],
                "properties": {"driveId": {"type": "string"}},
            }
        },
        tool_name="ms365-mcp__get-drive-root-item",
        server_default_param_names={"driveId"},
    )

    assert is_valid is True
    assert error is None


def test_validate_tool_parameters_rejects_unknown_schema_params():
    """Unknown planner-authored params must fail closed before MCP execution."""
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"

    is_valid, error = agent._validate_tool_parameters(
        parameters={
            "action": "create",
            "criteria": {"from": "bondaruk.aleksandra92@gmail.com"},
            "actions": {"addLabelIds": ["muxi-test"]},
        },
        tool_schema={
            "parameters": {
                "type": "object",
                "required": ["action"],
                "properties": {
                    "action": {"type": "string"},
                    "criteria": {"type": "object"},
                },
            }
        },
        tool_name="google-mcp__manage_gmail_filter",
    )

    assert is_valid is False
    assert error == "Unexpected parameters not in tool schema: actions"


def test_build_delegation_prompt_with_results_appends_prior_result_context():
    """Delegation prompts should carry prior tool results even without placeholders."""
    agent = object.__new__(Agent)
    my_results = {
        "{{COLUMN_A_DATA}}": {
            "status": "success",
            "result": json.dumps({"values": [[1], [2], [3]]}),
        }
    }

    prompt = agent._build_delegation_prompt_with_results(
        "Calculate the sum of the numbers in column A.",
        my_results,
        context_hint="sum column A",
    )

    assert "## Prior tool results" in prompt
    assert "{{COLUMN_A_DATA}}" in prompt
    assert "values" in prompt
    assert "do not invent missing data" in prompt.lower()


# ---------------------------------------------------------------------------
# v0.20260418.0 regression tests — text extraction, cross-placeholder
# fallback, literal-placeholder stripping, array inference validation.
# ---------------------------------------------------------------------------


def test_field_name_variants_covers_snake_camel_space_and_all_caps():
    """Variants must include snake_case, camelCase, spaced, Title, and
    ID-suffix all-caps forms so free-text extraction catches every common
    MCP serialization style."""
    variants = Agent._field_name_variants("message_id")
    assert "message_id" in variants
    assert "messageId" in variants
    assert "message id" in variants
    assert "Message Id" in variants
    assert "Message ID" in variants

    variants = Agent._field_name_variants("eventId")
    assert "eventId" in variants
    assert "event_id" in variants
    assert "event id" in variants
    assert "Event ID" in variants


def test_extract_field_values_from_text_handles_markdown_and_json_patterns():
    """Label-style `Field: value`, bold markdown `**Field:** value`, and
    embedded JSON `"field":"value"` must all be recognized."""
    text = (
        "1. From: ops@example.com\n"
        "   Subject: You've joined the Spark Devs group\n"
        "   **Message ID:** 19d78b1d775ca3e0\n"
        "\n"
        '   JSON snippet: {"event_id": "rl5p13b7jgd570rlph28stpaug"}\n'
        "   Received: 2026-04-10 08:16 AM\n"
    )
    assert Agent._extract_field_values_from_text(text, "message_id") == ["19d78b1d775ca3e0"]
    # JSON-embedded values are still discoverable.
    assert "rl5p13b7jgd570rlph28stpaug" in Agent._extract_field_values_from_text(text, "event_id")


def test_extract_field_values_from_text_collects_all_matches_for_arrays():
    """Gmail BUG-3: the Gmail search tool returns the 10 real message IDs
    inside a single text blob.  Extraction must collect all of them when
    the caller asks for every match."""
    text = (
        "Found 10 messages matching 'after:2026/04/10 before:2026/04/11':\n"
        "\n"
        "1. From: alice@example.com\n"
        "   **Message ID:** 19d78b1d775ca3e0\n"
        "2. From: bob@example.com\n"
        "   **Message ID:** 19d4e8c9d1f2a3b4\n"
        "3. From: carol@example.com\n"
        "   **Message ID:** 19d2a1e7b0d9c8f5\n"
    )
    values = Agent._extract_field_values_from_text(text, "message_id")
    assert values == [
        "19d78b1d775ca3e0",
        "19d4e8c9d1f2a3b4",
        "19d2a1e7b0d9c8f5",
    ]


def test_extract_field_from_result_payload_falls_back_to_text_patterns():
    """When the structured payload exposes result content only as free text
    (FastMCP default serialization), extraction must scan the text for
    `Field: value` style matches."""
    agent = object.__new__(Agent)
    payload = {
        "structuredContent": {
            "result": (
                "Event found in primary calendar:\n"
                "Title: Spark Test Event\n"
                "Time: 2026-04-18T12:00:00Z\n"
                "ID: rl5p13b7jgd570rlph28stpaug\n"
                "Link: https://calendar.google.com/event?id=rl5p13b7jgd570rlph28stpaug"
            )
        }
    }
    assert (
        agent._extract_field_from_result_payload(payload, "event_id")
        == "rl5p13b7jgd570rlph28stpaug"
    )
    assert agent._extract_field_from_result_payload(payload, "id") == "rl5p13b7jgd570rlph28stpaug"


def test_extract_field_from_result_payload_collects_all_in_array_mode():
    """Gmail BUG-3 root-cause check: with ``collect_all=True`` we return
    every match found in any text chunk, deduplicated, preserving order."""
    agent = object.__new__(Agent)
    payload = {
        "content": [
            {
                "type": "text",
                "text": (
                    "1. **Message ID:** aaa111\n"
                    "2. **Message ID:** bbb222\n"
                    "3. **Message ID:** ccc333\n"
                    "4. **Message ID:** bbb222\n"  # duplicate — must dedupe
                ),
            }
        ]
    }
    values = agent._extract_field_from_result_payload(payload, "message_id", collect_all=True)
    assert values == ["aaa111", "bbb222", "ccc333"]


def test_substitute_step_parameter_placeholders_resolves_dotted_array_param():
    """Gmail BUG-3 end-to-end: `{{APRIL_10_MESSAGES.message_ids}}` against
    a free-text result must resolve to the full list of IDs found in the
    text, not just the first one, when the parameter schema is an array."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    search_result = {
        "status": "success",
        "result": {
            "structuredContent": {
                "result": (
                    "Found 3 messages matching 'after:2026/04/10 before:2026/04/11':\n"
                    "\n"
                    "1. From: a@x.com\n"
                    "   **Message ID:** aaa111\n"
                    "2. From: b@x.com\n"
                    "   **Message ID:** bbb222\n"
                    "3. From: c@x.com\n"
                    "   **Message ID:** ccc333\n"
                )
            }
        },
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={"message_ids": "{{APRIL_10_MESSAGES.message_ids}}"},
        param_properties={"message_ids": {"type": "array", "items": {"type": "string"}}},
        full_schema={
            "type": "object",
            "required": ["message_ids"],
            "properties": {"message_ids": {"type": "array", "items": {"type": "string"}}},
        },
        action_description="Fetch full content for April 10 messages",
        my_results={"{{APRIL_10_MESSAGES}}": search_result},
        tool_name="google-mcp__get_gmail_messages_content_batch",
    )

    assert substituted["message_ids"] == ["aaa111", "bbb222", "ccc333"]


def test_substitute_step_parameter_placeholders_cross_placeholder_fallback():
    """Calendar BUG-1: the LLM references `{{EVENT_ID_FROM_SEARCH}}` but
    only assigned `{{EVENT_DETAILS}}`.  Cross-placeholder fallback must
    extract the event id from the single prior successful result."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    get_events_result = {
        "status": "success",
        "result": {
            "structuredContent": {
                "result": (
                    "Event found in primary calendar:\n"
                    "Title: Spark Test Event\n"
                    "Time: 2026-04-18T12:00:00Z\n"
                    "ID: rl5p13b7jgd570rlph28stpaug"
                )
            }
        },
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "delete",
            "calendar_id": "primary",
            "event_id": "{{EVENT_ID_FROM_SEARCH}}",
        },
        param_properties={
            "action": {"type": "string"},
            "calendar_id": {"type": "string"},
            "event_id": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {"type": "string"},
                "calendar_id": {"type": "string"},
                "event_id": {"type": "string"},
            },
        },
        action_description="Delete Spark Test event",
        my_results={"{{EVENT_DETAILS}}": get_events_result},
        tool_name="google-mcp__manage_event",
    )

    assert substituted["event_id"] == "rl5p13b7jgd570rlph28stpaug"
    assert substituted["action"] == "delete"
    assert substituted["calendar_id"] == "primary"


def test_substitute_step_parameter_placeholders_cross_placeholder_declines_ambiguous():
    """Cross-placeholder fallback must NOT guess when multiple distinct
    candidates exist across prior results — inference / repair handles
    the ambiguity more safely."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    first = {
        "status": "success",
        "result": {"structuredContent": {"result": "Event A\nID: event-aaa-111"}},
    }
    second = {
        "status": "success",
        "result": {"structuredContent": {"result": "Event B\nID: event-bbb-222"}},
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "delete",
            "event_id": "{{UNKNOWN_PLACEHOLDER}}",
        },
        param_properties={
            "action": {"type": "string"},
            "event_id": {"type": "string"},
        },
        full_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "event_id": {"type": "string"},
            },
        },
        action_description="Delete event",
        my_results={"{{FIRST}}": first, "{{SECOND}}": second},
        tool_name="google-mcp__manage_event",
    )

    # Ambiguous → leaves the literal placeholder for the strip step to
    # drop and the repair-plan flow to re-plan against.
    assert substituted["event_id"] == "{{UNKNOWN_PLACEHOLDER}}"


def test_strip_leftover_placeholder_parameters_drops_unresolved_non_required():
    """Defensive final pass: any non-required parameter still shaped like
    a placeholder after substitution/inference must be dropped before
    reaching MCP."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    cleaned = agent._strip_leftover_placeholder_parameters(
        parameters={
            "action": "delete",
            "calendar_id": "primary",
            "event_id": "{{EVENT_ID_FROM_SEARCH}}",
            "notes": "<<NOTES>>",
        },
        required_params=["action"],
        tool_name="google-mcp__manage_event",
    )

    assert "event_id" not in cleaned
    assert "notes" not in cleaned
    assert cleaned == {"action": "delete", "calendar_id": "primary"}


def test_strip_leftover_placeholder_parameters_preserves_required_literals():
    """Required parameters carrying literal placeholders are NOT silently
    dropped — the upstream unresolved-required check must keep routing
    them through the repair-plan flow."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    cleaned = agent._strip_leftover_placeholder_parameters(
        parameters={
            "event_id": "{{EVENT_ID}}",
            "calendar_id": "primary",
        },
        required_params=["event_id", "calendar_id"],
        tool_name="google-mcp__manage_event",
    )

    # Required placeholder survives — repair flow handles it.
    assert cleaned["event_id"] == "{{EVENT_ID}}"
    assert cleaned["calendar_id"] == "primary"


def test_validate_inferred_parameters_drops_fabricated_array_items():
    """Gmail BUG-3 defense-in-depth: the LLM hallucinates incrementing
    message IDs based on a single real ID from prior context.  The array
    validator must keep only items that literally appear in prior results
    and drop the fabricated ones."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    my_results = {
        "{{SEARCH}}": {
            "status": "success",
            "result": {
                "structuredContent": {
                    "result": ("Found 10 messages:\n" "1. **Message ID:** 19d78b1d775ca3e0\n")
                }
            },
        }
    }

    validated = agent._validate_inferred_parameters_against_results(
        inferred_parameters={
            "message_ids": [
                "19d78b1d775ca3e0",  # real ID from prior result
                "19d4e8c9d1f2a3b4",  # hallucinated
                "19d2a1e7b0d9c8f5",  # hallucinated
            ]
        },
        my_results=my_results,
        param_properties={"message_ids": {"type": "array", "items": {"type": "string"}}},
        full_schema={"properties": {"message_ids": {"type": "array", "items": {"type": "string"}}}},
        tool_name="google-mcp__get_gmail_messages_content_batch",
    )

    assert validated == {"message_ids": ["19d78b1d775ca3e0"]}


def test_validate_inferred_parameters_removes_array_when_all_fabricated():
    """When every array item is fabricated, drop the parameter entirely so
    the unresolved-required flow can fire a repair-plan instead of sending
    an empty or bogus list to MCP."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    my_results = {
        "{{SEARCH}}": {
            "status": "success",
            "result": {"structuredContent": {"result": "Found 0 messages."}},
        }
    }

    validated = agent._validate_inferred_parameters_against_results(
        inferred_parameters={"message_ids": ["bogus-1", "bogus-2"]},
        my_results=my_results,
        param_properties={"message_ids": {"type": "array", "items": {"type": "string"}}},
        full_schema={"properties": {"message_ids": {"type": "array", "items": {"type": "string"}}}},
        tool_name="google-mcp__get_gmail_messages_content_batch",
    )

    assert "message_ids" not in validated


def test_validate_inferred_parameters_keeps_real_ids_from_text_payload():
    """The validator accepts items whose string value appears anywhere in
    the joined text of prior results — even when the structure doesn't
    expose them as discrete record fields."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    my_results = {
        "{{SEARCH}}": {
            "status": "success",
            "result": {
                "structuredContent": {
                    "result": (
                        "Found 3 messages:\n"
                        "1. **Message ID:** aaa111\n"
                        "2. **Message ID:** bbb222\n"
                        "3. **Message ID:** ccc333\n"
                    )
                }
            },
        }
    }

    validated = agent._validate_inferred_parameters_against_results(
        inferred_parameters={"message_ids": ["aaa111", "bbb222", "ccc333"]},
        my_results=my_results,
        param_properties={"message_ids": {"type": "array", "items": {"type": "string"}}},
        full_schema={"properties": {"message_ids": {"type": "array", "items": {"type": "string"}}}},
        tool_name="google-mcp__get_gmail_messages_content_batch",
    )

    assert validated == {"message_ids": ["aaa111", "bbb222", "ccc333"]}


def test_collect_text_chunks_from_payload_walks_nested_structures():
    """Every non-empty string inside a nested dict/list payload must be
    visited so text-fallback extraction can see FastMCP's
    `content[].text` serialization."""
    payload = {
        "structuredContent": {
            "result": "ID: abc-123\nTitle: Spark",
        },
        "content": [
            {"type": "text", "text": "Related: xyz-789"},
            "Orphan string chunk",
            42,  # non-string values are skipped
        ],
    }
    chunks = Agent._collect_text_chunks_from_payload(payload)
    combined = "\n".join(chunks)
    assert "ID: abc-123" in combined
    assert "Related: xyz-789" in combined
    assert "Orphan string chunk" in combined


# ---------------------------------------------------------------------------
# v0.20260419.0 regression tests — `[N]` integer index syntax + nested
# dict/list placeholder substitution + recursive leftover stripping
# ---------------------------------------------------------------------------


def test_parse_placeholder_predicate_accepts_integer_index():
    """Bare `[N]` and `[-N]` must parse to a positional selector marker."""
    assert Agent._parse_placeholder_predicate("[0]") == {Agent.PLACEHOLDER_INDEX_KEY: 0}
    assert Agent._parse_placeholder_predicate("[3]") == {Agent.PLACEHOLDER_INDEX_KEY: 3}
    assert Agent._parse_placeholder_predicate("[-1]") == {Agent.PLACEHOLDER_INDEX_KEY: -1}
    # Non-integer numerics still go through the value path (require key=).
    assert Agent._parse_placeholder_predicate("[1.5]") is None
    assert Agent._parse_placeholder_predicate("[abc]") is None


def test_parse_placeholder_reference_supports_integer_index():
    """`{{WORKSHEET_LIST[0].id}}` must split into the index marker."""
    base, field, predicate = Agent._parse_placeholder_reference("{{WORKSHEET_LIST[0].id}}")
    assert base == "{{WORKSHEET_LIST}}"
    assert field == "id"
    assert predicate == {Agent.PLACEHOLDER_INDEX_KEY: 0}

    base, field, predicate = Agent._parse_placeholder_reference("{{LIST[-1]}}")
    assert base == "{{LIST}}"
    assert field is None
    assert predicate == {Agent.PLACEHOLDER_INDEX_KEY: -1}


def test_iter_indexable_records_prefers_top_level_value_wrapper():
    """MS Graph wrap shape: `{value: [...]}` should be the indexable list."""
    payload = {
        "value": [
            {"id": "{00000000-0001-0000-0000-000000000000}", "name": "Sheet1"},
            {"id": "{00000000-0002-0000-0000-000000000000}", "name": "Sheet2"},
        ]
    }
    records = Agent._iter_indexable_records(payload)
    assert len(records) == 2
    assert records[0]["name"] == "Sheet1"
    assert records[1]["name"] == "Sheet2"


def test_iter_indexable_records_handles_top_level_list():
    payload = [{"id": "a"}, {"id": "b"}]
    records = Agent._iter_indexable_records(payload)
    assert [r["id"] for r in records] == ["a", "b"]


def test_iter_indexable_records_walks_nested_when_no_wrapper_match():
    """If no wrapper key carries a list, fall back to depth-first walk."""
    payload = {
        "metadata": {"timestamp": "now"},
        "deep": {"layer": {"things": [{"name": "first"}, {"name": "second"}]}},
    }
    records = Agent._iter_indexable_records(payload)
    assert [r["name"] for r in records] == ["first", "second"]


def test_filter_records_by_predicate_dispatches_index_path():
    payload = {
        "value": [
            {"id": "{00000000-0001-0000-0000-000000000000}", "name": "Sheet1"},
            {"id": "{00000000-0002-0000-0000-000000000000}", "name": "Sheet2"},
            {"id": "{00000000-0003-0000-0000-000000000000}", "name": "Sheet3"},
        ]
    }
    first = Agent._filter_records_by_predicate(payload, {Agent.PLACEHOLDER_INDEX_KEY: 0})
    assert first["name"] == "Sheet1"

    last = Agent._filter_records_by_predicate(payload, {Agent.PLACEHOLDER_INDEX_KEY: -1})
    assert last["name"] == "Sheet3"

    out_of_range = Agent._filter_records_by_predicate(payload, {Agent.PLACEHOLDER_INDEX_KEY: 99})
    assert out_of_range is None

    collected = Agent._filter_records_by_predicate(
        payload, {Agent.PLACEHOLDER_INDEX_KEY: 1}, collect_all=True
    )
    assert isinstance(collected, list)
    assert len(collected) == 1
    assert collected[0]["name"] == "Sheet2"


def test_extract_field_with_index_predicate_picks_positional_record():
    """End-to-end: `{{WORKSHEET_LIST[0].id}}` resolves to the first sheet's id."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    payload = {
        "value": [
            {"id": "{00000000-0001-0000-0000-000000000000}", "name": "Sheet1"},
            {"id": "{00000000-0002-0000-0000-000000000000}", "name": "Sheet2"},
        ]
    }
    assert (
        agent._extract_field_from_result_payload(
            payload, "id", predicate={Agent.PLACEHOLDER_INDEX_KEY: 0}
        )
        == "{00000000-0001-0000-0000-000000000000}"
    )
    assert (
        agent._extract_field_from_result_payload(
            payload, "id", predicate={Agent.PLACEHOLDER_INDEX_KEY: 1}
        )
        == "{00000000-0002-0000-0000-000000000000}"
    )


def test_substitute_step_parameter_placeholders_resolves_index_predicate():
    """Dev #1 v0.20260418.0 Excel B2: `{{WORKSHEET_LIST[0].id}}` must
    resolve to the first worksheet's GUID, not silently fall back to the
    Book.xlsx driveItemId via the kind-aware fallback."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{WORKSHEET_LIST}}": {
            "success": True,
            "result": {
                "value": [
                    {"id": "{00000000-0001-0000-0000-000000000000}", "name": "Sheet1"},
                    {"id": "{00000000-0002-0000-0000-000000000000}", "name": "Sheet2"},
                ]
            },
        }
    }
    parameters = {"workbookWorksheetId": "{{WORKSHEET_LIST[0].id}}"}
    param_properties = {"workbookWorksheetId": {"type": "string"}}
    full_schema = {
        "type": "object",
        "required": ["workbookWorksheetId"],
        "properties": {"workbookWorksheetId": {"type": "string"}},
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters=parameters,
        param_properties=param_properties,
        full_schema=full_schema,
        action_description="Get the first worksheet from Book.xlsx",
        my_results=my_results,
        tool_name="ms365-mcp__get-excel-worksheet",
    )

    assert substituted["workbookWorksheetId"] == "{00000000-0001-0000-0000-000000000000}"


def test_substitute_step_parameter_placeholders_resolves_nested_dict_placeholder():
    """Dev #1 v0.20260418.0 OneDrive: a placeholder nested inside
    `parentReference: {id: "{{FOLDER[name='X'].id}}"}` must be substituted
    by the recursive nested-substitution pass — without it the literal
    placeholder string is sent to MS Graph."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{SPARK_FOLDER_SEARCH}}": {
            "success": True,
            "result": {
                "value": [
                    {"id": "drive-item-attachments", "name": "Attachments"},
                    {"id": "drive-item-spark-test", "name": "Spark Test"},
                ]
            },
        }
    }
    parameters = {
        "driveItemId": "01-source-file-id",
        "parentReference": {"id": "{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}"},
    }
    param_properties = {
        "driveItemId": {"type": "string"},
        "parentReference": {"type": "object"},
    }
    full_schema = {
        "type": "object",
        "required": ["driveItemId", "parentReference"],
        "properties": {
            "driveItemId": {"type": "string"},
            "parentReference": {"type": "object"},
        },
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters=parameters,
        param_properties=param_properties,
        full_schema=full_schema,
        action_description="Move file to the Spark Test folder",
        my_results=my_results,
        tool_name="ms365-mcp__move-rename-onedrive-item",
    )

    assert substituted["parentReference"] == {"id": "drive-item-spark-test"}
    assert substituted["driveItemId"] == "01-source-file-id"


def test_substitute_step_parameter_placeholders_resolves_nested_list_placeholder():
    """Lists of dicts also recurse so positional / name predicates inside
    an array element are honored."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    my_results = {
        "{{ATTENDEE_SEARCH}}": {
            "success": True,
            "result": {
                "value": [
                    {"address": "alice@example.com", "name": "Alice"},
                    {"address": "bob@example.com", "name": "Bob"},
                ]
            },
        }
    }
    parameters = {
        "attendees": [
            {"emailAddress": {"address": "{{ATTENDEE_SEARCH[name='Alice'].address}}"}},
        ]
    }
    param_properties = {"attendees": {"type": "array"}}
    full_schema = {
        "type": "object",
        "properties": {"attendees": {"type": "array"}},
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters=parameters,
        param_properties=param_properties,
        full_schema=full_schema,
        action_description="Add Alice as attendee",
        my_results=my_results,
        tool_name="ms365-mcp__update-calendar-event",
    )

    assert substituted["attendees"][0]["emailAddress"]["address"] == "alice@example.com"


def test_substitute_step_parameter_placeholders_caps_recursion_depth():
    """Pathological deeply-nested LLM payloads must not trigger uncontrolled recursion."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    deep_value: dict = {"placeholder": "{{FOO.id}}"}
    for _ in range(20):
        deep_value = {"nested": deep_value}

    my_results = {"{{FOO}}": {"success": True, "result": {"id": "real-id"}}}
    parameters = {"complex_param": deep_value}
    param_properties = {"complex_param": {"type": "object"}}
    full_schema = {"type": "object", "properties": {"complex_param": {"type": "object"}}}

    # Should not raise RecursionError; placeholder beyond depth cap stays as literal.
    substituted = agent._substitute_step_parameter_placeholders(
        parameters=parameters,
        param_properties=param_properties,
        full_schema=full_schema,
        action_description="",
        my_results=my_results,
        tool_name="dummy-tool",
    )
    assert substituted is not None


def test_find_unresolved_placeholder_leaves_walks_nested_structures():
    """The leaf finder must report dotted/indexed paths for nested literals."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    leaves = agent._find_unresolved_placeholder_leaves(
        {
            "parentReference": {"id": "{{FOO.id}}"},
            "attendees": [
                {"emailAddress": {"address": "{{ATTENDEE.email}}"}},
                {"emailAddress": {"address": "real@example.com"}},
            ],
            "subject": "Resolved literal",
        },
        base_path="parameters",
    )
    paths = sorted(leaf["param_path"] for leaf in leaves)
    assert paths == [
        "parameters.attendees[0].emailAddress.address",
        "parameters.parentReference.id",
    ]


def test_strip_leftover_placeholder_parameters_drops_top_level_with_nested_unresolved():
    """A non-required top-level dict containing an unresolved nested
    placeholder leaf must be dropped, not silently passed to MCP."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    parameters = {
        "driveItemId": "real-id",
        "parentReference": {"id": "{{MISSING.id}}"},  # nested unresolved
        "subject": "OK",
    }

    cleaned = agent._strip_leftover_placeholder_parameters(
        parameters=parameters,
        required_params=["driveItemId"],
        tool_name="ms365-mcp__move-rename-onedrive-item",
    )

    assert "parentReference" not in cleaned
    assert cleaned["driveItemId"] == "real-id"
    assert cleaned["subject"] == "OK"


def test_strip_leftover_placeholder_parameters_keeps_required_with_nested_unresolved():
    """Required dict params with nested unresolved placeholders are NOT
    dropped (the repair-plan flow handles them) but the warning event
    still fires."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    parameters = {"parentReference": {"id": "{{MISSING.id}}"}}

    cleaned = agent._strip_leftover_placeholder_parameters(
        parameters=parameters,
        required_params=["parentReference"],
        tool_name="ms365-mcp__move-rename-onedrive-item",
    )

    # Kept so the existing repair-plan path can react to the still-unresolved required param.
    assert cleaned == {"parentReference": {"id": "{{MISSING.id}}"}}


def test_has_resolved_required_parameter_value_rejects_nested_unresolved():
    """Required dict/list params with any nested unresolved placeholder
    must report as unresolved so the repair-plan flow fires (without this
    the OneDrive parentReference bug never triggers a repair attempt)."""
    agent = object.__new__(Agent)
    agent.agent_id = "ms365-assistant"

    assert (
        agent._has_resolved_required_parameter_value({"id": "real-id"}, {"type": "object"}) is True
    )
    assert (
        agent._has_resolved_required_parameter_value({"id": "{{MISSING.id}}"}, {"type": "object"})
        is False
    )
    assert (
        agent._has_resolved_required_parameter_value(
            [{"name": "{{MISSING.name}}"}], {"type": "array"}
        )
        is False
    )


# ---------------------------------------------------------------------------
# v0.20260420.0 regression tests
#
# Dev feedback traced to today's release:
#   A. Google Calendar: filtered placeholders like
#      {{EVENT_SEARCH[summary='Spark Test 2'].id}} drop the event_id because
#      the predicate filter cannot match against Google MCP's text-blob
#      payloads.
#   B. Gmail: `{{DRAFT_CONTENT.body}}\n\nHappy Birthday!` arrives literally
#      because embedded placeholders are not recognized by the whole-string
#      matcher, AND `.body` fails because the Gmail MCP uses a
#      `--- BODY ---` separator rather than `Body: value`.
# ---------------------------------------------------------------------------


# The Google Calendar `get_events` response shape: wrapped in
# structuredContent.result, the events are rendered as a bulleted text
# block with an inline ID field. This is the exact format from the field
# report logs (v0.20260420.0, google-mcp__get_events).
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


def test_parse_text_blocks_into_records_recovers_bulleted_google_calendar_events():
    """Google Calendar MCP returns a bulleted text block. The new parser
    must lift each bullet into a synthetic dict record with title aliases
    populated so predicate filters work against free-text payloads."""
    records = Agent._parse_text_blocks_into_records(GOOGLE_CALENDAR_GET_EVENTS_TEXT)

    assert len(records) == 3
    titles = [record.get("summary") for record in records]
    assert titles == ["Spark Test 2", "Ruby Daily Sync", "Emerald Daily Sync"]

    # Title should be exposed under every alias so predicates written
    # against any common name-field still resolve.
    for record in records:
        assert record["summary"] == record["title"] == record["name"] == record["subject"]

    # Key:value pairs inside the block must be captured — the inline ID
    # that lives on the same line as the link separator is critical
    # because the LLM emits `{{EVENT_SEARCH[summary='...'].id}}` to
    # extract exactly this field.
    assert records[0]["id"] == "rnnbrh9v8lh853dkvit1d8a234"
    assert records[1]["id"] == "09jdummda51b9m0fqlomnan8em"


def test_parse_text_blocks_into_records_returns_empty_for_non_bulleted_text():
    """Free narrative prose without bullets must not yield false-positive
    records — predicate matching depends on this to fail cleanly rather
    than silently match noise."""
    prose = (
        "The calendar has several events today. The first is Spark Test 2 at 10:00, "
        "followed by Ruby Daily Sync at noon."
    )
    assert Agent._parse_text_blocks_into_records(prose) == []
    assert Agent._parse_text_blocks_into_records(None) == []
    assert Agent._parse_text_blocks_into_records({}) == []


def test_filter_records_by_predicate_falls_back_to_text_blocks():
    """With no structured records to match, the predicate path must parse
    the free-text payload into synthetic records and match against those.
    This is the Google Calendar regression fix: the payload is wrapped as
    {"result": "<bulleted text>"} and the predicate `summary='Spark Test 2'`
    has to find the matching block anyway."""
    payload = {"result": GOOGLE_CALENDAR_GET_EVENTS_TEXT}
    matched = Agent._filter_records_by_predicate(payload, {"summary": "Spark Test 2"})

    assert matched is not None
    assert matched["summary"] == "Spark Test 2"
    assert matched["id"] == "rnnbrh9v8lh853dkvit1d8a234"


def test_substitute_step_parameter_placeholders_resolves_predicate_on_text_payload():
    """End-to-end: `{{EVENT_SEARCH[summary='Spark Test 2'].id}}` must
    resolve against a Google Calendar text-blob payload so the next
    manage_event step receives a real event_id."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    my_results = {
        "{{EVENT_SEARCH}}": {
            "status": "success",
            "result": {"result": GOOGLE_CALENDAR_GET_EVENTS_TEXT},
        }
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "action": "update",
            "event_id": "{{EVENT_SEARCH[summary='Spark Test 2'].id}}",
            "start_time": "2026-04-21T10:00:00+03:00",
            "end_time": "2026-04-21T10:45:00+03:00",
        },
        param_properties={
            "action": {"type": "string"},
            "event_id": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
        },
        full_schema={},
        action_description="Reschedule Spark Test 2",
        my_results=my_results,
        tool_name="google-mcp__manage_event",
    )

    assert substituted["event_id"] == "rnnbrh9v8lh853dkvit1d8a234"
    assert substituted["action"] == "update"


# ---------------------------------------------------------------------------
# Embedded placeholder substitution (Gmail draft body bug)
# ---------------------------------------------------------------------------


def test_contains_embedded_placeholder_detects_mixed_strings():
    """The embedded-placeholder scanner must fire on strings where a
    ``{{...}}`` token is surrounded by literal text, without ever
    reporting true on placeholder-free text."""
    assert Agent._contains_embedded_placeholder("{{DRAFT.body}}\n\nHappy Birthday!") is True
    assert Agent._contains_embedded_placeholder("Prefix {{FOO.id}} suffix") is True
    # Pure placeholder strings may also match (caller checks
    # _is_placeholder_like_value first).
    assert Agent._contains_embedded_placeholder("{{FOO.id}}") is True
    # Empty / non-string / no-token values must not match.
    assert Agent._contains_embedded_placeholder("no placeholder here") is False
    assert Agent._contains_embedded_placeholder("") is False
    assert Agent._contains_embedded_placeholder(None) is False
    assert Agent._contains_embedded_placeholder(123) is False


def test_substitute_embedded_placeholders_splices_resolved_values():
    """Gmail regression: the LLM emits
    `body="{{DRAFT_CONTENT.body}}\n\nHappy Birthday!"`. The resolver
    must splice in the real body text and preserve the literal suffix."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    successful_results = {
        "{{DRAFT_CONTENT}}": {
            "status": "success",
            "result": {"subject": "Meeting tomorrow", "body": "Hi Anna,\n\nBest regards"},
        }
    }

    result = agent._substitute_embedded_placeholders(
        text="{{DRAFT_CONTENT.body}}\n\nHappy Birthday!",
        successful_results=successful_results,
    )

    assert result == "Hi Anna,\n\nBest regards\n\nHappy Birthday!"


def test_substitute_embedded_placeholders_leaves_unresolved_tokens_intact():
    """Unresolved tokens must NOT be dropped mid-string — we need them to
    stay literal so `_find_unresolved_placeholder_leaves` can flag the
    parent parameter."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    successful_results = {
        "{{DRAFT_CONTENT}}": {
            "status": "success",
            "result": {"subject": "Meeting"},  # no `body` field
        }
    }

    result = agent._substitute_embedded_placeholders(
        text="{{DRAFT_CONTENT.body}}\n\nHappy Birthday!",
        successful_results=successful_results,
    )

    assert result == "{{DRAFT_CONTENT.body}}\n\nHappy Birthday!"


def test_substitute_embedded_placeholders_does_not_splice_structured_payload():
    """Bare ``{{FOO}}`` inside a larger string must be left intact when the
    referenced payload is a dict/list — we cannot sensibly interpolate a
    structured payload into free text."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    successful_results = {
        "{{FOO}}": {
            "status": "success",
            "result": {"some": "structured", "data": [1, 2, 3]},
        }
    }

    result = agent._substitute_embedded_placeholders(
        text="Prefix {{FOO}} suffix",
        successful_results=successful_results,
    )
    assert result == "Prefix {{FOO}} suffix"


def test_substitute_step_parameter_placeholders_resolves_embedded_body():
    """End-to-end: Gmail draft body with literal Happy Birthday! must be
    resolved through the whole substitution pipeline — not just the
    embedded helper in isolation."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    # Shape the payload the way Gmail MCP actually returns it: a free-text
    # blob with Subject on a `Subject: value` line and the body under a
    # `--- BODY ---` separator. Both Fix 2 (embedded substitution) and
    # Fix 3 (section separator field extraction) must cooperate.
    gmail_payload_text = (
        "Message ID: 19d9be86eb54a312\n"
        "Subject: Meeting tomorrow\n"
        "From: sender@example.com\n"
        "To: recipient@example.com\n"
        "\n"
        "--- BODY ---\n"
        "Hi Anna,\n\n"
        "I wanted to reach out regarding our meeting scheduled for tomorrow.\n\n"
        "Best regards\n"
    )

    my_results = {
        "{{DRAFT_CONTENT}}": {
            "status": "success",
            "result": {"result": gmail_payload_text},
        }
    }

    substituted = agent._substitute_step_parameter_placeholders(
        parameters={
            "subject": "{{DRAFT_CONTENT.subject}}",
            "body": "{{DRAFT_CONTENT.body}}\n\nHappy Birthday!",
            "to": ["recipient@example.com"],
        },
        param_properties={
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "to": {"type": "array"},
        },
        full_schema={},
        action_description="Update draft appending Happy Birthday",
        my_results=my_results,
        tool_name="google-mcp__draft_gmail_message",
    )

    # Subject resolves via the existing label-line extractor. The field
    # report confirms the pre-fix behavior already half-resolved subject
    # to the first whitespace-terminated token ("Meeting"); improving
    # multi-word label capture is a separate scope item.
    assert substituted["subject"] == "Meeting"
    # The body must contain both the resolved original body and the
    # literal suffix the LLM appended — this is the actual Fix 2 + Fix 3
    # cooperation we care about here.
    assert "Hi Anna," in substituted["body"]
    assert "Best regards" in substituted["body"]
    assert substituted["body"].endswith("Happy Birthday!")


def test_find_unresolved_placeholder_leaves_detects_embedded_tokens():
    """Embedded (not whole-string) unresolved placeholders must still flow
    through the leftover-strip flow so non-required params get dropped
    and devs see the warning."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    leaves = agent._find_unresolved_placeholder_leaves(
        "{{DRAFT.body}}\n\nHappy Birthday!",
        base_path="body",
    )

    assert leaves == [
        {"param_path": "body", "placeholder": "{{DRAFT.body}}"},
    ]


def test_find_unresolved_placeholder_leaves_detects_multiple_embedded_tokens():
    """Multiple unresolved tokens inside a single string yield one leaf
    per token so the observability warning can enumerate them all."""
    agent = object.__new__(Agent)
    agent.agent_id = "google-assistant"

    leaves = agent._find_unresolved_placeholder_leaves(
        "Prefix {{A.x}} middle {{B.y}} suffix",
        base_path="template",
    )

    placeholders = sorted(leaf["placeholder"] for leaf in leaves)
    assert placeholders == ["{{A.x}}", "{{B.y}}"]
    assert all(leaf["param_path"] == "template" for leaf in leaves)


# ---------------------------------------------------------------------------
# --- SECTION --- separator field extraction (Gmail body bug)
# ---------------------------------------------------------------------------


def test_extract_field_values_from_text_recognizes_section_separator():
    """Gmail's `get_gmail_message_content` returns the body under
    `--- BODY ---` rather than `Body: ...`. The extractor must pick up
    everything between the opening separator and the next one (or EOS)."""
    text = (
        "Subject: Meeting tomorrow\n"
        "From: sender@example.com\n"
        "\n"
        "--- BODY ---\n"
        "Hi Anna,\n\n"
        "Best regards\n"
    )

    body_values = Agent._extract_field_values_from_text(text, "body")
    assert len(body_values) == 1
    assert body_values[0].startswith("Hi Anna,")
    assert body_values[0].rstrip().endswith("Best regards")


def test_extract_field_values_from_text_section_separator_stops_at_next_section():
    """When a second `--- XYZ ---` appears after the body, the body
    capture must terminate there — otherwise we'd swallow subsequent
    fields into a single over-long value."""
    text = "--- BODY ---\n" "Body paragraph one.\n" "\n" "--- ATTACHMENTS ---\n" "- file1.pdf\n"

    body_values = Agent._extract_field_values_from_text(text, "body")
    assert body_values == ["Body paragraph one."]

    attachments = Agent._extract_field_values_from_text(text, "attachments")
    assert attachments == ["- file1.pdf"]


def test_extract_field_values_from_text_section_separator_not_confused_with_prose():
    """Narrative prose with bare `---` rules (no field name sandwiched
    between the dashes) must NOT produce a section-separator match —
    the dashes must flank the requested field name for Pattern 4 to
    fire. This guard avoids false positives on markdown horizontal
    rules or any other triple-dash prose."""
    text = "Some intro text.\n" "---\n" "Narrative sentence without a label.\n" "---\n"
    # Pattern 4 explicitly requires `--- <field> ---` — bare `---` rules
    # must not match. We verify that none of the extracted values came
    # from a section capture (a section capture would include the
    # trailing period from "Narrative sentence without a label.").
    matches = Agent._extract_field_values_from_text(text, "body")
    assert all("Narrative sentence without a label" not in m for m in matches)


# ---------------------------------------------------------------------------
# v0.20260422.0 regression — schema-documented sentinel values must be
# recognized as concrete values, not guesses.  Before this fix, tool-chains
# whose planner emitted a placeholder for a parameter whose description
# already documented a sentinel (e.g. "use 'me' for the current user's drive")
# collapsed silently: inference refused to return the sentinel, required-param
# repair fired, auto-discovery inserted an unrelated step without patching the
# failing param, and the replan_attempted guard blocked the second pass.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_infer_tool_parameters_prompt_documents_schema_sentinel_rule():
    """The inference system prompt must teach the LLM that sentinel values
    documented in a parameter's own Description text (e.g. "use 'me' for
    the current user") are valid concrete values, not guesses.  The guard
    must be generic (no hardcoded vendor / MCP / parameter names) AND keep
    the anti-guessing rules intact for every other case.

    Concrete regression case: a planner-emitted `driveId: {{DRIVE_ID}}`
    whose schema description documents the `"me"` sentinel must be
    resolvable by inference without an auto-discovery repair pass.
    """
    agent = object.__new__(Agent)
    agent.agent_id = "test-agent"
    agent.model = SimpleNamespace(chat=AsyncMock(return_value='{"driveId": "me"}'))

    with patch("muxi.runtime.formation.agents.agent.observability.observe"):
        result = await agent._infer_tool_parameters(
            tool_name="ms365-mcp__get-drive-root-item",
            required_params=["driveId"],
            param_properties={
                "driveId": {
                    "type": "string",
                    "description": "The drive id (use 'me' for the current user's drive)",
                },
            },
            full_schema={
                "type": "object",
                "properties": {
                    "driveId": {
                        "type": "string",
                        "description": "The drive id (use 'me' for the current user's drive)",
                    },
                },
                "required": ["driveId"],
            },
            action_description="Get the root item of the user's OneDrive",
            user_request="What's in cell A1 of Book.xlsx?",
        )

    assert result == {"driveId": "me"}

    # The system prompt captured by the mock must carry the generic sentinel
    # rule.  Inference calls model.chat with keyword args.
    call = agent.model.chat.call_args
    messages = call.kwargs.get("messages") or (call.args[0] if call.args else None)
    assert messages is not None
    system_prompt = messages[0]["content"]

    # Generic framing — the guidance is schema-driven, not vendor-specific.
    assert "Documented sentinel values" in system_prompt
    assert "parameter's own Description" in system_prompt

    # Scope the vendor-specificity check to ONLY the sentinel-rule block we
    # added (the caller-provided tool schema legitimately contains parameter
    # names and vendor-specific descriptions that we DO want echoed back to
    # the LLM).  The sentinel block starts at "Documented sentinel values"
    # and ends at the next blank line before the "If you cannot determine"
    # section.
    sentinel_block_start = system_prompt.index("Documented sentinel values")
    sentinel_block_end = system_prompt.index("If you cannot determine", sentinel_block_start)
    sentinel_block = system_prompt[sentinel_block_start:sentinel_block_end]

    for vendor_token in ("driveId", "userId", "Microsoft", "Graph"):
        assert vendor_token not in sentinel_block, (
            f"sentinel-rule block must stay generic — found vendor-specific "
            f"token '{vendor_token}' in the added instruction text"
        )
    # The anti-guessing guardrail is preserved verbatim for unrelated IDs.
    assert "Do NOT invent placeholder/default values" in system_prompt
    assert "leave it unresolved rather than guessing" in system_prompt


@pytest.mark.asyncio
async def test_infer_tool_parameters_sentinel_values_survive_post_closed_checks():
    """A short concrete sentinel string like `"me"` must survive every
    post-9f99e022 fail-closed guard so inference can return it as a real
    value.  This pins the contract: `_is_placeholder_like_value`,
    `_is_sentinel_placeholder_value`, and `_get_unresolved_required_parameters`
    all agree the sentinel is resolved."""
    agent = object.__new__(Agent)

    # A real, concrete string value — not a placeholder token.
    assert Agent._is_placeholder_like_value("me") is False
    # Not one of the LLM-invented "please inject this" sentinels
    # (auto-injected / from_server / etc.), so _merge_parameter_candidates
    # does not discard it.
    assert Agent._is_sentinel_placeholder_value("me") is False

    # And the unresolved-required check agrees: a step whose parameter is
    # `"me"` is treated as fully resolved, so no repair path fires.
    unresolved = agent._get_unresolved_required_parameters(
        parameters={"driveId": "me"},
        required_params=["driveId"],
        param_properties={"driveId": {"type": "string"}},
        full_schema={
            "required": ["driveId"],
            "properties": {"driveId": {"type": "string"}},
        },
    )
    assert unresolved == []
