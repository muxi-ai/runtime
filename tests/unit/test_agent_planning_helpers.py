"""Focused tests for agent planning helper guardrails."""

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
