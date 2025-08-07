"""
Utility functions for the Formation server.
"""

import re
from typing import Optional, List
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


def mask_secret_value(
    secret_value: Optional[str],
    common_prefixes: Optional[List[str]] = None
) -> str:
    """
    Mask a secret value for safe display, preserving identifiable parts.

    This function intelligently masks secrets while keeping useful identifying information:
    - Preserves protocols (https://, mongodb://, etc.)
    - Shows common API key prefixes (sk-, pk-, ghp_, etc.)
    - Displays first and last few characters for identification
    - Handles various secret lengths appropriately

    Args:
        secret_value: The secret value to mask. If None or empty, returns generic mask.
        common_prefixes: List of common API key prefixes to preserve.
                        Defaults to ["sk-", "pk-", "ghp_", "ghs_", "pat_", "key-", "tok-", "lin_"]

    Returns:
        Masked secret value safe for display

    Examples:
        >>> mask_secret_value("sk-1234567890abcdef")
        'sk-12••••••cdef'
        >>> mask_secret_value("https://user:pass@example.com")
        'https://us•••••••.com'
        >>> mask_secret_value("short")
        '••••••••'
    """
    if not secret_value:
        return "••••••••"

    # Default common prefixes if not provided
    if common_prefixes is None:
        common_prefixes = ["sk-", "pk-", "ghp_", "ghs_", "pat_", "key-", "tok-", "lin_"]

    # Check for protocols (preserve these)
    protocol_match = re.match(r'^([a-zA-Z][a-zA-Z0-9+.-]*://)', secret_value)
    protocol = protocol_match.group(1) if protocol_match else ""
    value_after_protocol = secret_value[len(protocol):]

    # Check for common API key prefixes
    prefix_len = 0
    for prefix in common_prefixes:
        if value_after_protocol.startswith(prefix):
            prefix_len = len(prefix)
            break

    if protocol:
        # For URLs with protocols, be more careful about what we show
        # Show protocol + first 2 chars + dots + last few chars
        if len(value_after_protocol) > 8:
            masked_value = f"{protocol}{value_after_protocol[:2]}•••••••{value_after_protocol[-4:]}"
        else:
            masked_value = f"{protocol}••••••••"
    elif len(value_after_protocol) > 12:
        if prefix_len > 0:
            # Show prefix + 2 chars and last 4 chars
            masked_value = f"{value_after_protocol[:prefix_len+2]}••••••{value_after_protocol[-4:]}"
        else:
            # Show first 4 and last 4 characters
            masked_value = f"{value_after_protocol[:4]}••••••••{value_after_protocol[-4:]}"
    elif len(value_after_protocol) > 6:
        # For medium secrets, show first 3 and last 3
        masked_value = f"{value_after_protocol[:3]}••••{value_after_protocol[-3:]}"
    else:
        # For very short secrets, just mask them entirely
        masked_value = "••••••••"

    return masked_value
