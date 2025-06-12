"""
Preference Extractor for User Experience Intelligence

Extracts explicit user preferences from conversation history using pure LLM analysis.
Supports both multi-user and single-user deployment modes.
Uses multilingual LLM detection instead of English-only regex patterns.
"""

import json
import time
from typing import List, Dict, Any, Optional
from ...llm import LLM
from .types import (
    Message, ExplicitPreference, PreferenceType, ConfidenceScore,
    PreferenceExtractionResult
)


class PreferenceExtractor:
    """Extract explicit user preferences from conversation history using pure LLM analysis"""

    def __init__(self, model: Optional[LLM] = None):
        """
        Initialize preference extractor

        Args:
            model: LLM model for preference extraction (required for multilingual support)
        """
        self.model = model
        if not model:
            # Warn that preference extraction will be limited without LLM
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "PreferenceExtractor initialized without model - "
                "preference extraction will be disabled"
            )

    async def extract_explicit(self, conversation_history: List[Message]) -> PreferenceExtractionResult:
        """
        Extract explicit preferences from conversation history using pure LLM analysis

        Args:
            conversation_history: List of conversation messages

        Returns:
            PreferenceExtractionResult with extracted preferences
        """
        if not conversation_history:
            return PreferenceExtractionResult(
                explicit_preferences=[],
                confidence_score=0.0,
                extraction_method="no_data",
                supporting_evidence=[]
            )

        if not self.model:
            # Return empty result if no model available
            return PreferenceExtractionResult(
                explicit_preferences=[],
                confidence_score=0.0,
                extraction_method="no_model_available",
                supporting_evidence=[]
            )

        # Use pure LLM analysis for multilingual preference extraction
        extracted_preferences = await self._extract_with_llm(conversation_history)

        # Deduplicate preferences
        deduplicated_preferences = self._deduplicate_preferences(extracted_preferences)

        # Calculate overall confidence
        confidence_score = self._calculate_extraction_confidence(
            deduplicated_preferences, len(conversation_history)
        )

        # Collect supporting evidence
        supporting_evidence = [pref.source_message for pref in deduplicated_preferences]

        return PreferenceExtractionResult(
            explicit_preferences=deduplicated_preferences,
            confidence_score=confidence_score,
            extraction_method="llm_analysis_multilingual",
            supporting_evidence=supporting_evidence
        )

    async def _extract_with_llm(self, messages: List[Message]) -> List[ExplicitPreference]:
        """Extract preferences using pure LLM analysis for multilingual support"""
        preferences = []

        # Prepare messages for LLM analysis
        message_text = "\n".join([
            f"{msg.role}: {msg.content}" for msg in messages[-15:]  # Last 15 messages
        ])

        prompt = f"""
        Analyze this conversation to identify explicit user preferences about how they like to
        interact and receive information. Look for any language where users explicitly state
        preferences about:

        1. COMMUNICATION_STYLE: formal, informal, casual, professional, friendly, technical, simple
        2. DETAIL_LEVEL: brief, concise, detailed, thorough, comprehensive, quick, short, long
        3. RESPONSE_FORMAT: list, table, bullets, numbered, markdown, json, html, step-by-step
        4. INTERACTION_PACE: quick, fast, immediate, slow, thorough, relaxed, urgent

        Examples across languages:
        - English: "I prefer a more formal tone", "Keep it brief", "Use bullet points"
        - Spanish: "Prefiero un estilo más formal", "Hazlo breve", "Usa puntos"
        - French: "Je préfère un ton plus formel", "Soyez bref", "Utilisez des puces"
        - German: "Ich bevorzuge einen formelleren Stil", "Halten Sie es kurz"
        - Chinese: "我喜欢正式的语调", "请简洁一些"
        - Japanese: "もっと正式な口調を好みます", "簡潔にしてください"

        Look for EXPLICIT statements only - not implied or inferred preferences.

        Conversation:
        {message_text}

        Respond with JSON only:
        [
          {{
            "preference_type": "communication_style|detail_level|response_format|interaction_pace",
            "value": "specific preference value (e.g., formal, brief, bullets, quick)",
            "confidence": 0.0-1.0,
            "source_message": "exact quote from user that shows this preference",
            "reasoning": "why this indicates the stated preference"
          }}
        ]

        Return empty list [] if no explicit preferences found.
        Minimum confidence threshold: 0.6
        """

        try:
            response = await self.model.generate(prompt, temperature=0.1, max_tokens=800)

            # Parse LLM response
            preferences_data = self._parse_llm_response(response)

            for pref_data in preferences_data:
                if pref_data.get("confidence", 0) >= 0.6:
                    # Map preference type string to enum
                    pref_type = self._map_preference_type(pref_data.get("preference_type"))

                    if pref_type:
                        confidence = ConfidenceScore(
                            value=float(pref_data.get("confidence", 0.6)),
                            data_points=1,
                            recency=self._calculate_recent_message_recency(messages),
                            consistency=1.0
                        )

                        preference = ExplicitPreference(
                            preference_type=pref_type,
                            value=pref_data.get("value", ""),
                            confidence=confidence,
                            source_message=pref_data.get("source_message", ""),
                            timestamp=time.time(),
                            context={
                                "extraction_method": "llm_analysis_multilingual",
                                "reasoning": pref_data.get("reasoning", "")
                            }
                        )
                        preferences.append(preference)

        except Exception as e:
            # Log error but continue
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error extracting preferences with LLM: {e}")

        return preferences

    def _map_preference_type(self, type_string: str) -> Optional[PreferenceType]:
        """Map preference type string to enum"""
        type_mapping = {
            "communication_style": PreferenceType.COMMUNICATION_STYLE,
            "detail_level": PreferenceType.DETAIL_LEVEL,
            "response_format": PreferenceType.RESPONSE_FORMAT,
            "interaction_pace": PreferenceType.INTERACTION_PACE
        }
        return type_mapping.get(type_string)

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM response JSON"""
        try:
            # Try to find JSON in the response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1

            if json_start >= 0 and json_end > json_start:
                json_text = response[json_start:json_end]
                return json.loads(json_text)
            else:
                return []
        except Exception:
            return []

    def _deduplicate_preferences(self, preferences: List[ExplicitPreference]) -> List[ExplicitPreference]:
        """Remove duplicate preferences, keeping the most confident ones"""
        seen = {}

        for pref in preferences:
            key = (pref.preference_type, pref.value)

            if key not in seen:
                seen[key] = pref
            else:
                # Keep the one with higher confidence
                if pref.confidence.weighted_confidence > seen[key].confidence.weighted_confidence:
                    seen[key] = pref

        return list(seen.values())

    def _calculate_extraction_confidence(self, preferences: List[ExplicitPreference],
                                       message_count: int) -> float:
        """Calculate overall confidence in extraction results"""
        if not preferences:
            return 0.0

        # Base confidence on average preference confidence
        avg_confidence = sum(p.confidence.weighted_confidence for p in preferences) / len(preferences)

        # Adjust based on data volume
        data_factor = min(message_count / 10, 1.0)  # More messages = higher confidence

        return avg_confidence * 0.8 + data_factor * 0.2

    def _calculate_message_recency(self, timestamp: float) -> float:
        """Calculate recency score for a message timestamp"""
        current_time = time.time()
        age_hours = (current_time - timestamp) / 3600

        # Messages are "fresh" for 24 hours, then decay
        if age_hours <= 24:
            return 1.0
        elif age_hours <= 168:  # 1 week
            return 1.0 - (age_hours - 24) / 144  # Linear decay
        else:
            return 0.1  # Minimum recency

    def _calculate_recent_message_recency(self, messages: List[Message]) -> float:
        """Calculate average recency for recent messages"""
        if not messages:
            return 0.0

        recent_messages = messages[-5:]  # Last 5 messages
        recency_scores = [self._calculate_message_recency(msg.timestamp) for msg in recent_messages]

        return sum(recency_scores) / len(recency_scores)
