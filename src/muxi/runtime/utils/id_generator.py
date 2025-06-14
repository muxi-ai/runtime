"""
ID generation utilities for the MUXI Framework.

This module provides functions for generating Nano IDs consistently
across the application.
"""

from nanoid import generate

# Observability integration
from .. import observability


def generate_nanoid(size: int = 21) -> str:
    """
    Generate a Nano ID of the specified size.

    Args:
        size: Length of the ID to generate. Default is 21 characters.

    Returns:
        A new Nano ID string.
    """
    observability.emit_event(
        event_type=observability.SystemEventType.ID_GENERATION_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting Nano ID generation",
        data={
            "operation": "generate_nanoid",
            "size": size,
            "alphabet_length": 64,  # Length of our custom alphabet
        },
    )

    try:
        alphabet = "_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        nano_id = generate(alphabet, size)

        observability.emit_event(
            event_type=observability.SystemEventType.ID_GENERATION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="Nano ID generation completed successfully",
            data={
                "operation": "generate_nanoid",
                "size": size,
                "generated_id_length": len(nano_id),
                "alphabet_length": len(alphabet),
            },
        )

        return nano_id

    except Exception as e:
        observability.emit_event(
            event_type=observability.ConversationEventType.ERROR_RETRY_ATTEMPTED,
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
    observability.emit_event(
        event_type=observability.SystemEventType.ID_GENERATION_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting default Nano ID generation",
        data={
            "operation": "get_default_nanoid",
            "size": 21,  # Default size
            "use_case": "sqlalchemy_default",
        },
    )

    try:
        nano_id = generate_nanoid()

        observability.emit_event(
            event_type=observability.SystemEventType.ID_GENERATION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="Default Nano ID generation completed successfully",
            data={
                "operation": "get_default_nanoid",
                "size": 21,
                "generated_id_length": len(nano_id),
                "use_case": "sqlalchemy_default",
            },
        )

        return nano_id

    except Exception as e:
        observability.emit_event(
            event_type=observability.ConversationEventType.ERROR_RETRY_ATTEMPTED,
            level=observability.EventLevel.ERROR,
            description="Default Nano ID generation failed with error",
            data={
                "operation": "get_default_nanoid",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
