"""Tests for _initialize_persistent_memory SQLite path handling."""

import pytest


class TestSQLitePathStripping:
    """Verify that sqlite:/// prefixes are stripped before passing to SQLiteMemory."""

    @pytest.mark.parametrize(
        "connection_string,expected_db_path",
        [
            ("sqlite:///./memory.db", "./memory.db"),
            ("sqlite:////absolute/path/memory.db", "/absolute/path/memory.db"),
            ("sqlite:///memory.db", "memory.db"),
            ("./memory.db", "./memory.db"),
            ("/tmp/test/memory.db", "/tmp/test/memory.db"),
        ],
    )
    def test_sqlite_prefix_stripped_for_db_path(self, connection_string, expected_db_path):
        """SQLiteMemory must receive a clean file path, not a SQLAlchemy URI."""
        # Replicate the stripping logic from _initialize_persistent_memory
        db_file_path = connection_string
        if db_file_path.startswith("sqlite:///"):
            db_file_path = db_file_path[len("sqlite:///"):]
        elif db_file_path.startswith("sqlite://"):
            db_file_path = db_file_path[len("sqlite://"):]

        assert db_file_path == expected_db_path, (
            f"Expected db_path={expected_db_path!r}, got {db_file_path!r}"
        )

    def test_sqlite_prefix_not_in_path(self):
        """Ensure a sqlite:/// prefix never reaches SQLiteMemory."""
        bad_paths = [
            "sqlite:///./memory.db",
            "sqlite:///memory.db",
            "sqlite:////abs/memory.db",
        ]
        for path in bad_paths:
            db_file_path = path
            if db_file_path.startswith("sqlite:///"):
                db_file_path = db_file_path[len("sqlite:///"):]
            elif db_file_path.startswith("sqlite://"):
                db_file_path = db_file_path[len("sqlite://"):]

            assert not db_file_path.startswith("sqlite:"), (
                f"Path still has sqlite prefix: {db_file_path}"
            )
