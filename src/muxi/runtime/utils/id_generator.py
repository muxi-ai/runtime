"""
ID generation utilities for the MUXI Framework.

This module provides functions for generating Nano IDs consistently
across the application.
"""

from nanoid import generate


def generate_nanoid(size: int = 21) -> str:
    """
    Generate a Nano ID of the specified size.

    Args:
        size: Length of the ID to generate. Default is 21 characters.

    Returns:
        A new Nano ID string.

    Raises:
        Exception: If nanoid generation fails.
    """
    alphabet = "_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return generate(alphabet, size)


def get_default_nanoid() -> str:
    """
    Get a default Nano ID with standard size.
    Used for SQLAlchemy default values.

    Returns:
        A new Nano ID string of standard length.

    Raises:
        Exception: If nanoid generation fails.
    """
    return generate_nanoid()


def generate_request_id() -> str:
    """
    Generate a request ID for API requests.

    Returns:
        A request ID in the format 'req_<nanoid>'
    """
    return f"req_{generate_nanoid()}"
