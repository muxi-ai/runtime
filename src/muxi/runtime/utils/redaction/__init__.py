"""Entity-based redaction layer (optional, opt-out via logging.redaction.entities)."""

from .base import (
    DEFAULT_ENTITY_THRESHOLD,
    EntityDetector,
    Span,
    get_entity_detector,
    mask_spans,
    set_entity_detector,
)
from .entity import PresidioDetector, build_entity_detector

__all__ = [
    "DEFAULT_ENTITY_THRESHOLD",
    "EntityDetector",
    "Span",
    "get_entity_detector",
    "set_entity_detector",
    "mask_spans",
    "PresidioDetector",
    "build_entity_detector",
]
