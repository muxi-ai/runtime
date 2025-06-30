"""
User Preference Engine for User Experience Intelligence

Main orchestrator for user preference learning and application.
Automatically detects multi-user vs single-user deployment mode and adapts behavior accordingly.
"""

import time
from typing import List, Optional, Dict, Any
from ...datatypes.intelligence import (
    Message,
    FeedbackEvent,
    UserPreferences,
    PreferenceType,
    ConfidenceScore,
    ConversationContext,
    ExplicitPreference,
    ImplicitPreference,
    ContextualPreference,
)
from .preference_extractor import PreferenceExtractor
from .behavior_analyzer import UserBehaviorAnalyzer
from .context_predictor import ContextPredictor


class UserPreferenceEngine:
    """
    Advanced user preference learning and application with multi/single-user support

    Automatically detects deployment mode based on overlord configuration:
    - Multi-user mode: PostgreSQL + Memobase (strict user separation)
    - Single-user mode: No long-term memory OR SQLite (global preferences)
    """

    def __init__(self, overlord):
        """
        Initialize preference engine with automatic mode detection

        Args:
            overlord: Overlord instance for accessing memory and models
        """
        self.overlord = overlord
        self.preference_extractor = PreferenceExtractor()
        self.behavior_analyzer = UserBehaviorAnalyzer()
        self.context_predictor = ContextPredictor()

        # Automatically detect deployment mode
        self.is_multi_user = self._detect_multi_user_mode()

        # Cache for user preferences to avoid repeated analysis
        self.preference_cache = {}
        self.cache_ttl = 3600  # 1 hour cache TTL

    def _detect_multi_user_mode(self) -> bool:
        """
        Detect if system should operate in multi-user mode

        Returns:
            True if multi-user mode, False if single-user mode
        """
        try:
            # Check if we have long-term memory and it's a Memobase instance
            if not self.overlord.long_term_memory:
                return False

            # Import here to avoid circular imports
            from ...services.memory.memobase import Memobase

            if not isinstance(self.overlord.long_term_memory, Memobase):
                return False

            # Check if it uses PostgreSQL (multi-user) vs SQLite (single-user)
            return self.overlord.long_term_memory.uses_postgresql()

        except Exception:
            # If there's any error in detection, default to single-user mode
            return False

    async def analyze_user_preferences(
        self,
        user_id: Optional[str],
        conversation_history: List[Message],
        feedback_data: List[FeedbackEvent],
    ) -> UserPreferences:
        """
        Extract and analyze user preferences with mode-aware operation

        Args:
            user_id: User identifier (required in multi-user mode, ignored in single-user mode)
            conversation_history: List of conversation messages
            feedback_data: List of feedback events

        Returns:
            UserPreferences object with all discovered preferences
        """
        # Multi-user mode: strict user separation and validation
        if self.is_multi_user:
            if not user_id:
                raise ValueError("user_id required in multi-user mode")

            # Filter data for this specific user
            user_history = await self._filter_user_history(conversation_history, user_id)
            user_feedback = await self._filter_user_feedback(feedback_data, user_id)
            storage_key = f"user_preferences_{user_id}"
            cache_key = f"preferences_{user_id}"

        # Single-user mode: global preference learning
        else:
            user_history = conversation_history  # Use all history
            user_feedback = feedback_data  # Use all feedback
            storage_key = "global_user_preferences"  # Single preference model
            cache_key = "global_preferences"
            user_id = None  # Normalize to None for single-user mode

        # Check cache first
        cached_preferences = self._get_cached_preferences(cache_key)
        if cached_preferences:
            return cached_preferences

        # Extract explicit preferences from conversations
        extraction_result = await self.preference_extractor.extract_explicit(user_history)
        explicit_prefs = extraction_result.explicit_preferences

        # Infer implicit preferences from behavior patterns
        behavior_result = await self.behavior_analyzer.infer_preferences(
            user_history, user_feedback
        )
        implicit_prefs = behavior_result.implicit_preferences

        # Predict contextual preferences
        current_context = self._get_current_context(user_history, user_feedback)
        context_result = await self.context_predictor.predict_preferences(
            storage_key, current_context
        )
        contextual_prefs = context_result.contextual_preferences

        # Calculate confidence scores for each preference type
        confidence_scores = self._calculate_confidence_scores(
            explicit_prefs, implicit_prefs, contextual_prefs
        )

        # Create user preferences object
        user_preferences = UserPreferences(
            user_id=user_id,
            deployment_mode="multi_user" if self.is_multi_user else "single_user",
            explicit=explicit_prefs,
            implicit=implicit_prefs,
            contextual=contextual_prefs,
            confidence_scores=confidence_scores,
            last_updated=time.time(),
        )

        # Cache the preferences
        self._cache_preferences(cache_key, user_preferences)

        # Store preferences for future learning (if we have long-term memory)
        if self.overlord.long_term_memory:
            await self._store_preferences(storage_key, user_preferences)

        return user_preferences

    async def update_preferences_from_feedback(
        self,
        user_id: Optional[str],
        feedback_event: FeedbackEvent,
        current_preferences: UserPreferences,
    ) -> UserPreferences:
        """
        Update user preferences based on new feedback

        Args:
            user_id: User identifier
            feedback_event: New feedback event
            current_preferences: Current user preferences

        Returns:
            Updated UserPreferences object
        """
        # Validate user_id requirement in multi-user mode
        if self.is_multi_user and not user_id:
            raise ValueError("user_id required in multi-user mode")

        # Create updated feedback list
        updated_feedback = [feedback_event]

        # Re-analyze behavior with new feedback
        behavior_result = await self.behavior_analyzer.infer_preferences(
            [], updated_feedback  # Only the new feedback for incremental update
        )

        # Update implicit preferences
        new_implicit_prefs = behavior_result.implicit_preferences
        updated_implicit = self._merge_preferences(current_preferences.implicit, new_implicit_prefs)

        # Update confidence scores
        updated_confidence_scores = self._calculate_confidence_scores(
            current_preferences.explicit, updated_implicit, current_preferences.contextual
        )

        # Create updated preferences
        updated_preferences = UserPreferences(
            user_id=current_preferences.user_id,
            deployment_mode=current_preferences.deployment_mode,
            explicit=current_preferences.explicit,
            implicit=updated_implicit,
            contextual=current_preferences.contextual,
            confidence_scores=updated_confidence_scores,
            last_updated=time.time(),
        )

        # Update cache
        cache_key = f"preferences_{user_id}" if self.is_multi_user else "global_preferences"
        self._cache_preferences(cache_key, updated_preferences)

        # Store updated preferences
        if self.overlord.long_term_memory:
            storage_key = (
                f"user_preferences_{user_id}" if self.is_multi_user else "global_user_preferences"
            )
            await self._store_preferences(storage_key, updated_preferences)

        return updated_preferences

    async def get_preferences_for_context(
        self, user_id: Optional[str], context: ConversationContext
    ) -> UserPreferences:
        """
        Get user preferences optimized for a specific context

        Args:
            user_id: User identifier
            context: Current conversation context

        Returns:
            UserPreferences optimized for the given context
        """
        # Get base preferences
        base_preferences = await self.get_stored_preferences(user_id)

        if not base_preferences:
            # If no stored preferences, create empty ones
            base_preferences = UserPreferences(
                user_id=user_id if self.is_multi_user else None,
                deployment_mode="multi_user" if self.is_multi_user else "single_user",
            )

        # Get contextual predictions
        storage_key = (
            f"user_preferences_{user_id}" if self.is_multi_user else "global_user_preferences"
        )
        context_result = await self.context_predictor.predict_preferences(storage_key, context)

        # Merge contextual preferences with base preferences
        enhanced_contextual = base_preferences.contextual + context_result.contextual_preferences

        # Create context-optimized preferences
        context_preferences = UserPreferences(
            user_id=base_preferences.user_id,
            deployment_mode=base_preferences.deployment_mode,
            explicit=base_preferences.explicit,
            implicit=base_preferences.implicit,
            contextual=enhanced_contextual,
            confidence_scores=self._calculate_confidence_scores(
                base_preferences.explicit, base_preferences.implicit, enhanced_contextual
            ),
            last_updated=time.time(),
        )

        return context_preferences

    async def get_stored_preferences(self, user_id: Optional[str]) -> Optional[UserPreferences]:
        """
        Get stored user preferences

        Args:
            user_id: User identifier

        Returns:
            Stored UserPreferences or None if not found
        """
        # Check cache first
        cache_key = f"preferences_{user_id}" if self.is_multi_user else "global_preferences"
        cached_preferences = self._get_cached_preferences(cache_key)
        if cached_preferences:
            return cached_preferences

        # Try to load from long-term memory
        if self.overlord.long_term_memory:
            storage_key = (
                f"user_preferences_{user_id}" if self.is_multi_user else "global_user_preferences"
            )
            try:
                stored_data = await self._load_preferences(storage_key)
                if stored_data:
                    preferences = self._deserialize_preferences(stored_data)
                    self._cache_preferences(cache_key, preferences)
                    return preferences
            except Exception as e:
                print(f"Error loading stored preferences: {e}")

        return None

    async def clear_user_preferences(self, user_id: Optional[str]):
        """
        Clear stored preferences for a user

        Args:
            user_id: User identifier
        """
        if self.is_multi_user and not user_id:
            raise ValueError("user_id required in multi-user mode")

        # Clear cache
        cache_key = f"preferences_{user_id}" if self.is_multi_user else "global_preferences"
        if cache_key in self.preference_cache:
            del self.preference_cache[cache_key]

        # Clear from long-term memory
        if self.overlord.long_term_memory:
            storage_key = (
                f"user_preferences_{user_id}" if self.is_multi_user else "global_user_preferences"
            )
            try:
                await self._delete_preferences(storage_key)
            except Exception as e:
                print(f"Error deleting stored preferences: {e}")

    # Helper methods for data filtering and processing

    async def _filter_user_history(self, messages: List[Message], user_id: str) -> List[Message]:
        """Filter messages for a specific user"""
        return [msg for msg in messages if msg.user_id == user_id]

    async def _filter_user_feedback(
        self, feedback: List[FeedbackEvent], user_id: str
    ) -> List[FeedbackEvent]:
        """Filter feedback for a specific user"""
        return [fb for fb in feedback if fb.user_id == user_id]

    def _get_current_context(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> ConversationContext:
        """Extract current conversation context from messages and feedback"""
        context = ConversationContext()

        if messages:
            # Analyze recent messages for context clues
            recent_messages = messages[-5:]  # Last 5 messages
            all_content = " ".join([msg.content.lower() for msg in recent_messages])

            # Simple topic extraction
            if any(
                keyword in all_content for keyword in ["urgent", "emergency", "asap", "quickly"]
            ):
                context.urgency = "high"
            elif any(
                keyword in all_content for keyword in ["when you can", "no rush", "take your time"]
            ):
                context.urgency = "low"

            # Simple mood detection
            if any(
                keyword in all_content for keyword in ["frustrated", "confused", "problem", "issue"]
            ):
                context.user_mood = "frustrated"
            elif any(keyword in all_content for keyword in ["excited", "great", "awesome", "love"]):
                context.user_mood = "excited"

            # Session length
            context.session_length = len(messages)

            # Available modalities (simplified)
            context.available_modalities = [
                "text"
            ]  # Could be enhanced to detect multimodal content

        return context

    def _calculate_confidence_scores(
        self,
        explicit: List[ExplicitPreference],
        implicit: List[ImplicitPreference],
        contextual: List[ContextualPreference],
    ) -> Dict[PreferenceType, ConfidenceScore]:
        """Calculate overall confidence scores for each preference type"""
        confidence_scores = {}

        for pref_type in PreferenceType:
            # Collect all preferences of this type
            explicit_prefs = [p for p in explicit if p.preference_type == pref_type]
            implicit_prefs = [p for p in implicit if p.preference_type == pref_type]
            contextual_prefs = [p for p in contextual if p.preference_type == pref_type]

            all_prefs = explicit_prefs + implicit_prefs + contextual_prefs

            if all_prefs:
                # Calculate combined confidence
                total_confidence = sum(p.confidence.weighted_confidence for p in all_prefs)
                avg_confidence = total_confidence / len(all_prefs)

                # Calculate data points and consistency
                total_data_points = sum(p.confidence.data_points for p in all_prefs)
                avg_recency = sum(p.confidence.recency for p in all_prefs) / len(all_prefs)

                # Consistency based on agreement between preferences
                consistency = self._calculate_preference_consistency(all_prefs)

                confidence_scores[pref_type] = ConfidenceScore(
                    value=avg_confidence,
                    data_points=total_data_points,
                    recency=avg_recency,
                    consistency=consistency,
                )

        return confidence_scores

    def _calculate_preference_consistency(self, preferences) -> float:
        """Calculate consistency between multiple preferences of the same type"""
        if len(preferences) <= 1:
            return 1.0

        # Simple consistency check - could be enhanced
        values = [str(p.value) for p in preferences]
        unique_values = len(set(values))
        return 1.0 - (unique_values - 1) / len(preferences)

    def _merge_preferences(self, existing, new) -> List:
        """Merge new preferences with existing ones, keeping the most confident"""
        merged = existing.copy()

        for new_pref in new:
            # Find if there's an existing preference of the same type
            existing_pref = next(
                (p for p in merged if p.preference_type == new_pref.preference_type), None
            )

            if existing_pref:
                # Replace if new preference is more confident
                if (
                    new_pref.confidence.weighted_confidence
                    > existing_pref.confidence.weighted_confidence
                ):
                    merged.remove(existing_pref)
                    merged.append(new_pref)
            else:
                # Add new preference
                merged.append(new_pref)

        return merged

    # Cache management methods

    def _get_cached_preferences(self, cache_key: str) -> Optional[UserPreferences]:
        """Get preferences from cache if not expired"""
        if cache_key in self.preference_cache:
            cached_data, timestamp = self.preference_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return cached_data
            else:
                # Remove expired cache entry
                del self.preference_cache[cache_key]
        return None

    def _cache_preferences(self, cache_key: str, preferences: UserPreferences):
        """Cache preferences with timestamp"""
        self.preference_cache[cache_key] = (preferences, time.time())

    # Storage methods (would be implemented based on available memory system)

    async def _store_preferences(self, storage_key: str, preferences: UserPreferences):
        """Store preferences in long-term memory"""
        try:
            serialized_data = self._serialize_preferences(preferences)

            # Extract user_id from storage_key for multi-user mode
            user_id = None
            if self.is_multi_user and storage_key.startswith("user_preferences_"):
                user_id = storage_key.replace("user_preferences_", "")

            # Store in long-term memory
            await self.overlord.long_term_memory.add(
                content=f"User preferences for {storage_key}",
                metadata={
                    "type": "user_preferences",
                    "storage_key": storage_key,
                    "preferences_data": serialized_data,
                    "last_updated": preferences.last_updated,
                },
                external_user_id=user_id,
            )
        except Exception as e:
            print(f"Error storing preferences: {e}")

    async def _load_preferences(self, storage_key: str) -> Optional[Dict[str, Any]]:
        """Load preferences from long-term memory"""
        try:
            # Extract user_id from storage_key for multi-user mode
            user_id = None
            if self.is_multi_user and storage_key.startswith("user_preferences_"):
                user_id = storage_key.replace("user_preferences_", "")

            # Search for preferences in long-term memory
            results = await self.overlord.long_term_memory.search(
                query=f"User preferences for {storage_key}",
                limit=1,
                filter_metadata={"type": "user_preferences", "storage_key": storage_key},
                external_user_id=user_id,
            )

            if results and len(results) > 0:
                # Get the most recent preferences
                most_recent = results[0]
                metadata = most_recent.get("metadata", {})
                return metadata.get("preferences_data")

            return None
        except Exception as e:
            print(f"Error loading preferences: {e}")
            return None

    async def _delete_preferences(self, storage_key: str):
        """Delete preferences from long-term memory"""
        try:
            # Extract user_id from storage_key for multi-user mode
            user_id = None
            if self.is_multi_user and storage_key.startswith("user_preferences_"):
                user_id = storage_key.replace("user_preferences_", "")

            # Search for preferences to get the memory ID
            results = await self.overlord.long_term_memory.search(
                query=f"User preferences for {storage_key}",
                limit=1,
                filter_metadata={"type": "user_preferences", "storage_key": storage_key},
                external_user_id=user_id,
            )

            if results and len(results) > 0:
                # Delete the memory using its ID
                memory_id = results[0].get("id")
                if memory_id:
                    self.overlord.long_term_memory.delete(memory_id)
        except Exception as e:
            print(f"Error deleting preferences: {e}")

    def _serialize_preferences(self, preferences: UserPreferences) -> Dict[str, Any]:
        """Serialize preferences for storage"""
        return {
            "user_id": preferences.user_id,
            "deployment_mode": preferences.deployment_mode,
            "last_updated": preferences.last_updated,
            "explicit": [
                {
                    "preference_type": pref.preference_type.value,
                    "value": pref.value,
                    "confidence": {
                        "value": pref.confidence.value,
                        "data_points": pref.confidence.data_points,
                        "recency": pref.confidence.recency,
                        "consistency": pref.confidence.consistency,
                    },
                }
                for pref in preferences.explicit
            ],
            "implicit": [
                {
                    "preference_type": pref.preference_type.value,
                    "value": pref.value,
                    "confidence": {
                        "value": pref.confidence.value,
                        "data_points": pref.confidence.data_points,
                        "recency": pref.confidence.recency,
                        "consistency": pref.confidence.consistency,
                    },
                    "inferred_from": pref.inferred_from,
                }
                for pref in preferences.implicit
            ],
            "contextual": [
                {
                    "preference_type": pref.preference_type.value,
                    "value": pref.value,
                    "confidence": {
                        "value": pref.confidence.value,
                        "data_points": pref.confidence.data_points,
                        "recency": pref.confidence.recency,
                        "consistency": pref.confidence.consistency,
                    },
                    "context_conditions": pref.context_conditions,
                }
                for pref in preferences.contextual
            ],
            "confidence_scores": {
                pref_type.value: {
                    "value": score.value,
                    "data_points": score.data_points,
                    "recency": score.recency,
                    "consistency": score.consistency,
                }
                for pref_type, score in preferences.confidence_scores.items()
            },
        }

    def _deserialize_preferences(self, data: Dict[str, Any]) -> UserPreferences:
        """Deserialize preferences from storage"""
        # Deserialize explicit preferences
        explicit_prefs = []
        for pref_data in data.get("explicit", []):
            explicit_prefs.append(
                ExplicitPreference(
                    preference_type=PreferenceType(pref_data["preference_type"]),
                    value=pref_data["value"],
                    confidence=ConfidenceScore(**pref_data["confidence"]),
                )
            )

        # Deserialize implicit preferences
        implicit_prefs = []
        for pref_data in data.get("implicit", []):
            implicit_prefs.append(
                ImplicitPreference(
                    preference_type=PreferenceType(pref_data["preference_type"]),
                    value=pref_data["value"],
                    confidence=ConfidenceScore(**pref_data["confidence"]),
                    inferred_from=pref_data.get("inferred_from", "unknown"),
                )
            )

        # Deserialize contextual preferences
        contextual_prefs = []
        for pref_data in data.get("contextual", []):
            contextual_prefs.append(
                ContextualPreference(
                    preference_type=PreferenceType(pref_data["preference_type"]),
                    value=pref_data["value"],
                    confidence=ConfidenceScore(**pref_data["confidence"]),
                    context_conditions=pref_data.get("context_conditions", {}),
                )
            )

        # Deserialize confidence scores
        confidence_scores = {}
        for pref_type_str, score_data in data.get("confidence_scores", {}).items():
            confidence_scores[PreferenceType(pref_type_str)] = ConfidenceScore(**score_data)

        return UserPreferences(
            user_id=data.get("user_id"),
            deployment_mode=data.get("deployment_mode", "single_user"),
            explicit=explicit_prefs,
            implicit=implicit_prefs,
            contextual=contextual_prefs,
            confidence_scores=confidence_scores,
            last_updated=data.get("last_updated", time.time()),
        )
