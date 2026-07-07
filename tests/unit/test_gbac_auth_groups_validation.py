"""Unit tests for the GBAC groups/auth coupling rule (2026-07-07 ruling).

A ``groups/`` directory containing group files requires
``server.auth: "required"``. The former "open formation with optional
groups" configuration gave unknown users full access while registered
users got filtered access (inverted trust), so the combination is now
inexpressible: formation load fails with a clear, actionable error.

Edge cases pinned here:
- open auth + group files      -> ConfigurationValidationError at load
- absent auth (default: open)  -> same error
- required auth + group files  -> loads, resolver active
- open auth + EMPTY groups/    -> inert (warning only, no error)
- open auth + no groups/ dir   -> unchanged, fine
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation.formation import Formation

FORMATION_ID = "gbac-auth-groups-test"


def formation_stub(tmp_path, auth: str | None) -> SimpleNamespace:
    """Formation stub mirroring the state _setup_groups sees.

    ``_setup_auth`` runs before ``_setup_groups`` in _prepare_services and
    stores the effective auth mode in ``_server_config``; ``auth=None``
    models the default (key absent -> open).
    """
    server_config = {"auth": auth} if auth is not None else {}
    return SimpleNamespace(
        _formation_path=str(tmp_path),
        _permission_resolver=None,
        _group_permissions={},
        formation_id=FORMATION_ID,
        config={"runtime": {}},
        _server_config=server_config,
    )


def write_group_file(tmp_path) -> None:
    (tmp_path / "groups").mkdir()
    (tmp_path / "groups" / "analyst.yaml").write_text("agents: [researcher]\n")


class TestGroupsRequireAuthRequired:
    def test_open_auth_with_group_files_fails_load(self, tmp_path):
        write_group_file(tmp_path)
        stub = formation_stub(tmp_path, auth="open")
        with pytest.raises(ConfigurationValidationError) as exc_info:
            Formation._setup_groups(stub)
        message = str(exc_info.value)
        assert "server.auth" in message
        assert "required" in message
        assert "groups" in message
        assert stub._permission_resolver is None

    def test_default_auth_absent_with_group_files_fails_load(self, tmp_path):
        """auth key absent means open -- the rule still applies."""
        write_group_file(tmp_path)
        stub = formation_stub(tmp_path, auth=None)
        with pytest.raises(ConfigurationValidationError, match="server.auth"):
            Formation._setup_groups(stub)

    def test_error_names_the_groups_directory(self, tmp_path):
        write_group_file(tmp_path)
        stub = formation_stub(tmp_path, auth="open")
        with pytest.raises(ConfigurationValidationError) as exc_info:
            Formation._setup_groups(stub)
        assert str(tmp_path / "groups") in str(exc_info.value)

    def test_error_suggests_the_fix(self, tmp_path):
        write_group_file(tmp_path)
        stub = formation_stub(tmp_path, auth="open")
        with pytest.raises(ConfigurationValidationError) as exc_info:
            Formation._setup_groups(stub)
        details = exc_info.value.details
        assert details["current_value"] == "open"
        assert "server.auth: required" in details["suggestion"]
        assert details["example"] == {"server": {"auth": "required"}}

    def test_required_auth_with_group_files_loads(self, tmp_path):
        write_group_file(tmp_path)
        stub = formation_stub(tmp_path, auth="required")
        Formation._setup_groups(stub)
        assert stub._permission_resolver is not None
        assert stub._permission_resolver.group_ids == ("analyst",)


class TestEdgeCasesStayInert:
    def test_open_auth_with_empty_groups_dir_is_inert(self, tmp_path):
        """Phase 2 behavior preserved: empty groups/ warns, never errors."""
        (tmp_path / "groups").mkdir()
        stub = formation_stub(tmp_path, auth="open")
        Formation._setup_groups(stub)  # must not raise
        assert stub._permission_resolver is None
        assert stub._group_permissions == {}

    def test_open_auth_without_groups_dir_is_fine(self, tmp_path):
        stub = formation_stub(tmp_path, auth="open")
        Formation._setup_groups(stub)  # must not raise
        assert stub._permission_resolver is None

    def test_required_auth_with_empty_groups_dir_is_inert(self, tmp_path):
        (tmp_path / "groups").mkdir()
        stub = formation_stub(tmp_path, auth="required")
        Formation._setup_groups(stub)
        assert stub._permission_resolver is None
