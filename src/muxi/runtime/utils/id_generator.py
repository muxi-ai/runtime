"""
ID generation utilities for the MUXI Framework.

This module provides functions for generating Nano IDs consistently
across the application.
"""

from nanoid import generate

# Observability integration
try:
    from ..observability import ObservabilityManager, ConversationEventType, SystemEventType, EventLevel
except ImportError:
    # Graceful fallback if observability is not available
    ObservabilityManager = None
    ConversationEventType = None
    EventLevel = None


def generate_nanoid(size: int = 21) -> str:
    """
    Generate a Nano ID of the specified size.

    Args:
        size: Length of the ID to generate. Default is 21 characters.

    Returns:
        A new Nano ID string.
    """
    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=SystemEventType.ID_GENERATION_STARTED,
                level=EventLevel.DEBUG,
                message="Starting Nano ID generation",
                data={
                    "operation": "generate_nanoid",
                    "size": size,
                    "alphabet_length": 64  # Length of our custom alphabet
                }
            )
        except Exception:
            pass

    try:
        alphabet = "_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        nano_id = generate(alphabet, size)

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=SystemEventType.ID_GENERATION_COMPLETED,
                    level=EventLevel.DEBUG,
                    message="Nano ID generation completed successfully",
                    data={
                        "operation": "generate_nanoid",
                        "size": size,
                        "generated_id_length": len(nano_id),
                        "alphabet_length": len(alphabet)
                    }
                )
            except Exception:
                pass

        return nano_id

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Nano ID generation failed with error",
                    data={
                        "operation": "generate_nanoid",
                        "size": size,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
        raise


def get_default_nanoid() -> str:
    """
    Get a default Nano ID with standard size.
    Used for SQLAlchemy default values.

    Returns:
        A new Nano ID string of standard length.
    """
    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=SystemEventType.ID_GENERATION_STARTED,
                level=EventLevel.DEBUG,
                message="Starting default Nano ID generation",
                data={
                    "operation": "get_default_nanoid",
                    "size": 21,  # Default size
                    "use_case": "sqlalchemy_default"
                }
            )
        except Exception:
            pass

    try:
        nano_id = generate_nanoid()

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=SystemEventType.ID_GENERATION_COMPLETED,
                    level=EventLevel.DEBUG,
                    message="Default Nano ID generation completed successfully",
                    data={
                        "operation": "get_default_nanoid",
                        "size": 21,
                        "generated_id_length": len(nano_id),
                        "use_case": "sqlalchemy_default"
                    }
                )
            except Exception:
                pass

        return nano_id

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Default Nano ID generation failed with error",
                    data={
                        "operation": "get_default_nanoid",
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
        raise
