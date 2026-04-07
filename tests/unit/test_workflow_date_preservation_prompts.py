"""Tests for prompt guardrails that preserve exact dates during workflow synthesis."""

from muxi.runtime.datatypes.workflow import SubTask
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.workflow.executor import WorkflowExecutor


def test_workflow_synthesis_system_prompt_preserves_absolute_dates():
    overlord = object.__new__(Overlord)

    prompt = overlord._get_workflow_synthesis_system_prompt()

    assert "Preserve explicit dates, weekdays, times, and time ranges exactly" in prompt
    assert "Do not convert absolute dates or times into relative wording" in prompt
    assert "'today', 'tomorrow', or 'yesterday'" in prompt


def test_workflow_executor_task_prompt_keeps_prior_dates_and_adds_guardrail():
    executor = object.__new__(WorkflowExecutor)
    task = SubTask(
        id="task_synthesis",
        description="Synthesize the calendar and email findings into a briefing.",
        required_capabilities=["writing"],
        estimated_complexity=4.0,
    )
    context = {
        "inputs": {
            "from_task_1": {
                "main": {
                    "result": "Calendar event: Tuesday, April 7, 2026 from 3:00 PM to 4:00 PM."
                }
            }
        }
    }

    prompt = executor._create_task_prompt(task, context)

    assert "Tuesday, April 7, 2026 from 3:00 PM to 4:00 PM" in prompt
    assert "Preserve explicit dates, weekdays, times, and time ranges" in prompt
    assert "Do not rewrite absolute dates/times into relative labels" in prompt
