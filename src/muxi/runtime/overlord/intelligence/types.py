"""
Types and Data Structures for User Experience Intelligence

Phase 3 implementation types supporting both multi-user and single-user modes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal
from enum import Enum
import time


class PreferenceType(Enum):
    """Types of user preferences that can be learned"""
    COMMUNICATION_STYLE = "communication_style"
    DETAIL_LEVEL = "detail_level"
    RESPONSE_FORMAT = "response_format"
    INTERACTION_PACE = "interaction_pace"
    CONTENT_TYPE = "content_type"
    TECHNICAL_DEPTH = "technical_depth"
    VISUAL_PREFERENCE = "visual_preference"
    LANGUAGE_COMPLEXITY = "language_complexity"


class AdaptationType(Enum):
    """Types of adaptations that can be applied to responses"""
    STYLE_ADAPTATION = "style_adaptation"
    DEPTH_ADAPTATION = "depth_adaptation"
    FORMAT_ADAPTATION = "format_adaptation"
    TIMING_ADAPTATION = "timing_adaptation"
    CONTENT_ADAPTATION = "content_adaptation"
    VISUAL_ADAPTATION = "visual_adaptation"


@dataclass
class ConfidenceScore:
    """Confidence scoring for preferences and adaptations"""
    value: float  # 0.0 to 1.0
    data_points: int  # Number of observations supporting this score
    recency: float  # How recent the data is (0.0 to 1.0, 1.0 = very recent)
    consistency: float  # How consistent the preference is (0.0 to 1.0)

    @property
    def weighted_confidence(self) -> float:
        """Calculate weighted confidence considering all factors"""
        return (self.value * 0.4 +
                min(self.data_points / 10, 1.0) * 0.3 +
                self.recency * 0.2 +
                self.consistency * 0.1)


@dataclass
class Message:
    """Represents a conversation message"""
    content: str
    role: str  # "user" or "assistant"
    timestamp: float
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedbackEvent:
    """Represents user feedback on responses"""
    user_id: Optional[str]
    message_id: str
    feedback_type: Literal["positive", "negative", "correction", "preference"]
    feedback_content: str
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExplicitPreference:
    """Explicitly stated user preference"""
    preference_type: PreferenceType
    value: Any
    confidence: ConfidenceScore
    source_message: str
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImplicitPreference:
    """Implicitly inferred user preference"""
    preference_type: PreferenceType
    value: Any
    confidence: ConfidenceScore
    inference_method: str
    supporting_evidence: List[str]
    timestamp: float


@dataclass
class ContextualPreference:
    """Context-dependent user preference"""
    preference_type: PreferenceType
    value: Any
    confidence: ConfidenceScore
    context_conditions: Dict[str, Any]
    prediction_method: str
    timestamp: float


@dataclass
class UserPreferences:
    """Complete user preference profile"""
    user_id: Optional[str]  # None for single-user mode
    deployment_mode: Literal["multi_user", "single_user"]
    explicit: List[ExplicitPreference] = field(default_factory=list)
    implicit: List[ImplicitPreference] = field(default_factory=list)
    contextual: List[ContextualPreference] = field(default_factory=list)
    confidence_scores: Dict[PreferenceType, ConfidenceScore] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)

    def get_preference(self, preference_type: PreferenceType,
                       context: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Get the best preference value for a given type and context"""
        # First try contextual preferences if context is provided
        if context:
            for pref in self.contextual:
                if pref.preference_type == preference_type:
                    if self._context_matches(pref.context_conditions, context):
                        return pref.value

        # Then try explicit preferences
        explicit_prefs = [p for p in self.explicit if p.preference_type == preference_type]
        if explicit_prefs:
            # Return the most confident explicit preference
            return max(explicit_prefs, key=lambda p: p.confidence.weighted_confidence).value

        # Finally try implicit preferences
        implicit_prefs = [p for p in self.implicit if p.preference_type == preference_type]
        if implicit_prefs:
            # Return the most confident implicit preference
            return max(implicit_prefs, key=lambda p: p.confidence.weighted_confidence).value

        return None

    def _context_matches(self, conditions: Dict[str, Any], current_context: Dict[str, Any]) -> bool:
        """Check if context conditions match current context"""
        for key, expected_value in conditions.items():
            if key not in current_context or current_context[key] != expected_value:
                return False
        return True

    @property
    def communication_style(self) -> Optional[str]:
        """Get preferred communication style"""
        return self.get_preference(PreferenceType.COMMUNICATION_STYLE)

    @property
    def detail_level(self) -> Optional[str]:
        """Get preferred detail level"""
        return self.get_preference(PreferenceType.DETAIL_LEVEL)

    @property
    def preferred_formats(self) -> Optional[List[str]]:
        """Get preferred response formats"""
        return self.get_preference(PreferenceType.RESPONSE_FORMAT)

    @property
    def interaction_pace(self) -> Optional[str]:
        """Get preferred interaction pace"""
        return self.get_preference(PreferenceType.INTERACTION_PACE)


@dataclass
class ConversationContext:
    """Current conversation context for adaptation"""
    topic: Optional[str] = None
    complexity_level: Optional[str] = None
    urgency: Optional[str] = None
    user_mood: Optional[str] = None
    session_length: int = 0
    previous_adaptations: List[str] = field(default_factory=list)
    current_task: Optional[str] = None
    available_modalities: List[str] = field(default_factory=lambda: ["text"])
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdaptationDetails:
    """Details about a specific adaptation applied"""
    adaptation_type: AdaptationType
    original_value: Any
    adapted_value: Any
    reason: str
    confidence: float
    method_used: str


@dataclass
class AdaptedResponse:
    """Response that has been adapted based on user preferences"""
    user_id: Optional[str]  # None for single-user mode
    deployment_mode: Literal["multi_user", "single_user"]
    original: str
    adapted: str
    adaptations_applied: List[AdaptationDetails] = field(default_factory=list)
    confidence: float = 0.0
    adaptation_time: float = field(default_factory=time.time)
    context_used: Optional[ConversationContext] = None
    preferences_used: Optional[UserPreferences] = None

    @property
    def adaptation_summary(self) -> Dict[str, Any]:
        """Get summary of adaptations applied"""
        return {
            "total_adaptations": len(self.adaptations_applied),
            "adaptation_types": [a.adaptation_type.value for a in self.adaptations_applied],
            "average_confidence": (
                sum(a.confidence for a in self.adaptations_applied) /
                len(self.adaptations_applied) if self.adaptations_applied else 0.0
            ),
            "deployment_mode": self.deployment_mode
        }


@dataclass
class LearningEvent:
    """Event for learning from user interactions"""
    user_id: Optional[str]
    event_type: Literal[
        "response_generated", "feedback_received", "preference_updated", "adaptation_applied"
    ]
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    context: Optional[ConversationContext] = None


@dataclass
class PreferenceExtractionResult:
    """Result of preference extraction from conversations"""
    explicit_preferences: List[ExplicitPreference]
    confidence_score: float
    extraction_method: str
    supporting_evidence: List[str]
    extraction_time: float = field(default_factory=time.time)


@dataclass
class BehaviorAnalysisResult:
    """Result of user behavior analysis"""
    implicit_preferences: List[ImplicitPreference]
    behavioral_patterns: Dict[str, Any]
    confidence_score: float
    analysis_method: str
    data_sources: List[str]
    analysis_time: float = field(default_factory=time.time)


@dataclass
class ContextPredictionResult:
    """Result of contextual preference prediction"""
    contextual_preferences: List[ContextualPreference]
    prediction_confidence: float
    prediction_method: str
    context_factors: Dict[str, Any]
    prediction_time: float = field(default_factory=time.time)
