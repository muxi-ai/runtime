"""Focused tests for agent planning helper guardrails."""

from muxi.runtime.formation.agents.agent import Agent


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
