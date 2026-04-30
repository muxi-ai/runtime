"""Tests for prompt guardrails that preserve exact dates.

The dedicated workflow-synthesis system prompt was retired when
synthesis collapsed into ``_apply_persona``'s single LLM pass; date
preservation guardrails now live in the persona system prompt itself.
The first test below pins that guardrail in source so future edits to
``_apply_persona`` don't silently strip it.
"""

import inspect

from muxi.runtime.datatypes.workflow import SubTask
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.workflow.executor import WorkflowExecutor


def test_apply_persona_system_prompt_preserves_absolute_dates():
    """Date-preservation guardrail must be present in ``_apply_persona``."""
    source = inspect.getsource(Overlord._apply_persona)

    assert "Preserve explicit dates, weekdays, times, and time ranges exactly" in source
    assert "Do not convert absolute dates or times into relative wording" in source
    assert "'today', 'tomorrow', or 'yesterday'" in source


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
