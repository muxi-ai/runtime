"""Unit tests for the GBAC schema + the removed server.auth surface.

Updated for the request-middleware PRD:

1. Schema -- the ``groups`` SQLAlchemy model creates cleanly on SQLite and
   enforces its per-formation composite unique. The former ``user_groups``
   membership table is GONE: MUXI stores no memberships (groups arrive per
   request from the formation middleware), and pre-existing deployed
   tables are left orphaned.
2. Config -- ``server.auth`` was removed entirely. Formations still
   carrying the key fail loudly at validation and at extraction time with
   an actionable migration message (rbac.fallback + middleware).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.formation.formation import Formation
from muxi.runtime.services.db import Base
from muxi.runtime.services.memory.long_term import Group, User, UserIdentifier

FORMATION_ID = "gbac-test-formation"

GBAC_TABLES = [
    User.__table__,
    UserIdentifier.__table__,
    Group.__table__,
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
    """Schema: the groups model on SQLite (no membership table)."""

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

    def test_user_groups_model_is_gone(self):
        """MUXI stores no memberships: the UserGroup model was removed."""
        import muxi.runtime.services.memory.long_term as long_term

        assert not hasattr(long_term, "UserGroup")


class TestServerAuthRemoved:
    """server.auth was removed; carrying it is a loud, actionable failure."""

    @staticmethod
    def _auth_errors(validator: FormationValidator) -> list:
        return [e for e in validator.result.errors if "auth" in e.lower()]

    def test_auth_absent_is_valid(self):
        validator = FormationValidator()
        validator._validate_server_config({"port": 8271})
        assert not self._auth_errors(validator)

    @pytest.mark.parametrize("value", ["open", "required", "banana"])
    def test_any_auth_value_rejected_by_validator(self, value):
        validator = FormationValidator()
        validator._validate_server_config({"auth": value})
        errors = self._auth_errors(validator)
        assert len(errors) == 1
        assert "removed" in errors[0]
        assert "rbac" in errors[0]

    @staticmethod
    def _formation_stub(server_config: dict) -> SimpleNamespace:
        return SimpleNamespace(config={"server": server_config}, _api_keys={})

    def test_setup_auth_without_auth_key(self):
        stub = self._formation_stub({})
        Formation._setup_auth(stub)
        assert "auth" not in stub._server_config

    @pytest.mark.parametrize("value", ["open", "required"])
    def test_setup_auth_rejects_removed_key(self, value):
        stub = self._formation_stub({"auth": value})
        with pytest.raises(ConfigurationValidationError) as exc_info:
            Formation._setup_auth(stub)
        assert "removed" in str(exc_info.value)

    def test_user_auth_gate_is_gone(self):
        import muxi.runtime.formation.server.auth as server_auth

        assert not hasattr(server_auth, "UserAuthGate")
