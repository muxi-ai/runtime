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
        """
        Selects the appropriate SQLAlchemy type descriptor for
        JSON storage based on the database dialect.

        For PostgreSQL, returns the native JSON type with `none_as_null=True`.
        For other dialects, returns a TEXT type for JSON serialization.
        """
        if dialect.name == "postgresql":
            # Use native JSONB for PostgreSQL
            return dialect.type_descriptor(JSON(none_as_null=True))
        else:
            # Use TEXT for SQLite and others
            return dialect.type_descriptor(TEXT())

    def process_bind_param(self, value, dialect):
        """
        Serializes a Python object for storage in a database JSON column.

        If the dialect is PostgreSQL, returns the value unchanged for native
        JSON handling. For other dialects, serializes the value to a JSON string.
        Returns None if the input is None.

        Raises:
            ValueError: If the value cannot be serialized to JSON.
        """
        if value is None:
            return None

        # For PostgreSQL, let the native JSON type handle it
        if dialect.name == "postgresql":
            return value

        # For SQLite, serialize to JSON string
        try:
            return json.dumps(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot serialize value to JSON: {value}") from e

    def process_result_value(self, value, dialect):
        """
        Converts a database value to a Python object after retrieval.

        If the value is `None`, returns `None`. For PostgreSQL,
        returns the value as-is since it is already deserialized.
        For other dialects, returns the value directly if it is a Python list
        or dict; otherwise, deserializes the JSON string to a Python object.
        """
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
