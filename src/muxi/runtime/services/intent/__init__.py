"""
Intent Detection Service

Unified multilingual intent detection for MUXI.
"""

from .cache import IntentCache
from .service import IntentDetectionService

__all__ = [
    "IntentDetectionService",
    "IntentCache",
]
