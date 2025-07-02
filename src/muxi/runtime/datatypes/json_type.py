"""
JSON Type Decorator for SQLAlchemy

Provides a database-agnostic JSON column type that works with both
PostgreSQL (JSONB) and SQLite (TEXT with JSON serialization).
"""

import json
from sqlalchemy.types import TEXT, TypeDecorator


class JSONType(TypeDecorator):
    """
    Custom JSON type that works with both PostgreSQL and SQLite.

    - For PostgreSQL: Uses native JSONB type
    - For SQLite: Uses TEXT with JSON serialization/deserialization

    This allows models to use JSON columns without worrying about
    the underlying database implementation.
    """

    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python object to database format."""
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        """Convert database format to Python object."""
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            # Already a Python object (e.g., from PostgreSQL JSONB)
            return value
        return json.loads(value)
