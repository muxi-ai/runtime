"""
Context Predictor for User Experience Intelligence

Predicts contextual user preferences based on current conversation context,
historical patterns, and environmental factors.
"""

import time
import json
from typing import Dict, Any, Optional, List
from collections import defaultdict
from .types import (
    ContextualPreference, PreferenceType, ConfidenceScore,
    ConversationContext, ContextPredictionResult
)


class ContextPredictor:
    """Predict contextual user preferences based on conversation context"""

    def __init__(self):
        """Initialize context predictor"""
        self.context_patterns = {}
        self.prediction_models = {
            "time_based": self._predict_time_based_preferences,
            "topic_based": self._predict_topic_based_preferences,
            "session_based": self._predict_session_based_preferences,
            "urgency_based": self._predict_urgency_based_preferences,
            "mood_based": self._predict_mood_based_preferences,
            "task_based": self._predict_task_based_preferences
        }

    async def predict_preferences(self,
                                storage_key: str,
                                current_context: ConversationContext) -> ContextPredictionResult:
        """
        Predict contextual preferences based on current context

        Args:
            storage_key: Key for accessing stored context patterns
            current_context: Current conversation context

        Returns:
            ContextPredictionResult with predicted contextual preferences
        """
        contextual_preferences = []
        context_factors = {}
        prediction_methods = []

        # Run all prediction models
        for model_name, prediction_method in self.prediction_models.items():
            try:
                model_result = await prediction_method(storage_key, current_context)
                if model_result:
                    preferences, factors = model_result
                    contextual_preferences.extend(preferences)
                    context_factors[model_name] = factors
                    prediction_methods.append(model_name)

            except Exception as e:
                print(f"Error in {model_name} prediction: {e}")
                continue

        # Calculate prediction confidence
        prediction_confidence = self._calculate_prediction_confidence(
            contextual_preferences, context_factors, current_context
        )

        return ContextPredictionResult(
            contextual_preferences=contextual_preferences,
            prediction_confidence=prediction_confidence,
            prediction_method=", ".join(prediction_methods),
            context_factors=context_factors
        )

    async def _predict_time_based_preferences(self,
                                            storage_key: str,
                                            context: ConversationContext) -> Optional[tuple]:
        """Predict preferences based on time of day/week patterns"""
        current_time = time.time()
        hour_of_day = int((current_time % 86400) // 3600)
        day_of_week = int((current_time // 86400) % 7)

        preferences = []
        factors = {
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "time_period": self._get_time_period(hour_of_day)
        }

        # Morning hours (6-12): Brief, quick responses
        if 6 <= hour_of_day < 12:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="brief",
                confidence=ConfidenceScore(value=0.6, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"time_period": "morning"},
                prediction_method="time_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.INTERACTION_PACE,
                value="quick",
                confidence=ConfidenceScore(value=0.65, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"time_period": "morning"},
                prediction_method="time_based",
                timestamp=current_time
            ))

        # Evening hours (18-22): More detailed, relaxed responses
        elif 18 <= hour_of_day < 22:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="detailed",
                confidence=ConfidenceScore(value=0.6, data_points=1, recency=1.0, consistency=0.7),
                context_conditions={"time_period": "evening"},
                prediction_method="time_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.INTERACTION_PACE,
                value="relaxed",
                confidence=ConfidenceScore(value=0.65, data_points=1, recency=1.0, consistency=0.7),
                context_conditions={"time_period": "evening"},
                prediction_method="time_based",
                timestamp=current_time
            ))

        # Weekend patterns
        if day_of_week in [5, 6]:  # Saturday, Sunday
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.COMMUNICATION_STYLE,
                value="casual",
                confidence=ConfidenceScore(value=0.55, data_points=1, recency=1.0, consistency=0.7),
                context_conditions={"day_type": "weekend"},
                prediction_method="time_based",
                timestamp=current_time
            ))

        return preferences, factors if preferences else None

    async def _predict_topic_based_preferences(self,
                                             storage_key: str,
                                             context: ConversationContext) -> Optional[tuple]:
        """Predict preferences based on conversation topic"""
        if not context.topic:
            return None

        preferences = []
        factors = {"topic": context.topic}
        current_time = time.time()

        topic_lower = context.topic.lower()

        # Technical topics
        if any(keyword in topic_lower for keyword in [
            "programming", "code", "software", "algorithm", "database", "api", "technical"
        ]):
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.TECHNICAL_DEPTH,
                value="high_technical",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.9),
                context_conditions={"topic_category": "technical"},
                prediction_method="topic_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.RESPONSE_FORMAT,
                value="code_blocks",
                confidence=ConfidenceScore(value=0.7, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"topic_category": "technical"},
                prediction_method="topic_based",
                timestamp=current_time
            ))

        # Educational/learning topics
        elif any(keyword in topic_lower for keyword in [
            "learn", "explain", "understand", "tutorial", "guide", "how to"
        ]):
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="comprehensive",
                confidence=ConfidenceScore(value=0.7, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"topic_category": "educational"},
                prediction_method="topic_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.RESPONSE_FORMAT,
                value="step-by-step",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"topic_category": "educational"},
                prediction_method="topic_based",
                timestamp=current_time
            ))

        # Quick reference/lookup topics
        elif any(keyword in topic_lower for keyword in [
            "quick", "fast", "summary", "overview", "definition", "what is"
        ]):
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="brief",
                confidence=ConfidenceScore(value=0.8, data_points=1, recency=1.0, consistency=0.9),
                context_conditions={"topic_category": "quick_reference"},
                prediction_method="topic_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.INTERACTION_PACE,
                value="immediate",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"topic_category": "quick_reference"},
                prediction_method="topic_based",
                timestamp=current_time
            ))

        return preferences, factors if preferences else None

    async def _predict_session_based_preferences(self,
                                               storage_key: str,
                                               context: ConversationContext) -> Optional[tuple]:
        """Predict preferences based on session characteristics"""
        preferences = []
        factors = {
            "session_length": context.session_length,
            "previous_adaptations": len(context.previous_adaptations)
        }
        current_time = time.time()

        # Long sessions - user might want more efficiency
        if context.session_length > 20:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.COMMUNICATION_STYLE,
                value="professional",
                confidence=ConfidenceScore(value=0.6, data_points=1, recency=1.0, consistency=0.7),
                context_conditions={"session_type": "long"},
                prediction_method="session_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="concise",
                confidence=ConfidenceScore(value=0.65, data_points=1, recency=1.0, consistency=0.75),
                context_conditions={"session_type": "long"},
                prediction_method="session_based",
                timestamp=current_time
            ))

        # Short sessions - user might want quick interaction
        elif context.session_length < 5:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.INTERACTION_PACE,
                value="quick",
                confidence=ConfidenceScore(value=0.7, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"session_type": "short"},
                prediction_method="session_based",
                timestamp=current_time
            ))

        # Many previous adaptations - user might have established preferences
        if len(context.previous_adaptations) > 5:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.COMMUNICATION_STYLE,
                value="consistent",
                confidence=ConfidenceScore(value=0.75, data_points=len(context.previous_adaptations),
                                         recency=1.0, consistency=0.9),
                context_conditions={"adaptation_history": "extensive"},
                prediction_method="session_based",
                timestamp=current_time
            ))

        return preferences, factors if preferences else None

    async def _predict_urgency_based_preferences(self,
                                               storage_key: str,
                                               context: ConversationContext) -> Optional[tuple]:
        """Predict preferences based on urgency level"""
        if not context.urgency:
            return None

        preferences = []
        factors = {"urgency_level": context.urgency}
        current_time = time.time()

        if context.urgency in ["high", "urgent", "emergency"]:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="brief",
                confidence=ConfidenceScore(value=0.9, data_points=1, recency=1.0, consistency=0.95),
                context_conditions={"urgency": "high"},
                prediction_method="urgency_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.INTERACTION_PACE,
                value="immediate",
                confidence=ConfidenceScore(value=0.95, data_points=1, recency=1.0, consistency=0.98),
                context_conditions={"urgency": "high"},
                prediction_method="urgency_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.RESPONSE_FORMAT,
                value="numbered",
                confidence=ConfidenceScore(value=0.8, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"urgency": "high"},
                prediction_method="urgency_based",
                timestamp=current_time
            ))

        elif context.urgency in ["low", "relaxed"]:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="comprehensive",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"urgency": "low"},
                prediction_method="urgency_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.COMMUNICATION_STYLE,
                value="friendly",
                confidence=ConfidenceScore(value=0.7, data_points=1, recency=1.0, consistency=0.75),
                context_conditions={"urgency": "low"},
                prediction_method="urgency_based",
                timestamp=current_time
            ))

        return preferences, factors if preferences else None

    async def _predict_mood_based_preferences(self,
                                            storage_key: str,
                                            context: ConversationContext) -> Optional[tuple]:
        """Predict preferences based on user mood"""
        if not context.user_mood:
            return None

        preferences = []
        factors = {"user_mood": context.user_mood}
        current_time = time.time()

        if context.user_mood in ["frustrated", "stressed", "confused"]:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.COMMUNICATION_STYLE,
                value="friendly",
                confidence=ConfidenceScore(value=0.8, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"mood": "negative"},
                prediction_method="mood_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="detailed",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"mood": "negative"},
                prediction_method="mood_based",
                timestamp=current_time
            ))

        elif context.user_mood in ["excited", "curious", "engaged"]:
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.COMMUNICATION_STYLE,
                value="enthusiastic",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"mood": "positive"},
                prediction_method="mood_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="comprehensive",
                confidence=ConfidenceScore(value=0.7, data_points=1, recency=1.0, consistency=0.75),
                context_conditions={"mood": "positive"},
                prediction_method="mood_based",
                timestamp=current_time
            ))

        return preferences, factors if preferences else None

    async def _predict_task_based_preferences(self,
                                            storage_key: str,
                                            context: ConversationContext) -> Optional[tuple]:
        """Predict preferences based on current task"""
        if not context.current_task:
            return None

        preferences = []
        factors = {"current_task": context.current_task}
        current_time = time.time()

        task_lower = context.current_task.lower()

        # Debugging/problem-solving tasks
        if any(keyword in task_lower for keyword in [
            "debug", "error", "problem", "issue", "fix", "troubleshoot"
        ]):
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.RESPONSE_FORMAT,
                value="step-by-step",
                confidence=ConfidenceScore(value=0.85, data_points=1, recency=1.0, consistency=0.9),
                context_conditions={"task_type": "debugging"},
                prediction_method="task_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.TECHNICAL_DEPTH,
                value="high_technical",
                confidence=ConfidenceScore(value=0.8, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"task_type": "debugging"},
                prediction_method="task_based",
                timestamp=current_time
            ))

        # Design/planning tasks
        elif any(keyword in task_lower for keyword in [
            "design", "plan", "architecture", "structure", "organize"
        ]):
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.RESPONSE_FORMAT,
                value="structured",
                confidence=ConfidenceScore(value=0.8, data_points=1, recency=1.0, consistency=0.85),
                context_conditions={"task_type": "design"},
                prediction_method="task_based",
                timestamp=current_time
            ))

            preferences.append(ContextualPreference(
                preference_type=PreferenceType.DETAIL_LEVEL,
                value="comprehensive",
                confidence=ConfidenceScore(value=0.75, data_points=1, recency=1.0, consistency=0.8),
                context_conditions={"task_type": "design"},
                prediction_method="task_based",
                timestamp=current_time
            ))

        # Implementation tasks
        elif any(keyword in task_lower for keyword in [
            "implement", "code", "build", "create", "develop"
        ]):
            preferences.append(ContextualPreference(
                preference_type=PreferenceType.RESPONSE_FORMAT,
                value="code_blocks",
                confidence=ConfidenceScore(value=0.9, data_points=1, recency=1.0, consistency=0.95),
                context_conditions={"task_type": "implementation"},
                prediction_method="task_based",
                timestamp=current_time
            ))

        return preferences, factors if preferences else None

    def _get_time_period(self, hour: int) -> str:
        """Get time period label for hour of day"""
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    def _calculate_prediction_confidence(self,
                                       preferences: List[ContextualPreference],
                                       context_factors: Dict[str, Any],
                                       current_context: ConversationContext) -> float:
        """Calculate overall confidence in contextual predictions"""
        if not preferences:
            return 0.0

        # Base confidence on individual preference confidences
        avg_confidence = sum(p.confidence.weighted_confidence for p in preferences) / len(preferences)

        # Adjust for context richness
        context_richness = 0.0
        total_factors = 7  # Total possible context factors

        if current_context.topic:
            context_richness += 1
        if current_context.urgency:
            context_richness += 1
        if current_context.user_mood:
            context_richness += 1
        if current_context.current_task:
            context_richness += 1
        if current_context.session_length > 0:
            context_richness += 1
        if current_context.previous_adaptations:
            context_richness += 1
        if current_context.available_modalities:
            context_richness += 1

        context_factor = context_richness / total_factors

        # Adjust for prediction model diversity
        model_diversity = len(context_factors) / len(self.prediction_models)

        return avg_confidence * 0.7 + context_factor * 0.2 + model_diversity * 0.1

    def store_context_pattern(self, storage_key: str, pattern_data: Dict[str, Any]):
        """Store a context pattern for future predictions"""
        # This would typically store to persistent storage
        # For now, store in memory
        self.context_patterns[storage_key] = pattern_data

    def get_context_pattern(self, storage_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored context pattern"""
        return self.context_patterns.get(storage_key)
