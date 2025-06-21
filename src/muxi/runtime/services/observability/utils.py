"""
Utility functions for the MUXI observability system.

This module consolidates network and string utilities used throughout
the observability system.
"""

import hashlib
import re
from typing import Any
from urllib.parse import urlparse


# ===================================================================
# NETWORK UTILITIES
# ===================================================================


def detect_stream_protocol(destination: str) -> str:
    """
    Detect the protocol type from a destination URL.

    Args:
        destination: The destination URL or connection string

    Returns:
        The detected protocol ('http', 'kafka', 'zmq', or 'unknown')
    """
    if not destination:
        return "unknown"

    destination = destination.lower().strip()

    # HTTP/HTTPS detection
    if destination.startswith(("http://", "https://")):
        return "http"

    # Kafka detection
    if destination.startswith("kafka://") or ":9092" in destination:
        return "kafka"

    # ZeroMQ detection
    if destination.startswith(("tcp://", "tcps://", "ipc://", "inproc://")):
        return "zmq"

    # Try to parse as URL
    try:
        parsed = urlparse(destination)
        if parsed.scheme in ["http", "https"]:
            return "http"
        elif parsed.scheme in ["tcp", "tcps", "ipc", "inproc"]:
            return "zmq"
        elif parsed.scheme == "kafka":
            return "kafka"
    except Exception:
        pass

    return "unknown"


def is_valid_url(url: str) -> bool:
    """
    Check if a string is a valid URL.

    Args:
        url: The URL string to validate

    Returns:
        True if the URL is valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


# ===================================================================
# STRING UTILITIES
# ===================================================================


def normalize_external_id(external_id: Any) -> str:
    """
    Normalize an external ID to a consistent string format.

    Args:
        external_id: The external ID to normalize (can be any type)

    Returns:
        Normalized string representation of the ID
    """
    if external_id is None:
        return "anonymous"

    # Convert to string
    id_str = str(external_id).strip()

    # Handle empty strings
    if not id_str:
        return "anonymous"

    # Normalize whitespace and special characters
    normalized = re.sub(r"\s+", "_", id_str)
    normalized = re.sub(r"[^\w\-_.]", "", normalized)

    # Ensure it's not too long
    if len(normalized) > 100:
        # Create a hash for very long IDs
        hash_obj = hashlib.sha256(normalized.encode())
        normalized = f"hashed_{hash_obj.hexdigest()[:16]}"

    return normalized or "anonymous"


def sanitize_destination_name(destination: str) -> str:
    """
    Sanitize a destination string for use as a filename or identifier.

    Args:
        destination: The destination URL or path to sanitize

    Returns:
        Sanitized string safe for use as identifier
    """
    if not destination:
        return "unknown"

    # Remove protocol prefixes
    sanitized = destination
    for prefix in ["http://", "https://", "kafka://", "tcp://", "tcps://", "ipc://", "inproc://"]:
        if sanitized.startswith(prefix):
            sanitized = sanitized[len(prefix):]
            break

    # Replace special characters with underscores
    sanitized = re.sub(r"[^\w\-_.]", "_", sanitized)

    # Remove multiple consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    return sanitized or "unknown"
