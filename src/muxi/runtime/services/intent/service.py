"""
Intent Detection Service

Unified multilingual intent detection using LLM for all intent classification needs.
Replaces keyword-based detection with language-agnostic LLM-based approach.
"""

import json
import hashlib
import inspect
from typing import Optional

from ...datatypes.intent import (
    IntentType,
    IntentResult,
    IntentDetectionContext,
    QueryType,
)
from ..llm import LLM
from .. import observability
from .cache import IntentCache


class IntentDetectionService:
    """Unified multilingual intent detection using LLM."""

    def __init__(
        self,
        llm_service: Optional[LLM] = None,
        cache_ttl: int = 3600,
        enable_cache: bool = True,
        llm_timeout: float = 30.0,
    ):
        """
        Initialize intent detection service.

        Args:
            llm_service: LLM service for intent detection
            cache_ttl: Cache TTL in seconds (default: 1 hour)
            enable_cache: Whether to enable caching
            llm_timeout: Timeout for LLM calls in seconds (default: 30s)
        """
        # Validate LLM service if provided
        if llm_service is not None:
            # Check if the LLM service has the required async method
            if not hasattr(llm_service, "generate_text"):
                raise ValueError("Provided llm_service must have a 'generate_text' method")
            # Check if generate_text is a coroutine function (async)
            if not inspect.iscoroutinefunction(llm_service.generate_text):
                raise ValueError(
                    "The 'generate_text' method of llm_service must be an async method"
                )

        self.llm = llm_service
        self.cache = IntentCache(ttl=cache_ttl) if enable_cache else None
        self.llm_timeout = llm_timeout

        # Prompt templates for different intent types
        self.prompts = {
            IntentType.QUERY_TYPE: self._get_query_type_prompt,
            IntentType.CLARIFICATION_CATEGORY: self._get_clarification_prompt,
            IntentType.SCHEDULE_TYPE: self._get_schedule_type_prompt,
            IntentType.CONTENT_CATEGORY: self._get_content_category_prompt,
            IntentType.ERROR_TYPE: self._get_error_type_prompt,
            IntentType.LEARNING_INTENT: self._get_learning_intent_prompt,
            IntentType.PROACTIVE_REQUEST: self._get_proactive_request_prompt,
            IntentType.MESSAGE_TYPE: self._get_message_type_prompt,
        }

    async def detect_intent(
        self, text: str, intent_type: IntentType, context: Optional[IntentDetectionContext] = None
    ) -> IntentResult:
        """
        Detect intent for any text in any language.

        Args:
            text: Text to analyze
            intent_type: Type of intent to detect
            context: Optional context for detection

        Returns:
            IntentResult with detected intent
        """
        if not self.llm:
            # Fallback to simple detection if no LLM available
            return self._fallback_detection(text, intent_type, context)

        # Check cache
        cache_key = self._get_cache_key(text, intent_type, context)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                observability.observe(
                    event_type=observability.SystemEvents.SERVICE_STARTED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "service": "intent_detection",
                        "action": "cache_hit",
                        "intent_type": intent_type.value,
                        "cache_key": cache_key[:16] + "...",
                    },
                    description="Intent detection cache hit",
                )
                return cached

        # Use LLM for detection
        try:
            result = await self._detect_with_llm(text, intent_type, context)

            # Cache result
            if self.cache and result.confidence > 0.7:  # Only cache confident results
                self.cache.set(cache_key, result)

            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "service": "intent_detection",
                    "intent_type": intent_type.value,
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "text_length": len(text),
                },
                description=f"Intent detected: {result.intent} ({result.confidence:.2f})",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "intent_type": intent_type.value,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "component": "intent_detection",
                },
                description=f"Intent detection failed: {str(e)}",
            )
            # Return fallback result
            return self._fallback_detection(text, intent_type, context)

    async def _detect_with_llm(
        self, text: str, intent_type: IntentType, context: Optional[IntentDetectionContext] = None
    ) -> IntentResult:
        """Use LLM to detect intent."""
        # Get appropriate prompt
        prompt_func = self.prompts.get(intent_type)
        if not prompt_func:
            raise ValueError(f"No prompt template for intent type: {intent_type}")

        prompt = prompt_func(text, context)

        # Call LLM
        response = await self.llm.generate_text(
            prompt=prompt,
            temperature=0.1,  # Low temperature for consistent classification
            max_tokens=200,
            timeout=self.llm_timeout,
        )

        # Parse response
        try:
            result_data = json.loads(response)

            # Map to appropriate enum if needed
            intent_value = result_data.get("intent", "unknown")
            if intent_type == IntentType.QUERY_TYPE:
                intent_value = self._normalize_query_type(intent_value)
            elif intent_type == IntentType.CLARIFICATION_CATEGORY:
                intent_value = self._normalize_clarification_category(intent_value)
            elif intent_type == IntentType.SCHEDULE_TYPE:
                intent_value = self._normalize_schedule_type(intent_value)

            return IntentResult(
                intent_type=intent_type,
                intent=intent_value,
                confidence=float(result_data.get("confidence", 0.5)),
                reasoning=result_data.get("reasoning"),
                metadata=result_data.get("metadata", {}),
                extracted_question=result_data.get("extracted_question"),
                alternatives=[
                    {"intent": alt, "confidence": conf}
                    for alt, conf in result_data.get("alternatives", {}).items()
                ],
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # If parsing fails, return low confidence result
            return IntentResult(
                intent_type=intent_type,
                intent="unclear",
                confidence=0.3,
                reasoning=f"Failed to parse LLM response: {str(e)}",
                metadata={"raw_response": response},
            )

    def _get_cache_key(
        self, text: str, intent_type: IntentType, context: Optional[IntentDetectionContext] = None
    ) -> str:
        """Generate cache key for intent detection."""
        # Create stable hash
        key_parts = [
            text.lower().strip(),
            intent_type.value,
        ]

        if context:
            if context.options:
                key_parts.append(",".join(sorted(context.options)))
            if context.user_language:
                key_parts.append(context.user_language)

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _fallback_detection(
        self, text: str, intent_type: IntentType, context: Optional[IntentDetectionContext] = None
    ) -> IntentResult:
        """Simple fallback detection when LLM is not available."""
        # Basic heuristics as fallback
        text_lower = text.lower().strip()

        if intent_type == IntentType.QUERY_TYPE:
            # Simple knowledge vs memory detection
            if any(
                word in text_lower for word in ["remember", "last time", "previously", "you said"]
            ):
                return IntentResult(
                    intent_type=intent_type,
                    intent=QueryType.MEMORY,
                    confidence=0.6,
                    reasoning="Fallback: Found memory-related keywords",
                )
            else:
                return IntentResult(
                    intent_type=intent_type,
                    intent=QueryType.KNOWLEDGE,
                    confidence=0.5,
                    reasoning="Fallback: Default to knowledge query",
                )

        # For other types, return unclear with low confidence
        return IntentResult(
            intent_type=intent_type,
            intent="unclear",
            confidence=0.2,
            reasoning="Fallback: LLM not available",
        )

    # Prompt template methods
    def _get_query_type_prompt(self, text: str, context: Optional[IntentDetectionContext]) -> str:
        """Get prompt for query type detection."""
        recent_context = ""
        if context and context.recent_messages:
            recent = "\n".join(
                [
                    f"{msg['role']}: {msg['content'][:100]}..."
                    for msg in context.recent_messages[-3:]
                ]
            )
            recent_context = f"\nRecent conversation:\n{recent}"

        return f"""Analyze this query and determine if it's asking for:
- "knowledge": General information, facts, explanations, how-to guides, definitions, concepts
- "memory": Past conversations, previous interactions, user-specific information, things said before
- "mixed": Contains both knowledge and memory aspects
- "unclear": Cannot determine the type

Query: {text}{recent_context}

Respond with JSON only:
{{
  "intent": "knowledge|memory|mixed|unclear",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of why this classification was chosen"
}}"""

    def _get_clarification_prompt(
        self, text: str, context: Optional[IntentDetectionContext]
    ) -> str:
        """Get prompt for clarification category detection."""
        return f"""Identify which category of information this text is asking about:
- "budget": Cost, price, funding, financial aspects, money
- "timeline": When, deadline, schedule, duration, timeframe
- "preferences": Style, likes, wants, choices, options
- "requirements": Specifications, needs, must-haves, constraints
- "scope": Size, extent, coverage, scale, boundaries
- "location": Where, place, region, area, geography
- "other": Doesn't fit the above categories
- "none": No clarification question detected

Text: {text}

Respond with JSON only:
{{
  "intent": "budget|timeline|preferences|requirements|scope|location|other|none",
  "confidence": 0.0-1.0,
  "extracted_question": "the specific question extracted if found, null otherwise",
  "reasoning": "brief explanation"
}}"""

    def _get_schedule_type_prompt(
        self, text: str, context: Optional[IntentDetectionContext]
    ) -> str:
        """Get prompt for schedule type detection."""
        return f"""Determine if this is a one-time or recurring schedule request:
- "one_time": Specific date/time, next occurrence, single event
- "recurring": Regular pattern, repeating, periodic (daily, weekly, monthly, etc.)
- "unclear": Cannot determine from the text

Text: {text}

Examples across languages:
- One-time: "tomorrow at 3pm", "next Monday", "on December 25th", "mañana a las 3"
- Recurring: "every day", "weekly on Mondays", "tous les jours", "每天"

Respond with JSON only:
{{
  "intent": "one_time|recurring|unclear",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "metadata": {{
    "detected_pattern": "the time pattern found if any"
  }}
}}"""

    def _get_content_category_prompt(
        self, text: str, context: Optional[IntentDetectionContext]
    ) -> str:
        """Get prompt for content category detection."""
        return f"""Categorize this content by its primary purpose:
- "technical": Code, programming, algorithms, technical specifications
- "explanatory": Explaining concepts, answering why/how questions
- "instructional": Step-by-step guides, tutorials, processes
- "conversational": Opinions, feelings, casual discussion
- "mixed": Contains multiple categories

Text: {text}

Respond with JSON only:
{{
  "intent": "technical|explanatory|instructional|conversational|mixed",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "alternatives": {{
    "category_name": confidence_score
  }}
}}"""

    def _get_error_type_prompt(self, text: str, context: Optional[IntentDetectionContext]) -> str:
        """Get prompt for error type detection."""
        return f"""Classify this error message into a category:
- "format": File format, encoding, corruption issues
- "size": File too large, memory limits, quota exceeded
- "permission": Access denied, authentication, forbidden
- "network": Connection failed, timeout, unreachable
- "parsing": Cannot parse, invalid syntax, malformed data
- "memory": Out of memory, allocation failed
- "api": API errors, rate limits, service errors
- "unknown": Cannot classify the error

Error text: {text}

Respond with JSON only:
{{
  "intent": "format|size|permission|network|parsing|memory|api|unknown",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    def _get_learning_intent_prompt(
        self, text: str, context: Optional[IntentDetectionContext]
    ) -> str:
        """Get prompt for learning intent detection."""
        return f"""Determine if this text indicates a learning intent:
- "tutorial": Wants step-by-step guidance
- "explanation": Wants to understand concepts
- "example": Wants practical examples
- "reference": Wants documentation or resources
- "none": No learning intent detected

Text: {text}

Respond with JSON only:
{{
  "intent": "tutorial|explanation|example|reference|none",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    def _get_proactive_request_prompt(
        self, text: str, context: Optional[IntentDetectionContext]
    ) -> str:
        """Get prompt for proactive request detection."""
        return f"""Analyze if this message requests proactive assistance:
- "guided_questioning": Asks for questions/interview to gather information
- "plan_feedback": Presents plan and asks for feedback
- "context_first": Wants understanding before proceeding
- "step_by_step": Requests step-by-step guidance
- "comprehensive_advice": Wants thorough analysis
- "none": No proactive request detected

Text: {text}

Respond with JSON only:
{{
  "intent": "guided_questioning|plan_feedback|context_first|step_by_step|comprehensive_advice|none",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    def _get_message_type_prompt(self, text: str, context: Optional[IntentDetectionContext]) -> str:
        """Get prompt for message type detection."""
        return f"""Classify this message type:
- "request": Asking for something to be done
- "query": Asking for information
- "consultation": Seeking advice or opinion
- "feedback": Providing feedback or response
- "statement": Making a statement or observation
- "other": Doesn't fit above categories

Text: {text}

Respond with JSON only:
{{
  "intent": "request|query|consultation|feedback|statement|other",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

    # Normalization methods
    def _normalize_query_type(self, value: str) -> str:
        """Normalize query type values."""
        value = value.lower().strip()
        if value in ["knowledge", "memory", "mixed", "unclear"]:
            return value
        return "unclear"

    def _normalize_clarification_category(self, value: str) -> str:
        """Normalize clarification category values."""
        value = value.lower().strip()
        valid = [
            "budget",
            "timeline",
            "preferences",
            "requirements",
            "scope",
            "location",
            "other",
            "none",
        ]
        if value in valid:
            return value
        return "other"

    def _normalize_schedule_type(self, value: str) -> str:
        """Normalize schedule type values."""
        value = value.lower().strip()
        if value in ["one_time", "recurring", "unclear"]:
            return value
        return "unclear"
