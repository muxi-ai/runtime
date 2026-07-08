"""
Formation isolation for scheduler batch queries.

Multiple formations can share a single database, so every query that feeds the
due-job worker must be scoped to the manager's formation_id.  Without that
scope, a formation executes jobs created by other formations (observed in e2e
where formations sharing one Postgres ran each other's stale recurring jobs).
"""

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.long_term import User, UserIdentifier
from muxi.runtime.services.scheduler.manager import JobManager
from muxi.runtime.services.scheduler.models import ScheduledJob, ScheduledJobAudit

SCHEDULER_TABLES = [
    User.__table__,
    UserIdentifier.__table__,
    ScheduledJob.__table__,
    ScheduledJobAudit.__table__,
]


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/scheduler.db")
    manager.create_tables(Base.metadata, tables=SCHEDULER_TABLES)
    yield manager
    manager.engine.dispose()


async def _create_recurring_job(job_manager: JobManager, user_id: str, title: str) -> str:
    return await job_manager.create_job(
        user_id=user_id,
        title=title,
        original_prompt="tell me a dad joke every minute",
        execution_prompt="tell me a dad joke",
        cron_expression="* * * * *",
        is_recurring=True,
    )


async def test_get_active_jobs_batch_excludes_other_formations(db_manager):
    manager_a = JobManager(db_manager, formation_id="formation-a")
    manager_b = JobManager(db_manager, formation_id="formation-b")

    job_a = await _create_recurring_job(manager_a, "user-a", "Formation A job")
    job_b = await _create_recurring_job(manager_b, "user-b", "Formation B job")

    batch_a = await manager_a.get_active_jobs_batch(offset=0, limit=100)
    batch_b = await manager_b.get_active_jobs_batch(offset=0, limit=100)

    assert [job["id"] for job in batch_a] == [job_a]
    assert [job["id"] for job in batch_b] == [job_b]


async def test_get_active_jobs_count_excludes_other_formations(db_manager):
    manager_a = JobManager(db_manager, formation_id="formation-a")
    manager_b = JobManager(db_manager, formation_id="formation-b")

    await _create_recurring_job(manager_a, "user-a", "Formation A job one")
    await _create_recurring_job(manager_a, "user-a", "Formation A job two")
    await _create_recurring_job(manager_b, "user-b", "Formation B job")

    assert await manager_a.get_active_jobs_count() == 2
    assert await manager_b.get_active_jobs_count() == 1
