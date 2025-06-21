"""
String processing utilities for the Overlord.
"""

from typing import Any


def normalize_external_id(external_user_id: Any) -> str:
    """
    Normalize any external user ID to consistent string format.

    This method converts external user IDs from various formats (string, int, float,
    objects) to a consistent string representation for internal processing. It handles
    common edge cases like None values and provides consistent string conversion
    for complex object types.

    Args:
        external_user_id: User ID in any format (str, int, float, object, None)

    Returns:
        Normalized string representation suitable for hashing and storage:
        - None values become "anonymous"
        - Numbers are converted to strings
        - Objects use their string representation
        - Strings are stripped of whitespace
    """
    # Handle None values as anonymous users
    if external_user_id is None:
        return "anonymous"

    # Handle string IDs by stripping whitespace
    if isinstance(external_user_id, str):
        return external_user_id.strip()

    # Handle numeric IDs by converting to string
    if isinstance(external_user_id, (int, float)):
        return str(external_user_id)

    # Handle any other type (objects, etc.) using string representation
    return str(external_user_id)
