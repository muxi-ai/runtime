"""The runtime never changes the case of a user id.

Without a request middleware, a mixed-case id such as ``Ada@Example.com``
(or a Slack-style ``U024BE7LH``) must reach every downstream site verbatim:
the chat pipeline's memory key (the ``UserIdentifier`` row that maps the
external id to the internal user), the credentials resolver, and the
scheduler. A differently-cased id is a different user, so nothing is
silently merged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from muxi.runtime.formation.credentials.encrypted import EncryptedCredentialResolver
from muxi.runtime.formation.credentials.resolver import Credential
from muxi.runtime.formation.overlord.chat_orchestrator import ChatOrchestrator
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.long_term import User, UserIdentifier
from muxi.runtime.services.scheduler.manager import JobManager
from muxi.runtime.services.scheduler.models import ScheduledJob, ScheduledJobAudit

FORMATION_ID = "case-test-formation"
USER_ID = "Ada@Example.com"
# The scheduler's input validator only admits [A-Za-z0-9_.-] ids, so its
# case check uses a Slack-style id instead of an email address.
SCHEDULER_USER_ID = "U024BE7LH"


@pytest.fixture
def db_manager(tmp_path):
    """File-backed SQLite DatabaseManager (sync + async engines share it)."""
    manager = DatabaseManager(f"sqlite:///{tmp_path}/case.db")
    manager.create_tables(
        Base.metadata,
        tables=[
            User.__table__,
            UserIdentifier.__table__,
            Credential.__table__,
            ScheduledJob.__table__,
            ScheduledJobAudit.__table__,
        ],
    )
    yield manager
    manager.engine.dispose()


async def stored_identifiers(db_manager):
    async with db_manager.get_async_session() as session:
        rows = await session.execute(
            select(UserIdentifier.identifier).where(UserIdentifier.formation_id == FORMATION_ID)
        )
        return sorted(rows.scalars().all())


class _PipelineStopped(Exception):
    """Raised by the request tracker seam once the memory key is resolved."""


async def test_chat_pipeline_memory_key_keeps_user_id_case(db_manager):
    tracked = []

    def track_request(**kwargs):
        tracked.append(kwargs)
        raise _PipelineStopped

    overlord = SimpleNamespace(
        is_multi_user=True,
        formation_id=FORMATION_ID,
        db_manager=db_manager,
        long_term_memory=None,
        observability_manager=SimpleNamespace(track_request=track_request),
    )

    with pytest.raises(_PipelineStopped):
        await ChatOrchestrator(overlord).chat("hello", user_id=USER_ID)

    assert tracked[0]["user_id"] == USER_ID
    assert await stored_identifiers(db_manager) == [USER_ID]


async def test_credentials_resolver_keeps_user_id_case(db_manager):
    resolver = EncryptedCredentialResolver(
        async_session_maker=db_manager.AsyncSession,
        formation_id=FORMATION_ID,
        db_manager=db_manager,
    )

    await resolver.store_credential(USER_ID, "github", {"token": "t-1"}, credential_name="work")

    assert await stored_identifiers(db_manager) == [USER_ID]
    assert await resolver.resolve(USER_ID, "github") is not None
    assert await resolver.resolve(USER_ID.lower(), "github") is None


async def test_scheduler_keeps_user_id_case(db_manager):
    manager = JobManager(db_manager, formation_id=FORMATION_ID)

    job_id = await manager.create_job(
        user_id=SCHEDULER_USER_ID,
        title="Daily digest",
        original_prompt="send me a digest every morning",
        execution_prompt="send a digest",
        cron_expression="0 9 * * *",
        is_recurring=True,
    )

    assert await stored_identifiers(db_manager) == [SCHEDULER_USER_ID]
    assert [job["id"] for job in await manager.get_user_jobs(SCHEDULER_USER_ID)] == [job_id]
    assert await manager.get_user_jobs(SCHEDULER_USER_ID.lower()) == []
