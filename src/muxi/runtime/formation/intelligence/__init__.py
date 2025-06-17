"""
Intelligence Module for MUXI Overlord

Phase 3: User Experience Intelligence Implementation

This module provides intelligent context understanding and adaptive response generation
with automatic multi-user vs single-user mode detection based on deployment configuration.
"""

from .types import (
    UserPreferences,
    ConversationContext,
    AdaptedResponse,
    FeedbackEvent,
    PreferenceType,
    AdaptationType,
    ConfidenceScore
)

from .preference_engine import UserPreferenceEngine
from .preference_extractor import PreferenceExtractor
from .behavior_analyzer import UserBehaviorAnalyzer
from .context_predictor import ContextPredictor
from .adaptive_generator import AdaptiveResponseGenerator

__all__ = [
    # Types
    'UserPreferences',
    'ConversationContext',
    'AdaptedResponse',
    'FeedbackEvent',
    'PreferenceType',
    'AdaptationType',
    'ConfidenceScore',

    # Core Components
    'UserPreferenceEngine',
    'PreferenceExtractor',
    'UserBehaviorAnalyzer',
    'ContextPredictor',
    'AdaptiveResponseGenerator'
]
