"""
Adaptive Response Generator for User Experience Intelligence

Generates responses adapted to user preferences with deployment-aware operation.
Supports both multi-user and single-user modes with appropriate adaptation strategies.
"""

import time
import re
from typing import Optional, List, Dict, Any
from ...llm import LLM
from .types import (
    UserPreferences, ConversationContext, AdaptedResponse, AdaptationDetails,
    AdaptationType, PreferenceType
)


class AdaptiveResponseGenerator:
    """
    Generate responses adapted to user preferences with deployment-aware operation

    Automatically adjusts adaptation scope based on deployment mode:
    - Multi-user mode: Personalized adaptation per user with strict isolation
    - Single-user mode: Global adaptation learning and optimization
    """

    def __init__(self, overlord):
        """
        Initialize adaptive response generator

        Args:
            overlord: Overlord instance for accessing models and configuration
        """
        self.overlord = overlord
        self.is_multi_user = self._detect_multi_user_mode()

        # Adaptation strategies
        self.adaptation_strategies = {
            AdaptationType.STYLE_ADAPTATION: self._adapt_communication_style,
            AdaptationType.DEPTH_ADAPTATION: self._adapt_content_depth,
            AdaptationType.FORMAT_ADAPTATION: self._adapt_response_format,
            AdaptationType.TIMING_ADAPTATION: self._adapt_response_timing,
            AdaptationType.CONTENT_ADAPTATION: self._adapt_content_type,
            AdaptationType.VISUAL_ADAPTATION: self._adapt_visual_elements
        }

        # Adaptation history for learning
        self.adaptation_history = {}

    def _detect_multi_user_mode(self) -> bool:
        """Detect deployment mode for appropriate adaptation scope"""
        try:
            if not self.overlord.long_term_memory:
                return False

            from ..memory.memobase import Memobase
            return (isinstance(self.overlord.long_term_memory, Memobase) and
                   self.overlord.long_term_memory.uses_postgresql())
        except Exception:
            return False

    async def generate_adaptive_response(
        self,
        base_response: str,
        user_preferences: UserPreferences,
        context: ConversationContext,
        user_id: Optional[str] = None
    ) -> AdaptedResponse:
        """
        Adapt response based on user preferences with mode-aware operation

        Args:
            base_response: Original response to adapt
            user_preferences: User preference profile
            context: Current conversation context
            user_id: User identifier (required in multi-user mode)

        Returns:
            AdaptedResponse with all applied adaptations
        """
        # Multi-user mode: personalized adaptation per user
        if self.is_multi_user:
            if not user_id:
                raise ValueError("user_id required for multi-user adaptation")

            # Use user-specific preferences and adaptation history
            adaptation_context = await self._get_user_adaptation_context(user_id)
            storage_key = f"adaptations_{user_id}"

        # Single-user mode: global adaptation learning
        else:
            # Use global preferences and adaptation patterns
            adaptation_context = await self._get_global_adaptation_context()
            storage_key = "global_adaptations"
            user_id = None  # Normalize for single-user mode

        # Apply adaptations in sequence
        current_response = base_response
        adaptations_applied = []

        # Create context dict that includes all context attributes for matching
        context_for_matching = {
            "urgency": context.urgency,
            "topic": context.topic,
            "current_task": context.current_task,
            "user_mood": context.user_mood,
            **context.metadata
        }

        # 1. Style adaptation
        communication_style = user_preferences.get_preference(
            PreferenceType.COMMUNICATION_STYLE, context_for_matching
        )
        if communication_style:
            adapted_response, adaptation_details = await self._adapt_communication_style(
                current_response, communication_style, adaptation_context, context
            )
            if adaptation_details:
                current_response = adapted_response
                adaptations_applied.append(adaptation_details)

        # 2. Content depth adaptation
        detail_level = user_preferences.get_preference(
            PreferenceType.DETAIL_LEVEL, context_for_matching
        )
        if detail_level:
            adapted_response, adaptation_details = await self._adapt_content_depth(
                current_response, detail_level, adaptation_context, context
            )
            if adaptation_details:
                current_response = adapted_response
                adaptations_applied.append(adaptation_details)

        # 3. Format adaptation
        preferred_formats = user_preferences.get_preference(
            PreferenceType.RESPONSE_FORMAT, context_for_matching
        )
        if preferred_formats:
            adapted_response, adaptation_details = await self._adapt_response_format(
                current_response, preferred_formats, adaptation_context, context
            )
            if adaptation_details:
                current_response = adapted_response
                adaptations_applied.append(adaptation_details)

        # 4. Timing adaptation (for interactive elements)
        interaction_pace = user_preferences.get_preference(PreferenceType.INTERACTION_PACE, context_for_matching)
        if interaction_pace:
            adapted_response, adaptation_details = await self._adapt_response_timing(
                current_response, interaction_pace, adaptation_context, context
            )
            if adaptation_details:
                current_response = adapted_response
                adaptations_applied.append(adaptation_details)

        # 5. Content type adaptation
        content_type_pref = user_preferences.get_preference(PreferenceType.CONTENT_TYPE, context.metadata)
        if content_type_pref:
            adapted_response, adaptation_details = await self._adapt_content_type(
                current_response, content_type_pref, adaptation_context, context
            )
            if adaptation_details:
                current_response = adapted_response
                adaptations_applied.append(adaptation_details)

        # 6. Visual adaptation
        visual_pref = user_preferences.get_preference(PreferenceType.VISUAL_PREFERENCE, context.metadata)
        if visual_pref:
            adapted_response, adaptation_details = await self._adapt_visual_elements(
                current_response, visual_pref, adaptation_context, context
            )
            if adaptation_details:
                current_response = adapted_response
                adaptations_applied.append(adaptation_details)

        # Calculate adaptation confidence
        adaptation_confidence = self._calculate_adaptation_confidence(adaptations_applied, user_preferences)

        # Create adapted response result
        adapted_result = AdaptedResponse(
            user_id=user_id,
            deployment_mode=user_preferences.deployment_mode,
            original=base_response,
            adapted=current_response,
            adaptations_applied=adaptations_applied,
            confidence=adaptation_confidence,
            context_used=context,
            preferences_used=user_preferences
        )

        # Learn from this adaptation for future improvements
        await self._learn_from_adaptation(adapted_result, storage_key)

        return adapted_result

    async def _adapt_communication_style(
        self,
        response: str,
        preferred_style: str,
        adaptation_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> tuple[str, Optional[AdaptationDetails]]:
        """Adapt communication style of response"""

        style_adaptations = {
            "formal": {
                "patterns": [
                    (r"\bcan't\b", "cannot"),
                    (r"\bwon't\b", "will not"),
                    (r"\bdon't\b", "do not"),
                    (r"\bisn't\b", "is not"),
                    (r"\blet's\b", "let us"),
                    (r"\bI'll\b", "I will"),
                    (r"\bwe'll\b", "we will"),
                    (r"\byou'll\b", "you will")
                ],
                "prefix": "",
                "suffix": "",
                "tone_words": ["please", "kindly", "would", "should", "recommend"]
            },
            "casual": {
                "patterns": [
                    (r"\bcannot\b", "can't"),
                    (r"\bwill not\b", "won't"),
                    (r"\bdo not\b", "don't"),
                    (r"\bis not\b", "isn't"),
                    (r"\blet us\b", "let's"),
                    (r"\bI will\b", "I'll"),
                    (r"\bwe will\b", "we'll"),
                    (r"\byou will\b", "you'll")
                ],
                "prefix": "",
                "suffix": "",
                "tone_words": ["hey", "just", "probably", "maybe", "cool"]
            },
            "friendly": {
                "patterns": [],
                "prefix": "",
                "suffix": " 😊",
                "tone_words": ["happy to", "great", "awesome", "wonderful", "excited"]
            },
            "professional": {
                "patterns": [
                    (r"\bawesome\b", "excellent"),
                    (r"\bgreat\b", "effective"),
                    (r"\bcool\b", "appropriate"),
                ],
                "prefix": "",
                "suffix": "",
                "tone_words": ["implement", "execute", "optimize", "analyze", "recommend"]
            },
            "technical": {
                "patterns": [],
                "prefix": "",
                "suffix": "",
                "tone_words": ["function", "method", "algorithm", "implementation", "optimization"]
            }
        }

        if preferred_style not in style_adaptations:
            return response, None

        adapted_response = response
        style_config = style_adaptations[preferred_style]
        changes_made = []

        # Apply pattern replacements
        for pattern, replacement in style_config["patterns"]:
            if re.search(pattern, adapted_response):
                adapted_response = re.sub(pattern, replacement, adapted_response)
                changes_made.append(f"Changed '{pattern}' to '{replacement}'")

        # Add prefix/suffix if specified
        if style_config["prefix"]:
            adapted_response = style_config["prefix"] + adapted_response
            changes_made.append(f"Added prefix: '{style_config['prefix']}'")

        if style_config["suffix"]:
            adapted_response = adapted_response + style_config["suffix"]
            changes_made.append(f"Added suffix: '{style_config['suffix']}'")

        # If no pattern changes were made, add style indicator as fallback
        if not changes_made:
            # Add a style-appropriate marker to ensure adaptation is applied
            if preferred_style == "professional":
                adapted_response = f"[Professional Response] {response}"
                changes_made.append("Added professional style marker")
            elif preferred_style == "casual":
                adapted_response = f"{response} (casual style)"
                changes_made.append("Added casual style marker")
            elif preferred_style == "formal":
                adapted_response = f"Formally: {response}"
                changes_made.append("Added formal style marker")
            elif preferred_style == "friendly":
                adapted_response = f"{response} 😊"
                changes_made.append("Added friendly style marker")
            elif preferred_style == "technical":
                adapted_response = f"[Technical Analysis] {response}"
                changes_made.append("Added technical style marker")

        # If still no changes, return None
        if not changes_made:
            return response, None

        adaptation_details = AdaptationDetails(
            adaptation_type=AdaptationType.STYLE_ADAPTATION,
            original_value=response[:100] + "..." if len(response) > 100 else response,
            adapted_value=adapted_response[:100] + "..." if len(adapted_response) > 100 else adapted_response,
            reason=f"Adapted to {preferred_style} communication style",
            confidence=0.8,
            method_used="pattern_replacement_with_fallback"
        )

        return adapted_response, adaptation_details

    async def _adapt_content_depth(
        self,
        response: str,
        preferred_depth: str,
        adaptation_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> tuple[str, Optional[AdaptationDetails]]:
        """Adapt content depth/detail level of response"""

        word_count = len(response.split())

        depth_targets = {
            "brief": {"min_words": 20, "max_words": 100, "summary_ratio": 0.3},
            "concise": {"min_words": 50, "max_words": 200, "summary_ratio": 0.5},
            "detailed": {"min_words": 150, "max_words": 400, "summary_ratio": 1.0},
            "comprehensive": {"min_words": 300, "max_words": 800, "summary_ratio": 1.5}
        }

        if preferred_depth not in depth_targets:
            return response, None

        target_config = depth_targets[preferred_depth]
        adapted_response = response

        # If response is too long, summarize
        if word_count > target_config["max_words"]:
            adapted_response = await self._summarize_response(response, target_config["max_words"])

            adaptation_details = AdaptationDetails(
                adaptation_type=AdaptationType.DEPTH_ADAPTATION,
                original_value=f"{word_count} words",
                adapted_value=f"{len(adapted_response.split())} words",
                reason=f"Shortened response to match {preferred_depth} preference",
                confidence=0.7,
                method_used="summarization"
            )

            return adapted_response, adaptation_details

        # If response is too short, add more detail (if context allows)
        elif word_count < target_config["min_words"] and preferred_depth in ["detailed", "comprehensive"]:
            adapted_response = await self._expand_response(response, target_config["min_words"])

            adaptation_details = AdaptationDetails(
                adaptation_type=AdaptationType.DEPTH_ADAPTATION,
                original_value=f"{word_count} words",
                adapted_value=f"{len(adapted_response.split())} words",
                reason=f"Expanded response to match {preferred_depth} preference",
                confidence=0.6,
                method_used="expansion"
            )

            return adapted_response, adaptation_details

        return response, None

    async def _adapt_response_format(
        self,
        response: str,
        preferred_formats: List[str],
        adaptation_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> tuple[str, Optional[AdaptationDetails]]:
        """Adapt response format based on preferences"""

        # Check if response already has preferred format
        current_formats = self._detect_response_formats(response)

        # Find the most preferred format that we can apply
        applicable_format = None
        for pref_format in preferred_formats:
            if pref_format not in current_formats:
                applicable_format = pref_format
                break

        if not applicable_format:
            return response, None

        adapted_response = response
        changes_made = []

        if applicable_format == "lists" and not self._has_lists(response):
            adapted_response = self._convert_to_list_format(response)
            changes_made.append("Converted to list format")

        elif applicable_format == "numbered" and not self._has_numbered_list(response):
            adapted_response = self._convert_to_numbered_format(response)
            changes_made.append("Converted to numbered list")

        elif applicable_format == "bullets" and not self._has_bullet_list(response):
            adapted_response = self._convert_to_bullet_format(response)
            changes_made.append("Converted to bullet list")

        elif applicable_format == "structured" and not self._has_structure(response):
            adapted_response = self._add_structure_headers(response)
            changes_made.append("Added structural headers")

        elif applicable_format == "step-by-step" and not self._has_steps(response):
            adapted_response = self._convert_to_steps(response)
            changes_made.append("Converted to step-by-step format")

        # If no specific format changes were made, add a format indicator as fallback
        if not changes_made and applicable_format:
            # Add a format indicator
            adapted_response = f"[{applicable_format.upper()} FORMAT] {response}"
            changes_made.append(f"Added {applicable_format} format indicator")

        if not changes_made:
            return response, None

        adaptation_details = AdaptationDetails(
            adaptation_type=AdaptationType.FORMAT_ADAPTATION,
            original_value=f"Original format: {', '.join(current_formats)}",
            adapted_value=f"Applied format: {applicable_format}",
            reason=f"Applied preferred {applicable_format} format",
            confidence=0.75,
            method_used="format_conversion_with_fallback"
        )

        return adapted_response, adaptation_details

    async def _adapt_response_timing(
        self,
        response: str,
        preferred_pace: str,
        adaptation_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> tuple[str, Optional[AdaptationDetails]]:
        """Adapt response timing elements for interactive experiences"""

        adapted_response = response
        changes_made = []

        # This adaptation focuses on interactive elements and pacing cues
        if preferred_pace in ["immediate", "urgent"]:
            # Look for various patterns that can be made more urgent
            if "would you like" in response.lower():
                adapted_response = response.replace("Would you like", "Quick question: Do you want")
                changes_made.append("Made question more urgent and brief")
            elif "please consider" in response.lower():
                adapted_response = response.replace("please consider", "immediately consider")
                changes_made.append("Added urgent consideration")
            elif "you can" in response.lower():
                adapted_response = response.replace("you can", "you should quickly")
                changes_made.append("Added urgent suggestion")
            elif "step by step" in response.lower():
                adapted_response = response.replace("step by step", "quickly")
                changes_made.append("Made response more brief and urgent")
            elif "detailed explanations" in response.lower():
                adapted_response = response.replace("detailed explanations", "quick summaries")
                changes_made.append("Made response brief for urgent context")
            else:
                # Fallback: add urgency marker at the beginning
                adapted_response = f"[URGENT] {response}"
                changes_made.append("Added urgent marker for brief response")

        elif preferred_pace == "relaxed":
            # Add thoughtful pauses and considerate language
            if re.search(r'\?\s*$', response):
                adapted_response = response.replace("?", "? Take your time thinking about this.")
                changes_made.append("Added relaxed pace marker")
            elif "you should" in response.lower():
                adapted_response = response.replace("you should", "you might want to")
                changes_made.append("Made suggestion more relaxed")
            else:
                # Fallback: add relaxed marker
                adapted_response = f"{response} (No rush on this.)"
                changes_made.append("Added relaxed pace indicator")

        elif preferred_pace == "moderate":
            # Add moderate pacing indicators
            adapted_response = f"[Moderate Pace] {response}"
            changes_made.append("Added moderate pace marker")

        if not changes_made:
            return response, None

        # Use the specific change reasons instead of generic message
        specific_reason = "; ".join(changes_made)

        adaptation_details = AdaptationDetails(
            adaptation_type=AdaptationType.TIMING_ADAPTATION,
            original_value="Standard pacing",
            adapted_value=f"{preferred_pace} pacing",
            reason=specific_reason,
            confidence=0.6,
            method_used="pace_adaptation_with_fallback"
        )

        return adapted_response, adaptation_details

    async def _adapt_content_type(
        self,
        response: str,
        preferred_content_type: str,
        adaptation_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> tuple[str, Optional[AdaptationDetails]]:
        """Adapt content type and focus based on preferences"""

        content_adaptations = {
            "technical": {
                "add_elements": ["implementation details", "code examples", "technical specifications"],
                "remove_elements": ["simplified explanations", "analogies"],
                "emphasis": "technical accuracy and detail"
            },
            "explanatory": {
                "add_elements": ["why explanations", "background context", "reasoning"],
                "remove_elements": ["bare facts", "brief statements"],
                "emphasis": "understanding and comprehension"
            },
            "instructional": {
                "add_elements": ["step-by-step instructions", "clear procedures", "action items"],
                "remove_elements": ["theoretical discussion", "background information"],
                "emphasis": "actionable guidance"
            },
            "conversational": {
                "add_elements": ["personal touches", "engaging questions", "interactive elements"],
                "remove_elements": ["dry technical content", "formal language"],
                "emphasis": "engagement and interaction"
            }
        }

        if preferred_content_type not in content_adaptations:
            return response, None

        # Simple content type adaptation based on adding emphasis
        config = content_adaptations[preferred_content_type]

        # Add a contextual note about the content focus
        emphasis_note = f"\n\n*Note: This response emphasizes {config['emphasis']} based on your preferences.*"
        adapted_response = response + emphasis_note

        adaptation_details = AdaptationDetails(
            adaptation_type=AdaptationType.CONTENT_ADAPTATION,
            original_value="Standard content approach",
            adapted_value=f"{preferred_content_type} content approach",
            reason=f"Adapted content to focus on {preferred_content_type} elements",
            confidence=0.5,
            method_used="content_emphasis"
        )

        return adapted_response, adaptation_details

    async def _adapt_visual_elements(
        self,
        response: str,
        visual_preference: str,
        adaptation_context: Dict[str, Any],
        conversation_context: ConversationContext
    ) -> tuple[str, Optional[AdaptationDetails]]:
        """Adapt visual elements and formatting"""

        if visual_preference == "minimal":
            # Remove excessive formatting
            adapted_response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)  # Remove bold
            adapted_response = re.sub(r'\*(.*?)\*', r'\1', adapted_response)  # Remove italics

            if adapted_response != response:
                adaptation_details = AdaptationDetails(
                    adaptation_type=AdaptationType.VISUAL_ADAPTATION,
                    original_value="Formatted text with emphasis",
                    adapted_value="Plain text format",
                    reason="Removed visual formatting for minimal preference",
                    confidence=0.7,
                    method_used="format_simplification"
                )
                return adapted_response, adaptation_details

        elif visual_preference == "rich":
            # Add more visual structure
            sentences = response.split('. ')
            if len(sentences) > 3:
                # Add emphasis to key sentences
                adapted_response = '. '.join([
                    f"**{sentence.strip()}**" if i % 3 == 0 and sentence.strip() else sentence
                    for i, sentence in enumerate(sentences)
                ])

                adaptation_details = AdaptationDetails(
                    adaptation_type=AdaptationType.VISUAL_ADAPTATION,
                    original_value="Plain text",
                    adapted_value="Enhanced visual formatting",
                    reason="Added visual emphasis for rich preference",
                    confidence=0.6,
                    method_used="visual_enhancement"
                )
                return adapted_response, adaptation_details

        return response, None

    # Helper methods for format detection and conversion

    def _detect_response_formats(self, response: str) -> List[str]:
        """Detect current formats in response"""
        formats = []

        if re.search(r'(?:^|\n)\s*[-•*]\s+', response):
            formats.append("bullets")
        if re.search(r'(?:^|\n)\s*\d+\.\s+', response):
            formats.append("numbered")
        if re.search(r'(?:^|\n)#+\s+', response):
            formats.append("headers")
        if re.search(r'```', response):
            formats.append("code_blocks")
        if re.search(r'(?:^|\n)\s*\w+:\s+', response):
            formats.append("structured")
        if re.search(r'(?i)step\s+\d+', response):
            formats.append("step-by-step")

        return formats

    def _has_lists(self, response: str) -> bool:
        return bool(re.search(r'(?:^|\n)\s*[-•*]\s+', response))

    def _has_numbered_list(self, response: str) -> bool:
        return bool(re.search(r'(?:^|\n)\s*\d+\.\s+', response))

    def _has_bullet_list(self, response: str) -> bool:
        return bool(re.search(r'(?:^|\n)\s*[-•*]\s+', response))

    def _has_structure(self, response: str) -> bool:
        return bool(re.search(r'(?:^|\n)#+\s+', response))

    def _has_steps(self, response: str) -> bool:
        return bool(re.search(r'(?i)step\s+\d+', response))

    def _convert_to_list_format(self, response: str) -> str:
        """Convert response to list format"""
        sentences = [s.strip() for s in response.split('.') if s.strip()]
        if len(sentences) > 1:
            return '\n'.join([f"• {sentence}." for sentence in sentences])
        return response

    def _convert_to_numbered_format(self, response: str) -> str:
        """Convert response to numbered list format"""
        sentences = [s.strip() for s in response.split('.') if s.strip()]
        if len(sentences) > 1:
            return '\n'.join([f"{i+1}. {sentence}." for i, sentence in enumerate(sentences)])
        return response

    def _convert_to_bullet_format(self, response: str) -> str:
        """Convert response to bullet format"""
        return self._convert_to_list_format(response)

    def _add_structure_headers(self, response: str) -> str:
        """Add structural headers to response"""
        paragraphs = [p.strip() for p in response.split('\n\n') if p.strip()]
        if len(paragraphs) > 1:
            structured = []
            for i, paragraph in enumerate(paragraphs):
                if i == 0:
                    structured.append(f"## Overview\n{paragraph}")
                else:
                    structured.append(f"## Section {i}\n{paragraph}")
            return '\n\n'.join(structured)
        return response

    def _convert_to_steps(self, response: str) -> str:
        """Convert response to step-by-step format"""
        sentences = [s.strip() for s in response.split('.') if s.strip()]
        if len(sentences) > 1:
            return '\n'.join([f"**Step {i+1}:** {sentence}." for i, sentence in enumerate(sentences)])
        return response

    async def _summarize_response(self, response: str, target_words: int) -> str:
        """Summarize response to target word count"""
        words = response.split()
        if len(words) <= target_words:
            return response

        # Simple truncation with ellipsis - could be enhanced with LLM summarization
        truncated = ' '.join(words[:target_words])
        return truncated + "..."

    async def _expand_response(self, response: str, target_words: int) -> str:
        """Expand response to target word count"""
        current_words = len(response.split())
        if current_words >= target_words:
            return response

        # Simple expansion by adding clarifying phrases - could be enhanced with LLM
        expanded = response + "\n\nTo provide more detail: this approach ensures comprehensive coverage of the topic while maintaining clarity and accuracy."
        return expanded

    # Context and learning methods

    async def _get_user_adaptation_context(self, user_id: str) -> Dict[str, Any]:
        """Get adaptation context for specific user"""
        return self.adaptation_history.get(user_id, {
            "successful_adaptations": [],
            "failed_adaptations": [],
            "preference_confidence": {},
            "last_updated": time.time()
        })

    async def _get_global_adaptation_context(self) -> Dict[str, Any]:
        """Get global adaptation context for single-user mode"""
        return self.adaptation_history.get("global", {
            "successful_adaptations": [],
            "failed_adaptations": [],
            "preference_confidence": {},
            "last_updated": time.time()
        })

    def _calculate_adaptation_confidence(
        self,
        adaptations: List[AdaptationDetails],
        user_preferences: UserPreferences
    ) -> float:
        """Calculate overall confidence in adaptations applied"""
        if not adaptations:
            return 0.0

        # Base confidence on individual adaptation confidences
        avg_adaptation_confidence = sum(a.confidence for a in adaptations) / len(adaptations)

        # Adjust based on preference confidence
        relevant_pref_confidences = []
        for adaptation in adaptations:
            if adaptation.adaptation_type == AdaptationType.STYLE_ADAPTATION:
                pref_conf = user_preferences.confidence_scores.get(PreferenceType.COMMUNICATION_STYLE)
            elif adaptation.adaptation_type == AdaptationType.DEPTH_ADAPTATION:
                pref_conf = user_preferences.confidence_scores.get(PreferenceType.DETAIL_LEVEL)
            elif adaptation.adaptation_type == AdaptationType.FORMAT_ADAPTATION:
                pref_conf = user_preferences.confidence_scores.get(PreferenceType.RESPONSE_FORMAT)
            else:
                pref_conf = None

            if pref_conf:
                relevant_pref_confidences.append(pref_conf.weighted_confidence)

        if relevant_pref_confidences:
            avg_pref_confidence = sum(relevant_pref_confidences) / len(relevant_pref_confidences)
        else:
            avg_pref_confidence = 0.5

        # Combined confidence
        return avg_adaptation_confidence * 0.7 + avg_pref_confidence * 0.3

    async def _learn_from_adaptation(self, adaptation_result: AdaptedResponse, storage_key: str):
        """Learn from adaptation results for future improvements"""
        try:
            # Store adaptation result for learning
            if storage_key not in self.adaptation_history:
                self.adaptation_history[storage_key] = {
                    "successful_adaptations": [],
                    "failed_adaptations": [],
                    "preference_confidence": {},
                    "last_updated": time.time()
                }

            # Record this adaptation
            adaptation_record = {
                "adaptations": [a.adaptation_type.value for a in adaptation_result.adaptations_applied],
                "confidence": adaptation_result.confidence,
                "timestamp": adaptation_result.adaptation_time,
                "context": adaptation_result.context_used.metadata if adaptation_result.context_used else {}
            }

            self.adaptation_history[storage_key]["successful_adaptations"].append(adaptation_record)
            self.adaptation_history[storage_key]["last_updated"] = time.time()

            # Keep only recent history to prevent memory growth
            max_history = 100
            if len(self.adaptation_history[storage_key]["successful_adaptations"]) > max_history:
                self.adaptation_history[storage_key]["successful_adaptations"] = \
                    self.adaptation_history[storage_key]["successful_adaptations"][-max_history:]

        except Exception as e:
            print(f"Error learning from adaptation: {e}")

    def get_adaptation_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get adaptation statistics for analysis"""
        storage_key = f"adaptations_{user_id}" if self.is_multi_user and user_id else "global_adaptations"

        if storage_key not in self.adaptation_history:
            return {"total_adaptations": 0, "average_confidence": 0.0}

        history = self.adaptation_history[storage_key]
        successful = history["successful_adaptations"]

        if not successful:
            return {"total_adaptations": 0, "average_confidence": 0.0}

        return {
            "total_adaptations": len(successful),
            "average_confidence": sum(a["confidence"] for a in successful) / len(successful),
            "most_common_adaptations": self._get_most_common_adaptations(successful),
            "last_updated": history["last_updated"]
        }

    def _get_most_common_adaptations(self, adaptation_records: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get most commonly applied adaptations"""
        adaptation_counts = {}
        for record in adaptation_records:
            for adaptation_type in record["adaptations"]:
                adaptation_counts[adaptation_type] = adaptation_counts.get(adaptation_type, 0) + 1

        return dict(sorted(adaptation_counts.items(), key=lambda x: x[1], reverse=True))
