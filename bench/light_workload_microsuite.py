"""
Light-workload micro-suite for Phase 0 baseline of feature/local-classification.

These prompts are deliberately chosen to NOT trigger heavy planning calls.
The pre-planning pipeline (RequestAnalyzer, AgentRouter, Clarification,
Actionability) is the dominant wall-time cost for this class of request,
which is exactly the surface we're targeting with local classifiers.

Each tuple is ``(label, prompt)``. The label is for reporting only; the
prompt is what gets sent to the runtime.

Categories covered (matches the categorical decisions on the
RequestAnalyzer hot path):

* greeting / acknowledgment      → actionability=False, no planning
* simple question                → actionable but trivial, may skip planning
* scheduler-query intent         → exercises is_scheduler_query_request
* scheduling intent              → exercises is_scheduling_request
* explicit approval (yes/no)     → exercises is_explicit_approval_request
* short follow-up                → exercises buffer + minimal planning
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class LightPrompt:
    label: str
    text: str


LIGHT_WORKLOAD: List[LightPrompt] = [
    LightPrompt("greeting", "hello"),
    LightPrompt("acknowledgment", "thanks"),
    LightPrompt("simple_question", "what time is it?"),
    LightPrompt("help_request", "can you help me?"),
    LightPrompt("scheduler_query", "show my scheduled jobs"),
    LightPrompt("approval_yes", "yes, please proceed"),
    LightPrompt("approval_no", "no, cancel that"),
    LightPrompt("follow_up", "tell me more"),
    LightPrompt("trivia", "what's the weather like?"),
    LightPrompt("scheduling", "schedule a reminder in 5 minutes to drink water"),
]


def all_prompts() -> List[LightPrompt]:
    return list(LIGHT_WORKLOAD)
