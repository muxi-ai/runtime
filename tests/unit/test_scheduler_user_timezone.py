"""A new job's schedule is read in the user's own timezone.

When the user has set a timezone (``/preferences timezone``, kept in the proactive user
channel store), a job created from their request is read in that timezone, else in the
formation's ``scheduler.timezone``. The job keeps that timezone in
``job_metadata["timezone"]`` and the scheduler evaluates its cron (and its exclusion rules) in
it, daylight saving time included: "every day at 9am" for a user in New York fires at 13:00
UTC in summer and 14:00 UTC in winter on a formation that runs in UTC.

Jobs that carry no timezone (created before this, or through the admin API) keep the
formation's timezone, as before.

Runs against a real SQLite scheduler database and a memory-only user channel store; the
prompt rewriter is a small fake that keeps the prompt, and the job type is settled through
the parser's cache.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
import pytz

from muxi.runtime.formation.proactive.user_channels import UserChannelStore
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.long_term import User, UserIdentifier
from muxi.runtime.services.scheduler import parser as parser_module
from muxi.runtime.services.scheduler.models import ScheduledJob, ScheduledJobAudit
from muxi.runtime.services.scheduler.service import SchedulerService

FORMATION_ID = "formation-tz"
NEW_YORK = "America/New_York"
SCHEDULER_TABLES = [
    User.__table__,
    UserIdentifier.__table__,
    ScheduledJob.__table__,
    ScheduledJobAudit.__table__,
]


class FakeRewriter:
    """Keeps the prompt as it is; rewriting it for execution is not what these tests cover."""

    async def rewrite_for_execution(self, original_prompt: str) -> str:
        return original_prompt


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/scheduler.db")
    manager.create_tables(Base.metadata, tables=SCHEDULER_TABLES)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def channel_store():
    return UserChannelStore(formation_id=FORMATION_ID)


def make_service(db_manager, channel_store, **scheduler_config) -> SchedulerService:
    overlord = SimpleNamespace(
        formation_config={"scheduler": {"enabled": True, **scheduler_config}},
        formation_id=FORMATION_ID,
        db_manager=db_manager,
        user_channel_store=channel_store,
    )
    service = SchedulerService(overlord)
    service.prompt_rewriter = FakeRewriter()
    return service


async def create(
    service: SchedulerService, user_id: str, schedule: str, job_type: str = "recurring"
) -> dict:
    service.schedule_parser.cache.cache_job_type(schedule, job_type)
    return await service.create_job(
        user_id=user_id, title="Stretch", original_prompt=schedule, schedule=schedule
    )


async def due_job_ids(service: SchedulerService, utc_time: datetime) -> list:
    """The ids of the jobs due at a moment, with "now" in the formation's timezone, as the
    worker cycle passes it."""
    now = pytz.UTC.localize(utc_time).astimezone(pytz.timezone(service.formation_timezone))
    return [job["id"] for job in await service.get_due_jobs_map_reduce(now)]


async def stored_timezone(service: SchedulerService, job_id: str):
    job = await service.job_manager.get_job(job_id)
    return job["job_metadata"].get("timezone")


async def test_user_timezone_reads_and_fires_the_job_across_dst(db_manager, channel_store):
    await channel_store.set_preferences("ada", timezone=NEW_YORK)
    service = make_service(db_manager, channel_store)  # formation in UTC

    job = await create(service, "ada", "remind me to stretch every day at 9am")

    assert job["cron_expression"] == "0 9 * * *"
    assert job["timezone"] == NEW_YORK
    assert await stored_timezone(service, job["job_id"]) == NEW_YORK

    # Daylight saving time (EDT, UTC-4) until November 1, 2026
    assert await due_job_ids(service, datetime(2026, 10, 30, 13, 0, 30)) == [job["job_id"]]
    assert await due_job_ids(service, datetime(2026, 10, 30, 9, 0, 30)) == []
    assert await due_job_ids(service, datetime(2026, 10, 30, 14, 0, 30)) == []
    # Standard time (EST, UTC-5) from November 1, 2026
    assert await due_job_ids(service, datetime(2026, 11, 2, 14, 0, 30)) == [job["job_id"]]
    assert await due_job_ids(service, datetime(2026, 11, 2, 13, 0, 30)) == []


async def test_user_timezone_reads_a_one_time_job(db_manager, channel_store, monkeypatch):
    # Monday, September 28, 2026, 02:00 UTC: still Sunday evening in New York
    monkeypatch.setattr(
        parser_module, "utc_now", lambda: pytz.UTC.localize(datetime(2026, 9, 28, 2))
    )
    await channel_store.set_preferences("ada", timezone=NEW_YORK)
    service = make_service(db_manager, channel_store)

    job = await create(service, "ada", "remind me tomorrow to call mom", job_type="one_time")

    # Monday 09:00 in New York (EDT)
    assert job["scheduled_for"] == pytz.UTC.localize(datetime(2026, 9, 28, 13, 0))
    assert job["default_time_used"] is True
    assert job["timezone"] == NEW_YORK
    assert await stored_timezone(service, job["job_id"]) == NEW_YORK


async def test_user_without_a_timezone_gets_the_formations(db_manager, channel_store):
    service = make_service(db_manager, channel_store, timezone="Europe/London")

    job = await create(service, "bob", "remind me to stretch every day at 9am")

    assert job["timezone"] == "Europe/London"
    assert await stored_timezone(service, job["job_id"]) == "Europe/London"
    # 09:00 BST is 08:00 UTC
    assert await due_job_ids(service, datetime(2026, 10, 20, 8, 0, 30)) == [job["job_id"]]


async def test_unknown_user_timezone_falls_back_to_the_formations(db_manager, channel_store):
    await channel_store.set_preferences("cy", timezone="Mars/Olympus_Mons")
    service = make_service(db_manager, channel_store)

    job = await create(service, "cy", "remind me to stretch every day at 9am")

    assert job["timezone"] == "UTC"


async def test_formation_without_a_user_channel_store_uses_its_timezone(db_manager):
    service = make_service(db_manager, None, timezone=NEW_YORK)

    job = await create(service, "dee", "remind me to stretch every day at 9am")

    assert job["timezone"] == NEW_YORK


async def test_job_without_a_stored_timezone_keeps_the_formations(db_manager, channel_store):
    # A job created before jobs stored a timezone, or through the admin API, for a user who
    # has since set one
    await channel_store.set_preferences("ada", timezone=NEW_YORK)
    service = make_service(db_manager, channel_store, timezone="Europe/London")
    job_id = await service.job_manager.create_job(
        user_id="ada",
        title="Stretch",
        original_prompt="remind me to stretch every day at 9am",
        execution_prompt="Remind the user to stretch",
        cron_expression="0 9 * * *",
    )

    assert await stored_timezone(service, job_id) is None
    # 09:00 in London (08:00 UTC), not in New York
    assert await due_job_ids(service, datetime(2026, 10, 20, 8, 0, 30)) == [job_id]
    assert await due_job_ids(service, datetime(2026, 10, 20, 13, 0, 30)) == []


async def test_configured_default_time_is_used_and_reported(db_manager, channel_store):
    await channel_store.set_preferences("ada", timezone=NEW_YORK)
    service = make_service(db_manager, channel_store, default_time="8:30am")

    job = await create(service, "ada", "remind me daily to stretch")

    assert job["cron_expression"] == "30 8 * * *"
    assert job["default_time_used"] is True
    assert job["timezone"] == NEW_YORK


async def test_replaced_job_keeps_its_timezone(db_manager, channel_store):
    await channel_store.set_preferences("ada", timezone=NEW_YORK)
    service = make_service(db_manager, channel_store)
    job = await create(service, "ada", "remind me to stretch every day at 9am")

    async def always_different(old_prompt, new_prompt):
        return True

    service.job_manager._is_significant_prompt_change = always_different
    new_job_id, action = await service.job_manager.update_or_replace_job(
        job["job_id"], "ada", new_prompt="send me the weather"
    )

    assert action == "replaced"
    assert await stored_timezone(service, new_job_id) == NEW_YORK


@pytest.mark.parametrize(
    "rule, utc_time",
    [
        # Friday 23:30 in New York is already Saturday in UTC
        ({"type": "cron", "pattern": "* * * * 0,6"}, datetime(2026, 10, 3, 3, 30)),
        # September 30, 22:00 in New York is already October 1 in UTC
        ({"type": "complex_date", "pattern": "nth_day:1"}, datetime(2026, 10, 1, 2, 0)),
    ],
)
async def test_exclusions_are_read_in_the_jobs_timezone(db_manager, channel_store, rule, utc_time):
    service = make_service(db_manager, channel_store)  # formation in UTC
    now = pytz.UTC.localize(utc_time)
    with_timezone = {
        "id": "job_1",
        "exclusion_rules": [rule],
        "job_metadata": {"timezone": NEW_YORK},
    }
    without_timezone = {"id": "job_2", "exclusion_rules": [rule], "job_metadata": {}}

    assert await service._check_exclusion_rules(with_timezone, now) is False
    assert await service._check_exclusion_rules(without_timezone, now) is True
