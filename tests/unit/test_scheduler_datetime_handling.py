from datetime import datetime, timezone

import pytest
import pytz

from muxi.runtime.services.scheduler.models import ScheduledJob
from muxi.runtime.services.scheduler.service import SchedulerService


@pytest.mark.asyncio
async def test_is_recurring_job_due_treats_naive_last_run_as_utc():
    service = object.__new__(SchedulerService)
    service.check_interval_minutes = 1

    current_time = pytz.timezone("America/Los_Angeles").localize(datetime(2026, 4, 21, 11, 46, 0))
    job = {
        "id": "job-recurring",
        "cron_expression": "* * * * *",
        "last_run_at": "2026-04-21T18:44:50.158030",
    }

    assert await service._is_recurring_job_due(job, current_time) is True


@pytest.mark.asyncio
async def test_is_onetime_job_due_treats_naive_scheduled_for_as_utc():
    service = object.__new__(SchedulerService)
    service.check_interval_minutes = 1

    current_time = datetime(2026, 4, 21, 18, 46, 0, tzinfo=timezone.utc)
    job = {
        "id": "job-onetime",
        "is_recurring": False,
        "scheduled_for": "2026-04-21T18:45:30",
        "last_run_at": None,
    }

    assert await service._is_onetime_job_due(job, current_time) is True


def test_scheduled_job_to_dict_serializes_naive_datetimes_as_utc():
    job = ScheduledJob(
        id="job-1",
        user_id=1,
        title="Test job",
        original_prompt="say hello",
        execution_prompt="say hello",
        is_recurring=False,
        cron_expression=None,
        scheduled_for=datetime(2026, 4, 21, 18, 45, 30),
        created_at=datetime(2026, 4, 21, 18, 40, 0),
        updated_at=datetime(2026, 4, 21, 18, 41, 0),
        last_run_at=datetime(2026, 4, 21, 18, 45, 50, 158030),
    )

    payload = job.to_dict()

    assert payload["scheduled_for"] == "2026-04-21T18:45:30Z"
    assert payload["created_at"] == "2026-04-21T18:40:00Z"
    assert payload["updated_at"] == "2026-04-21T18:41:00Z"
    assert payload["last_run_at"] == "2026-04-21T18:45:50.158030Z"
