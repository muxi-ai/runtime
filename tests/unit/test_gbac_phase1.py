"""Unit tests for GBAC Phase 1: groups schema, server.auth config, and the user auth gate.

Covers the three Phase 1 surfaces of the group-based access control PRD:

1. Schema -- the ``groups`` and ``user_groups`` SQLAlchemy models create
   cleanly on SQLite and enforce their per-formation composite uniques.
2. Config -- ``server.auth`` accepts ``open``/``required`` (default ``open``)
   and rejects anything else at both validation and extraction time.
3. Gate -- ``UserAuthGate`` is a no-op when auth is open, rejects unknown
   users with 401 when auth is required, and admits known users seeded in
   the ``users``/``user_identifiers`` tables.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.formation.formation import Formation
from muxi.runtime.formation.server.auth import UserAuthGate
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.long_term import Group, User, UserGroup, UserIdentifier
from muxi.runtime.utils.user_resolution import resolve_user_identifier

FORMATION_ID = "gbac-test-formation"

GBAC_TABLES = [
    User.__table__,
    UserIdentifier.__table__,
    Group.__table__,
    UserGroup.__table__,
]


@pytest.fixture
def sqlite_session():
    """In-memory SQLite session with the users/identifiers/groups tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=GBAC_TABLES)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


class TestGroupModels:
    """Schema: groups and user_groups models on SQLite."""

    def test_group_creation(self, sqlite_session):
        """A group row persists with its PRD columns plus formation_id."""
        sqlite_session.add(
            Group(
                group_id="analyst",
                name="Business Analyst",
                description="Analysis and reporting",
                formation_id=FORMATION_ID,
            )
        )
        sqlite_session.commit()

        group = sqlite_session.execute(select(Group)).scalar_one()
        assert group.group_id == "analyst"
        assert group.name == "Business Analyst"
        assert group.description == "Analysis and reporting"
        assert group.formation_id == FORMATION_ID
        assert group.created_at is not None

    def test_group_id_unique_per_formation(self, sqlite_session):
        """Duplicate group_id in the same formation is rejected."""
        sqlite_session.add(Group(group_id="analyst", formation_id=FORMATION_ID))
        sqlite_session.commit()

        sqlite_session.add(Group(group_id="analyst", formation_id=FORMATION_ID))
        with pytest.raises(IntegrityError):
            sqlite_session.commit()

    def test_group_id_reusable_across_formations(self, sqlite_session):
        """The same group_id may exist in different formations."""
        sqlite_session.add(Group(group_id="analyst", formation_id=FORMATION_ID))
        sqlite_session.add(Group(group_id="analyst", formation_id="other-formation"))
        sqlite_session.commit()

        count = len(sqlite_session.execute(select(Group)).scalars().all())
        assert count == 2

    def test_user_group_membership(self, sqlite_session):
        """Membership rows store the external identifier string as user_id."""
        sqlite_session.add(
            UserGroup(user_id="alice@example.com", group_id="analyst", formation_id=FORMATION_ID)
        )
        sqlite_session.commit()

        membership = sqlite_session.execute(select(UserGroup)).scalar_one()
        assert membership.user_id == "alice@example.com"
        assert membership.group_id == "analyst"
        assert membership.formation_id == FORMATION_ID
        assert membership.created_at is not None

    def test_user_group_unique_per_formation(self, sqlite_session):
        """Duplicate membership in the same formation is rejected."""
        sqlite_session.add(
            UserGroup(user_id="alice@example.com", group_id="analyst", formation_id=FORMATION_ID)
        )
        sqlite_session.commit()

        sqlite_session.add(
            UserGroup(user_id="alice@example.com", group_id="analyst", formation_id=FORMATION_ID)
        )
        with pytest.raises(IntegrityError):
            sqlite_session.commit()


class TestServerAuthValidation:
    """Config: server.auth validation in FormationValidator."""

    @staticmethod
    def _auth_errors(validator: FormationValidator) -> list:
        return [e for e in validator.result.errors if "auth" in e.lower()]

    def test_auth_absent_is_valid(self):
        validator = FormationValidator()
        validator._validate_server_config({"port": 8271})
        assert not self._auth_errors(validator)

    def test_auth_open_accepted(self):
        validator = FormationValidator()
        validator._validate_server_config({"auth": "open"})
        assert not self._auth_errors(validator)

    def test_auth_required_accepted(self):
        validator = FormationValidator()
        validator._validate_server_config({"auth": "required"})
        assert not self._auth_errors(validator)

    def test_auth_garbage_rejected(self):
        validator = FormationValidator()
        validator._validate_server_config({"auth": "banana"})
        errors = self._auth_errors(validator)
        assert len(errors) == 1
        assert "'open' or 'required'" in errors[0]


class TestServerAuthExtraction:
    """Config: server.auth extraction in Formation._setup_auth."""

    @staticmethod
    def _formation_stub(server_config: dict) -> SimpleNamespace:
        return SimpleNamespace(config={"server": server_config}, _api_keys={})

    def test_auth_defaults_to_open(self):
        stub = self._formation_stub({})
        Formation._setup_auth(stub)
        assert stub._server_config["auth"] == "open"

    def test_auth_required_stored(self):
        stub = self._formation_stub({"auth": "required"})
        Formation._setup_auth(stub)
        assert stub._server_config["auth"] == "required"

    def test_auth_invalid_raises(self):
        stub = self._formation_stub({"auth": "banana"})
        with pytest.raises(ConfigurationValidationError):
            Formation._setup_auth(stub)


def _make_request(
    formation,
    path: str = "/v1/chat",
    headers: dict | None = None,
    body: bytes = b"",
) -> Request:
    """Build a minimal starlette Request wired to a stub formation."""
    app = SimpleNamespace(state=SimpleNamespace(formation=formation))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "app": app,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.fixture
async def gate_db(tmp_path):
    """File-backed SQLite DatabaseManager with one known user seeded."""
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/gate.db")
    Base.metadata.create_all(db_manager.engine, tables=GBAC_TABLES)
    await resolve_user_identifier(
        identifier="alice@example.com",
        formation_id=FORMATION_ID,
        db_manager=db_manager,
        kv_cache=None,
        create_if_missing=True,
    )
    yield db_manager
    db_manager.engine.dispose()


def _formation_stub(auth: str, db_manager=None) -> SimpleNamespace:
    return SimpleNamespace(
        _server_config={"auth": auth, "host": "127.0.0.1", "port": 8271},
        _db_manager=db_manager,
        formation_id=FORMATION_ID,
    )


class TestUserAuthGate:
    """Gate: UserAuthGate dependency behavior."""

    async def test_auth_open_lets_unknown_user_through(self):
        """With auth open the gate is a no-op (no database access needed)."""
        gate = UserAuthGate()
        request = _make_request(
            _formation_stub("open", db_manager=None),
            headers={"X-Muxi-User-Id": "stranger@example.com"},
        )
        assert await gate(request) is None

    async def test_auth_required_rejects_unknown_user(self, gate_db):
        gate = UserAuthGate()
        request = _make_request(
            _formation_stub("required", gate_db),
            headers={"X-Muxi-User-Id": "stranger@example.com"},
        )
        with pytest.raises(HTTPException) as exc_info:
            await gate(request)
        assert exc_info.value.status_code == 401
        assert "stranger@example.com" in exc_info.value.detail

    async def test_auth_required_allows_known_user(self, gate_db):
        gate = UserAuthGate()
        request = _make_request(
            _formation_stub("required", gate_db),
            headers={"X-Muxi-User-Id": "alice@example.com"},
        )
        assert await gate(request) is None

    async def test_auth_required_rejects_anonymous_default_user(self, gate_db):
        """No identity resolves to the default user "0", unknown unless seeded."""
        gate = UserAuthGate()
        request = _make_request(_formation_stub("required", gate_db))
        with pytest.raises(HTTPException) as exc_info:
            await gate(request)
        assert exc_info.value.status_code == 401

    async def test_auth_required_chat_body_fallback_known_user(self, gate_db):
        """The deprecated body user_id is honored on chat endpoints."""
        gate = UserAuthGate()
        request = _make_request(
            _formation_stub("required", gate_db),
            path="/v1/chat",
            headers={"Content-Type": "application/json"},
            body=b'{"message": "hi", "user_id": "alice@example.com"}',
        )
        assert await gate(request) is None

    async def test_auth_required_body_ignored_on_trigger_routes(self, gate_db):
        """Trigger routes read identity from the header only, so the gate does too."""
        gate = UserAuthGate()
        request = _make_request(
            _formation_stub("required", gate_db),
            path="/v1/triggers/test-trigger",
            headers={"Content-Type": "application/json"},
            body=b'{"data": {}, "user_id": "alice@example.com"}',
        )
        with pytest.raises(HTTPException) as exc_info:
            await gate(request)
        assert exc_info.value.status_code == 401

    async def test_auth_required_without_database_fails_closed(self):
        gate = UserAuthGate()
        request = _make_request(
            _formation_stub("required", db_manager=None),
            headers={"X-Muxi-User-Id": "alice@example.com"},
        )
        with pytest.raises(HTTPException) as exc_info:
            await gate(request)
        assert exc_info.value.status_code == 500
