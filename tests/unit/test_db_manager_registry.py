"""Tests for the connection-string-keyed database manager registry.

The database manager used to be a process-level singleton: the first
get_database_manager() call pinned the connection string for the whole
process, so a second formation loaded in the same process silently
shared the first formation's SQLite path. The registry keys managers by
resolved connection string, so formations get isolated databases while
callers sharing a connection string still share one engine and pool.
"""

import pytest
from sqlalchemy import text

from muxi.runtime.services import db as db_module
from muxi.runtime.services.db import (
    DatabaseManager,
    get_database_manager,
    set_database_manager,
)


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    """Isolate each test's registry and DB-related environment."""
    monkeypatch.setattr(db_module, "_db_managers", {})
    monkeypatch.delenv("POSTGRES_DATABASE_URL", raising=False)
    monkeypatch.delenv("SQLITE_DATABASE_PATH", raising=False)


class TestFormationScopedManagers:
    def test_two_formations_get_isolated_databases(self, tmp_path):
        """Two formations loaded in one process must not share a database."""
        first = get_database_manager(f"sqlite:///{tmp_path}/formation_a.db")
        second = get_database_manager(f"sqlite:///{tmp_path}/formation_b.db")

        assert first is not second
        assert first.connection_string != second.connection_string

        with first.engine.connect() as conn:
            conn.execute(text("CREATE TABLE marker (id INTEGER PRIMARY KEY)"))
            conn.execute(text("INSERT INTO marker (id) VALUES (1)"))
            conn.commit()

        with second.engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='marker'")
            ).fetchall()
        assert tables == []

    def test_same_connection_string_shares_manager(self, tmp_path):
        """Repeated calls for one connection string share the engine/pool."""
        connection_string = f"sqlite:///{tmp_path}/formation.db"
        assert get_database_manager(connection_string) is get_database_manager(connection_string)

    def test_bare_db_path_normalized_to_sqlite_url(self, tmp_path):
        """A bare .db path and its sqlite:/// spelling resolve to one manager."""
        path = f"{tmp_path}/formation.db"
        prefixed = get_database_manager(f"sqlite:///{path}")
        bare = get_database_manager(path)
        assert bare is prefixed

    def test_default_resolution_is_stable(self, tmp_path, monkeypatch):
        """No-arg calls (env/default resolution) keep returning one manager."""
        monkeypatch.setenv("SQLITE_DATABASE_PATH", f"{tmp_path}/default.db")
        assert get_database_manager() is get_database_manager()

    def test_default_and_explicit_same_path_share_manager(self, tmp_path, monkeypatch):
        """Env-resolved and explicit connection strings share one manager."""
        monkeypatch.setenv("SQLITE_DATABASE_PATH", f"{tmp_path}/default.db")
        explicit = get_database_manager(f"sqlite:///{tmp_path}/default.db")
        assert get_database_manager() is explicit

    def test_timeout_ignored_for_existing_manager(self, tmp_path):
        """First call's timeout is authoritative for a connection string."""
        connection_string = f"sqlite:///{tmp_path}/formation.db"
        first = get_database_manager(connection_string, statement_timeout_seconds=30)
        second = get_database_manager(connection_string, statement_timeout_seconds=60)
        assert second is first
        assert second.statement_timeout_seconds == 30

    def test_set_database_manager_registers_by_connection_string(self, tmp_path):
        connection_string = f"sqlite:///{tmp_path}/formation.db"
        manager = DatabaseManager(connection_string)
        set_database_manager(manager)
        assert get_database_manager(connection_string) is manager
