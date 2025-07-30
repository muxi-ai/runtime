"""
Utility functions for the Formation server.
"""

from typing import Optional
from starlette.datastructures import Headers


def get_header_case_insensitive(headers: Headers, header_name: str) -> Optional[str]:
    """
    Get a header value from the request headers in a case-insensitive manner.

    Args:
        headers: The request headers object
        header_name: The header name to look for (case-insensitive)

    Returns:
        The header value if found, None otherwise
    """
    # Starlette Headers class already handles case-insensitive lookups
    return headers.get(header_name)


def has_header_case_insensitive(headers: Headers, header_name: str) -> bool:
    """
    Check if a header exists in the request headers (case-insensitive).

    Args:
        headers: The request headers object
        header_name: The header name to check for (case-insensitive)

    Returns:
        True if the header exists, False otherwise
    """
    return get_header_case_insensitive(headers, header_name) is not None
