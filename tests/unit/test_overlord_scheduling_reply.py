"""The overlord answers every scheduling request itself.

When the request analyzer marks a message as a scheduling request, the overlord creates
the job and replies directly. A failure is never handed on to SOP or agent handling,
where an agent could answer as if a job had been set up when none was:

- the model unavailable -> "try again in a few minutes";
- the schedule not understood -> "could you rephrase it";
- anything else -> a generic failure.

On success the reply reads the schedule back in plain words with its timezone.
"""

import inspect
from datetime import datetime
from typing import Any, Dict, List

import pytest
import pytz

from muxi.runtime.formation.overlord import overlord as overlord_module
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.services.scheduler.parser import (
    ScheduleNotUnderstoodError,
    ScheduleUnavailableError,
)

MESSAGE = "remind me to stretch every day at 3:30pm"


class FakeScheduler:
    """Returns a fixed created job from create_job, or raises a fixed error."""

    def __init__(self, job: Dict[str, Any] = None, error: Exception = None):
        self.job = job
        self.error = error
        self.calls: List[Dict[str, Any]] = []

    async def create_job(self, **kwargs) -> Dict[str, Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.job


@pytest.fixture
def streamed(monkeypatch) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    def record(event_type, content, **metadata):
        events.append({"event_type": event_type, "content": content, **metadata})

    monkeypatch.setattr(overlord_module.streaming, "stream", record)
    return events


def make_overlord(scheduler: FakeScheduler) -> Overlord:
    overlord = Overlord.__new__(Overlord)
    overlord.scheduler_service = scheduler
    return overlord


def recurring(cron: str, timezone: str = "UTC") -> Dict[str, Any]:
    return {
        "job_id": "job_1",
        "cron_expression": cron,
        "scheduled_for": None,
        "timezone": timezone,
        "default_time_used": False,
    }


@pytest.mark.parametrize(
    "error, kind, content",
    [
        (
            ScheduleUnavailableError("model down"),
            "schedule_unavailable",
            "I couldn't set that up right now because scheduling is temporarily unavailable. "
            "Please try again in a few minutes.",
        ),
        (
            ScheduleNotUnderstoodError("not a schedule"),
            "schedule_not_understood",
            "I didn't understand that schedule. Could you rephrase it, for example "
            '"every weekday at 9am"?',
        ),
        (
            RuntimeError("database gone"),
            "scheduler_failed",
            "I couldn't set that up because something went wrong while creating the "
            "scheduled job. Please try again.",
        ),
    ],
)
async def test_failure_is_answered_directly(streamed, error, kind, content):
    overlord = make_overlord(FakeScheduler(error=error))

    response = await overlord._handle_scheduling_request(MESSAGE, "user-1", 0.0)

    assert response.content == content
    assert response.metadata == {"handled_by": "scheduler_service", "error_kind": kind}
    assert [(e["event_type"], e["content"], e["status"]) for e in streamed] == [
        ("completed", content, "error")
    ]


def test_scheduling_branch_returns_the_handler_reply():
    """No fall-through: the branch returns whatever the handler answers."""
    source = inspect.getsource(Overlord._process_sync_chat)
    assert "return await self._handle_scheduling_request(" in source


@pytest.mark.parametrize(
    "job, when",
    [
        (recurring("30 15 * * *"), "every day at 3:30pm (UTC)"),
        (
            recurring("30 15 * * 2,4", "Europe/London"),
            "every Tuesday and Thursday at 3:30pm (Europe/London)",
        ),
        (recurring("0 9 1 * *"), "on the 1st of every month at 9am (UTC)"),
        (recurring("5 4 * 1 2"), 'on the cron schedule "5 4 * 1 2" (UTC)'),
        (
            {
                "job_id": "job_1",
                "cron_expression": None,
                "scheduled_for": pytz.UTC.localize(datetime(2026, 9, 29, 14, 30)),
                "timezone": "Europe/London",
                "default_time_used": False,
            },
            "on Tuesday, September 29, 2026 at 3:30pm (Europe/London)",
        ),
    ],
)
async def test_success_reply_says_when_the_job_runs(streamed, job, when):
    scheduler = FakeScheduler(job=job)
    overlord = make_overlord(scheduler)

    response = await overlord._handle_scheduling_request(MESSAGE, "user-1", 0.0)

    content = (
        f"I've created a scheduled job for you. Your request '{MESSAGE}' has been "
        f"scheduled successfully and will run {when}. (Job ID: job_1)"
    )
    assert response.content == content
    assert response.metadata == {"job_id": "job_1", "handled_by": "scheduler_service"}
    assert [(e["event_type"], e["content"], e["status"]) for e in streamed] == [
        ("completed", content, "success")
    ]
    assert scheduler.calls == [
        {
            "user_id": "user-1",
            "title": f"Scheduled: {MESSAGE}",
            "original_prompt": MESSAGE,
            "schedule": MESSAGE,
            "exclusions": [],
        }
    ]


@pytest.mark.parametrize(
    "job, when",
    [
        (
            {**recurring("30 8 * * *"), "default_time_used": True},
            "every day at 8:30am (UTC)",
        ),
        (
            {
                "job_id": "job_1",
                "cron_expression": None,
                "scheduled_for": pytz.UTC.localize(datetime(2026, 9, 29, 13, 0)),
                "timezone": "America/New_York",
                "default_time_used": True,
            },
            "on Tuesday, September 29, 2026 at 9am (America/New_York)",
        ),
    ],
)
async def test_success_reply_says_when_the_default_time_was_used(streamed, job, when):
    overlord = make_overlord(FakeScheduler(job=job))

    response = await overlord._handle_scheduling_request(MESSAGE, "user-1", 0.0)

    assert response.content == (
        f"I've created a scheduled job for you. Your request '{MESSAGE}' has been "
        f"scheduled successfully and will run {when}. No time was given, so I used the "
        "default time; tell me a time to change it. (Job ID: job_1)"
    )
