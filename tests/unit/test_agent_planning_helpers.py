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
