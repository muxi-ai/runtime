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
    Return the current UTC datetime as an ISO 8601 string with a 'Z' suffix to indicate UTC.

    Returns:
        str: ISO 8601 formatted UTC datetime string ending with 'Z'.
    """
    return utc_now().isoformat().replace("+00:00", "Z")


def utc_now_naive() -> datetime:
    """
    Return the current UTC datetime as a naive (timezone-unaware) object.

    Intended for use with databases that require TIMESTAMP WITHOUT TIME ZONE
    columns, such as PostgreSQL when accessed via asyncpg.

    Returns:
        datetime: Current UTC time without timezone information.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
