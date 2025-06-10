"""
Preference Extractor for User Experience Intelligence

Extracts explicit user preferences from conversation history using LLM analysis.
Supports both multi-user and single-user deployment modes.
"""

import re
import json
import time
from typing import List, Dict, Any, Optional
from ...llm import LLM
from .types import (
    Message, ExplicitPreference, PreferenceType, ConfidenceScore,
    PreferenceExtractionResult
)


class PreferenceExtractor:
    """Extract explicit user preferences from conversation history"""

    def __init__(self, model: Optional[LLM] = None):
        """
        Initialize preference extractor

        Args:
            model: LLM model for preference extraction (optional, will use overlord's model if not provided)
        """
        self.model = model

        # Preference extraction prompts for different preference types
        self.extraction_prompts = {
            PreferenceType.COMMUNICATION_STYLE: {
                "patterns": [
                    r"(?i)(?:i prefer|i like|please use|can you use)\s+(?:a\s+)?(?:more\s+)?(formal|informal|casual|professional|friendly|technical|simple)\s+(?:style|tone|approach)",
                    r"(?i)(?:be more|write in a|use a)\s+(formal|informal|casual|professional|friendly|technical|simple)\s+(?:way|manner|style|tone)",
                    r"(?i)(?:i want|i need|please be)\s+(?:more\s+)?(formal|informal|casual|professional|friendly|technical|simple)",
                ],
                "prompt": """Analyze the following conversation messages and identify any explicit preferences the user has stated about communication style (formal, informal, casual, professional, friendly, technical, simple).

Look for phrases like:
- "I prefer a more formal tone"
- "Can you be more casual?"
- "Please use simple language"
- "I like technical explanations"

Messages:
{messages}

Return a JSON list of preferences found:
[
  {{
    "preference_type": "communication_style",
    "value": "formal|informal|casual|professional|friendly|technical|simple",
    "confidence": 0.0-1.0,
    "source_message": "exact quote from message",
    "reasoning": "why this indicates the preference"
  }}
]

Only include clear, explicit statements. Return empty list [] if no preferences found."""
            },

            PreferenceType.DETAIL_LEVEL: {
                "patterns": [
                    r"(?i)(?:i want|i need|give me|provide)\s+(?:more\s+)?(detailed|brief|concise|thorough|comprehensive|quick|short|long)\s+(?:explanations?|responses?|answers?|information)",
                    r"(?i)(?:keep it|make it|be more)\s+(brief|concise|detailed|thorough|short|simple)",
                    r"(?i)(?:i prefer|i like)\s+(?:more\s+)?(detailed|brief|concise|comprehensive|quick)\s+(?:responses?|explanations?|answers?)",
                ],
                "prompt": """Analyze the following conversation messages and identify any explicit preferences the user has stated about response detail level (brief, concise, detailed, thorough, comprehensive, quick, short, long).

Look for phrases like:
- "I want detailed explanations"
- "Keep it brief"
- "Give me comprehensive information"
- "I prefer concise answers"

Messages:
{messages}

Return a JSON list of preferences found:
[
  {{
    "preference_type": "detail_level",
    "value": "brief|concise|detailed|thorough|comprehensive|quick|short|long",
    "confidence": 0.0-1.0,
    "source_message": "exact quote from message",
    "reasoning": "why this indicates the preference"
  }}
]

Only include clear, explicit statements. Return empty list [] if no preferences found."""
            },

            PreferenceType.RESPONSE_FORMAT: {
                "patterns": [
                    r"(?i)(?:can you|please)\s+(?:format|structure|organize|present)\s+(?:this|that|your response|the answer)\s+(?:as|in|using)\s+(?:a\s+)?(list|table|bullets?|numbered|markdown|json|html|steps?)",
                    r"(?i)(?:i prefer|i like|use)\s+(?:a\s+)?(list|table|bullets?|numbered|markdown|json|html|step-by-step)\s+(?:format|structure|layout)",
                    r"(?i)(?:show|give|present)\s+(?:this|that|me)\s+(?:as|in)\s+(?:a\s+)?(list|table|bullets?|numbered|markdown|json|html|steps?)",
                ],
                "prompt": """Analyze the following conversation messages and identify any explicit preferences the user has stated about response format (list, table, bullets, numbered, markdown, json, html, step-by-step).

Look for phrases like:
- "Can you format this as a list?"
- "I prefer bullet points"
- "Present this in a table"
- "Use step-by-step format"

Messages:
{messages}

Return a JSON list of preferences found:
[
  {{
    "preference_type": "response_format",
    "value": "list|table|bullets|numbered|markdown|json|html|step-by-step",
    "confidence": 0.0-1.0,
    "source_message": "exact quote from message",
    "reasoning": "why this indicates the preference"
  }}
]

Only include clear, explicit statements. Return empty list [] if no preferences found."""
            },

            PreferenceType.INTERACTION_PACE: {
                "patterns": [
                    r"(?i)(?:i'm in a|this is)\s+(hurry|rush|urgent|emergency)",
                    r"(?i)(?:take your|no\s+)time|(?:don't|no need to)\s+rush",
                    r"(?i)(?:i need|i want)\s+(?:a\s+)?(quick|fast|immediate|slow|thorough)\s+(?:response|answer|reply)",
                ],
                "prompt": """Analyze the following conversation messages and identify any explicit preferences the user has stated about interaction pace (quick, fast, immediate, slow, thorough, relaxed, urgent).

Look for phrases like:
- "I'm in a hurry"
- "Take your time"
- "I need a quick response"
- "This is urgent"

Messages:
{messages}

Return a JSON list of preferences found:
[
  {{
    "preference_type": "interaction_pace",
    "value": "quick|fast|immediate|slow|thorough|relaxed|urgent",
    "confidence": 0.0-1.0,
    "source_message": "exact quote from message",
    "reasoning": "why this indicates the preference"
  }}
]

Only include clear, explicit statements. Return empty list [] if no preferences found."""
            }
        }

    async def extract_explicit(self, conversation_history: List[Message]) -> PreferenceExtractionResult:
        """
        Extract explicit preferences from conversation history

        Args:
            conversation_history: List of conversation messages

        Returns:
            PreferenceExtractionResult with extracted preferences
        """
        if not conversation_history:
            return PreferenceExtractionResult(
                explicit_preferences=[],
                confidence_score=0.0,
                extraction_method="pattern_matching",
                supporting_evidence=[]
            )

        # First try pattern matching for quick extraction
        pattern_preferences = await self._extract_with_patterns(conversation_history)

        # Then use LLM for more sophisticated extraction if model is available
        llm_preferences = []
        if self.model:
            llm_preferences = await self._extract_with_llm(conversation_history)

        # Combine and deduplicate preferences
        all_preferences = pattern_preferences + llm_preferences
        deduplicated_preferences = self._deduplicate_preferences(all_preferences)

        # Calculate overall confidence
        confidence_score = self._calculate_extraction_confidence(
            deduplicated_preferences, len(conversation_history)
        )

        # Collect supporting evidence
        supporting_evidence = [pref.source_message for pref in deduplicated_preferences]

        extraction_method = "pattern_matching"
        if self.model:
            extraction_method = "pattern_matching + llm_analysis"

        return PreferenceExtractionResult(
            explicit_preferences=deduplicated_preferences,
            confidence_score=confidence_score,
            extraction_method=extraction_method,
            supporting_evidence=supporting_evidence
        )

    async def _extract_with_patterns(self, messages: List[Message]) -> List[ExplicitPreference]:
        """Extract preferences using regex patterns"""
        preferences = []

        for message in messages:
            if message.role != "user":
                continue

            content = message.content.lower()

            for pref_type, config in self.extraction_prompts.items():
                for pattern in config["patterns"]:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        # Extract the preference value from the match
                        value = self._extract_value_from_match(match, pref_type)
                        if value:
                            confidence = ConfidenceScore(
                                value=0.8,  # High confidence for pattern matches
                                data_points=1,
                                recency=self._calculate_message_recency(message.timestamp),
                                consistency=1.0  # Single observation, so consistent
                            )

                            preference = ExplicitPreference(
                                preference_type=pref_type,
                                value=value,
                                confidence=confidence,
                                source_message=message.content,
                                timestamp=message.timestamp,
                                context={"extraction_method": "pattern_matching"}
                            )
                            preferences.append(preference)

        return preferences

    async def _extract_with_llm(self, messages: List[Message]) -> List[ExplicitPreference]:
        """Extract preferences using LLM analysis"""
        preferences = []

        # Prepare messages for LLM analysis
        message_text = "\n".join([
            f"{msg.role}: {msg.content}" for msg in messages[-10:]  # Last 10 messages
        ])

        # Extract preferences for each type
        for pref_type, config in self.extraction_prompts.items():
            try:
                prompt = config["prompt"].format(messages=message_text)
                response = await self.model.generate(prompt)

                # Parse JSON response
                preferences_data = self._parse_llm_response(response)

                for pref_data in preferences_data:
                    if pref_data.get("preference_type") == pref_type.value:
                        confidence = ConfidenceScore(
                            value=float(pref_data.get("confidence", 0.7)),
                            data_points=1,
                            recency=self._calculate_recent_message_recency(messages),
                            consistency=1.0
                        )

                        preference = ExplicitPreference(
                            preference_type=pref_type,
                            value=pref_data.get("value"),
                            confidence=confidence,
                            source_message=pref_data.get("source_message", ""),
                            timestamp=time.time(),
                            context={
                                "extraction_method": "llm_analysis",
                                "reasoning": pref_data.get("reasoning", "")
                            }
                        )
                        preferences.append(preference)

            except Exception as e:
                # Log error but continue with other preference types
                print(f"Error extracting {pref_type.value} with LLM: {e}")
                continue

        return preferences

    def _extract_value_from_match(self, match, pref_type: PreferenceType) -> Optional[str]:
        """Extract preference value from regex match"""
        try:
            groups = match.groups()
            if groups:
                return groups[0].lower()
        except Exception:
            pass
        return None

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
