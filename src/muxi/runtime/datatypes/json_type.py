"""
JSON Type Decorator for SQLAlchemy

Provides a database-agnostic JSON column type that works with both
PostgreSQL (JSONB) and SQLite (TEXT with JSON serialization).
"""

import json
from sqlalchemy import JSON
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

    def load_dialect_impl(self, dialect):
        """Load the appropriate implementation based on the dialect."""
        if dialect.name == "postgresql":
            # Use native JSONB for PostgreSQL
            return dialect.type_descriptor(JSON(none_as_null=True))
        else:
            # Use TEXT for SQLite and others
            return dialect.type_descriptor(TEXT())

    def process_bind_param(self, value, dialect):
        """Convert Python object to database format."""
        if value is None:
            return None
        
        # For PostgreSQL, let the native JSON type handle it
        if dialect.name == "postgresql":
            return value
        
        # For SQLite, serialize to JSON string
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        """Convert database format to Python object."""
        if value is None:
            return None
        
        # For PostgreSQL, the value is already deserialized
        if dialect.name == "postgresql":
            return value
            
        # For SQLite, deserialize from JSON string
        if isinstance(value, (list, dict)):
            # Already a Python object
            return value
        return json.loads(value)
