"""The runtime changes the case of one kind of user id only: an email address.

The request entry points lowercase an email-shaped id (``Ada@Example.com``
becomes ``ada@example.com``) before the middleware step, so email addresses
are case-insensitive with or without a middleware. Every other id, such as a
Slack-style ``U024BE7LH``, passes byte-for-byte. Past the entry point the id
is never touched again: the chat orchestrator's memory key (the
``UserIdentifier`` row that maps the external id to the internal user), the
credentials resolver and the scheduler all keep the id they are handed
verbatim, so nothing is silently merged downstream.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from muxi.runtime.formation.background.request_tracker import RequestTracker
from muxi.runtime.formation.credentials.encrypted import EncryptedCredentialResolver
from muxi.runtime.formation.credentials.resolver import Credential
from muxi.runtime.formation.overlord.chat_orchestrator import ChatOrchestrator
from muxi.runtime.formation.overlord.input_validation import InputValidator
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.long_term import User, UserIdentifier
from muxi.runtime.services.observability.manager import ObservabilityManager
from muxi.runtime.services.scheduler.manager import JobManager
from muxi.runtime.services.scheduler.models import ScheduledJob, ScheduledJobAudit
from muxi.runtime.utils.user_resolution import lowercase_email_user_id

FORMATION_ID = "case-test-formation"
USER_ID = "Ada@Example.com"


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


def make_overlord(db_manager) -> Overlord:
    """A real Overlord carrying only the state the greeting fast path reads.

    A bare greeting with no buffer memory takes the orchestrator's early
    heuristic path: the identity is resolved, the request is tracked, and
    the persona fallback answers without any model call.
    """
    overlord = Overlord.__new__(Overlord)
    overlord.is_multi_user = True
    overlord.formation_id = FORMATION_ID
    overlord.db_manager = db_manager
    overlord.long_term_memory = None
    overlord.buffer_memory_manager = None
    overlord.agents = {}
    overlord.streaming = False
    overlord.routing_model = None
    overlord._capability_models = {}
    overlord._background_tasks = set()
    overlord.observability_manager = ObservabilityManager()
    overlord.request_tracker = RequestTracker()
    # State Overlord.chat() reads on the way to the orchestrator: no
    # middleware, no permission resolver, no commands block, and no buffer
    # memory holding a clarification for the session it generates.
    overlord.input_validator = InputValidator()
    overlord.user_channel_store = None
    overlord._configured_services = {}
    overlord._commands_config = None
    overlord.formation_config = {}
    overlord.buffer_memory = None
    overlord.chat_orchestrator = ChatOrchestrator(overlord)
    return overlord


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        ("Ada@Example.com", "ada@example.com"),
        ("ADA+Hero@Mail.Example.COM", "ada+hero@mail.example.com"),
        ("ada@example.com", "ada@example.com"),
        ("U024BE7LH", "U024BE7LH"),
        ("eun_usr_ada", "eun_usr_ada"),
        ("Employee-42", "Employee-42"),
        ("A@B", "A@B"),
        ("@X.com", "@X.com"),
        ("A@@B.com", "A@@B.com"),
        ("A b@C.com", "A b@C.com"),
        (" Ada@Example.com", " Ada@Example.com"),
        ("Ada@Example.com\n", "Ada@Example.com\n"),
        ("Ada@.Example.com", "Ada@.Example.com"),
        ("Ada@Example.", "Ada@Example."),
    ],
)
def test_only_email_shaped_user_ids_are_lowercased(user_id, expected):
    assert lowercase_email_user_id(user_id) == expected


async def test_chat_entry_point_lowercases_email_user_id(db_manager):
    overlord = make_overlord(db_manager)

    response = await overlord.chat("hello", user_id=USER_ID)

    assert response.metadata["early_heuristic"] is True
    [state] = (await overlord.request_tracker.get_all_requests()).values()
    assert state.user_id == "ada@example.com"
    assert await stored_identifiers(db_manager) == ["ada@example.com"]


async def test_chat_entry_point_keeps_non_email_user_id(db_manager):
    overlord = make_overlord(db_manager)

    await overlord.chat("hello", user_id="U024BE7LH")

    assert await stored_identifiers(db_manager) == ["U024BE7LH"]


async def test_chat_pipeline_keeps_user_id_case(db_manager):
    overlord = make_overlord(db_manager)

    response = await ChatOrchestrator(overlord).chat("hello", user_id=USER_ID)

    assert response.metadata["early_heuristic"] is True
    [state] = (await overlord.request_tracker.get_all_requests()).values()
    assert state.user_id == USER_ID
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
        user_id=USER_ID,
        title="Daily digest",
        original_prompt="send me a digest every morning",
        execution_prompt="send a digest",
        cron_expression="0 9 * * *",
        is_recurring=True,
    )

    assert await stored_identifiers(db_manager) == [USER_ID]
    assert [job["id"] for job in await manager.get_user_jobs(USER_ID)] == [job_id]
    assert await manager.get_user_jobs(USER_ID.lower()) == []
