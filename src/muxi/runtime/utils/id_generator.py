"""
ID generation utilities for the MUXI Framework.

This module provides functions for generating Nano IDs consistently
across the application.
"""

from nanoid import generate

# Observability integration
from ..services import observability


def generate_nanoid(size: int = 21) -> str:
    """
    Generate a Nano ID of the specified size.

    Args:
        size: Length of the ID to generate. Default is 21 characters.

    Returns:
        A new Nano ID string.
    """

    try:
        alphabet = "_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        nano_id = generate(alphabet, size)
        return nano_id

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
            level=observability.EventLevel.ERROR,
            description="Nano ID generation failed with error",
            data={
                "operation": "generate_nanoid",
                "size": size,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )

        raise


def get_default_nanoid() -> str:
    """
    Get a default Nano ID with standard size.
    Used for SQLAlchemy default values.

    Returns:
        A new Nano ID string of standard length.
    """
    try:
        nano_id = generate_nanoid()
        return nano_id

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
            level=observability.EventLevel.ERROR,
            description="Default Nano ID generation failed with error",
            data={
                "operation": "get_default_nanoid",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
