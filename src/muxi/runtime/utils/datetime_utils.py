"""
Datetime utility functions for MUXI framework.

Provides timezone-aware datetime functions to replace deprecated datetime.utcnow().
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """
    Get current UTC time with timezone awareness.

    This replaces the deprecated datetime.utcnow() with a timezone-aware equivalent.

    Returns:
        Current datetime in UTC with timezone information
    """
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """
    Get current UTC time as ISO format string.

    Returns:
        Current datetime in UTC as ISO format string with 'Z' suffix
    """
    return utc_now().isoformat().replace("+00:00", "Z")


def utc_now_naive() -> datetime:
    """
    Get current UTC time without timezone information.

    This is needed for databases that use TIMESTAMP WITHOUT TIME ZONE columns,
    particularly when using asyncpg with PostgreSQL.

    Returns:
        Current datetime in UTC without timezone information
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
