"""
Contextual parameter enricher for filling missing information from user context.

This module enriches parameters using user context memory to pre-fill
information where possible, reducing the need for clarifying questions.
"""


from typing import Dict, List, Optional, Any, Tuple

from .datatypes import (
    ParameterMapping,
    ContextEnrichmentError
)


class ContextualParameterEnricher:
    """Enriches parameters using user context memory"""

    def __init__(self, overlord):
        """
        Initialize the parameter enricher

        Args:
            overlord: Reference to overlord for accessing user context
        """
        self.overlord = overlord
        self.parameter_mappings = self._initialize_parameter_mappings()
        self.confidence_threshold = 0.6

    async def enrich_parameters(
        self,
        tool_schema: Dict[str, Any],
        provided_params: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """
        Fill missing parameters from user context where possible

        Args:
            tool_schema: Schema definition for the tool
            provided_params: Parameters already provided by user
            user_context: User's context memory

        Returns:
            Tuple of (enriched_params, confidence_scores)
        """
        try:
            #  Info - TODO: add observability

            enriched_params = provided_params.copy()
            confidence_scores = {}

            # Process all parameters in the schema
            for param_name, param_info in tool_schema.get("properties", {}).items():
                if param_name not in enriched_params:
                    # Try to find value in user context
                    context_value, confidence = await self._find_context_value(
                        param_name, param_info, user_context
                    )

                    if context_value is not None and confidence >= self.confidence_threshold:
                        enriched_params[param_name] = context_value
                        confidence_scores[param_name] = confidence
                        #  Info - TODO: add observability

            return enriched_params, confidence_scores

        except Exception as e:
            #  Error - TODO: add observability
            raise ContextEnrichmentError(f"Failed to enrich parameters: {e}")

    async def enrich_reasoning_context(
        self,
        intent: str,
        provided_context: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, float]]:
        """
        Enrich reasoning context with user background and preferences

        Args:
            intent: User's primary intent
            provided_context: Context already provided
            user_context: User's context memory

        Returns:
            Tuple of (enriched_context, confidence_scores)
        """
        try:
            #  Info - TODO: add observability

            enriched_context = provided_context.copy()
            confidence_scores = {}

            # Get relevant context based on intent
            relevant_mappings = self._get_intent_mappings(intent)

            for context_key, mapping in relevant_mappings.items():
                if context_key not in enriched_context:
                    context_value, confidence = await self._find_mapped_value(
                        mapping, user_context
                    )

                    if context_value is not None and confidence >= self.confidence_threshold:
                        enriched_context[context_key] = context_value
                        confidence_scores[context_key] = confidence

            return enriched_context, confidence_scores

        except Exception as e:
            #  Error - TODO: add observability
            raise ContextEnrichmentError(f"Failed to enrich reasoning context: {e}")

    async def learn_parameter_mapping(
        self,
        parameter_name: str,
        user_response: str,
        context_key: str,
        confidence: float
    ) -> None:
        """
        Learn new parameter mapping from successful interactions

        Args:
            parameter_name: Name of the parameter
            user_response: User's response that provided the value
            context_key: Key in user context that should map to this parameter
            confidence: Confidence in this mapping
        """
        try:
            # Update or create parameter mapping
            if parameter_name not in self.parameter_mappings:
                self.parameter_mappings[parameter_name] = ParameterMapping(
                    parameter_name=parameter_name,
                    context_keys=[],
                    confidence_threshold=0.6
                )

            mapping = self.parameter_mappings[parameter_name]

            # Add context key if not already present
            if context_key not in mapping.context_keys:
                mapping.context_keys.append(context_key)
                #  Info - TODO: add observability

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability

    # Private helper methods

    async def _find_context_value(
        self,
        param_name: str,
        param_info: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Tuple[Optional[Any], float]:
        """Find parameter value in user context with confidence score"""

        # Try direct parameter mapping first
        if param_name in self.parameter_mappings:
            mapping = self.parameter_mappings[param_name]
            value, confidence = await self._find_mapped_value(mapping, user_context)
            if value is not None:
                return value, confidence

        # Try direct key match
        if param_name in user_context:
            value = self._extract_context_value(user_context[param_name])
            return value, 0.9

        # Try fuzzy matching
        fuzzy_matches = self._find_fuzzy_matches(param_name, user_context)
        for match_key, similarity in fuzzy_matches:
            if similarity > 0.7:
                value = self._extract_context_value(user_context[match_key])
                return value, similarity

        # Try semantic matching based on parameter description
        semantic_value = await self._find_semantic_match(
            param_name, param_info, user_context
        )
        if semantic_value:
            return semantic_value, 0.7

        return None, 0.0

    async def _find_mapped_value(
        self,
        mapping: ParameterMapping,
        user_context: Dict[str, Any]
    ) -> Tuple[Optional[Any], float]:
        """Find value using parameter mapping"""

        for context_key in mapping.context_keys:
            if context_key in user_context:
                value = self._extract_context_value(user_context[context_key])
                if value is not None:
                    return value, 0.8

        return None, 0.0

    def _extract_context_value(self, context_item: Any) -> Any:
        """Extract value from context item structure"""
        if isinstance(context_item, dict):
            # Handle structured context items
            if "value" in context_item:
                return context_item["value"]
            elif "content" in context_item:
                return context_item["content"]
            else:
                return context_item
        return context_item

    def _find_fuzzy_matches(
        self,
        param_name: str,
        user_context: Dict[str, Any]
    ) -> List[Tuple[str, float]]:
        """Find fuzzy matches for parameter name in context keys"""
        matches = []
        param_words = set(param_name.lower().replace("_", " ").split())

        for context_key in user_context.keys():
            context_words = set(context_key.lower().replace("_", " ").split())

            # Calculate word overlap similarity
            if param_words and context_words:
                overlap = len(param_words.intersection(context_words))
                similarity = overlap / max(len(param_words), len(context_words))

                if similarity > 0.5:
                    matches.append((context_key, similarity))

        # Sort by similarity
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    async def _find_semantic_match(
        self,
        param_name: str,
        param_info: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Optional[Any]:
        """Find semantic matches using parameter description"""

        description = param_info.get("description", "").lower()
        if not description:
            return None

        # Simple semantic matching based on keywords
        semantic_keywords = {
            "location": ["city", "place", "address", "where", "area"],
            "time": ["when", "time", "hour", "schedule"],
            "date": ["when", "day", "date", "schedule"],
            "preference": ["like", "prefer", "favorite", "choice"],
            "goal": ["want", "aim", "objective", "target"],
            "background": ["experience", "history", "expertise", "knowledge"]
        }

        for semantic_type, keywords in semantic_keywords.items():
            if any(keyword in description for keyword in keywords):
                # Look for matching context
                for context_key, context_value in user_context.items():
                    if any(keyword in context_key.lower() for keyword in keywords):
                        return self._extract_context_value(context_value)

        return None

    def _get_intent_mappings(self, intent: str) -> Dict[str, ParameterMapping]:
        """Get relevant parameter mappings for a specific intent"""

        intent_mappings = {
            "investment_advice": {
                "risk_tolerance": ParameterMapping(
                    parameter_name="risk_tolerance",
                    context_keys=["risk_profile", "investment_risk", "risk_tolerance"],
                    confidence_threshold=0.7
                ),
                "investment_timeline": ParameterMapping(
                    parameter_name="investment_timeline",
                    context_keys=["timeline", "investment_horizon", "time_frame"],
                    confidence_threshold=0.7
                ),
                "financial_goals": ParameterMapping(
                    parameter_name="financial_goals",
                    context_keys=["goals", "financial_objectives", "investment_goals"],
                    confidence_threshold=0.7
                )
            },
            "technical_explanation": {
                "technical_background": ParameterMapping(
                    parameter_name="technical_background",
                    context_keys=["background", "expertise", "experience_level"],
                    confidence_threshold=0.8
                ),
                "specific_interest": ParameterMapping(
                    parameter_name="specific_interest",
                    context_keys=["interests", "focus_area", "specialization"],
                    confidence_threshold=0.6
                )
            }
        }

        return intent_mappings.get(intent.lower(), {})

    def _initialize_parameter_mappings(self) -> Dict[str, ParameterMapping]:
        """Initialize default parameter mappings"""
        return {
            "location": ParameterMapping(
                parameter_name="location",
                context_keys=["location", "city", "address", "current_location", "home_city"],
                confidence_threshold=0.7
            ),
            "date": ParameterMapping(
                parameter_name="date",
                context_keys=["preferred_date", "date", "when", "schedule"],
                confidence_threshold=0.7
            ),
            "time": ParameterMapping(
                parameter_name="time",
                context_keys=["preferred_time", "time", "schedule", "when"],
                confidence_threshold=0.7
            ),
            "party_size": ParameterMapping(
                parameter_name="party_size",
                context_keys=["group_size", "people", "party_size", "family_size"],
                confidence_threshold=0.8
            ),
            "cuisine": ParameterMapping(
                parameter_name="cuisine",
                context_keys=["favorite_cuisine", "cuisine_preference", "food_preference"],
                confidence_threshold=0.7
            ),
            "preferences": ParameterMapping(
                parameter_name="preferences",
                context_keys=["preferences", "likes", "dislikes", "style"],
                confidence_threshold=0.6
            ),
            "budget": ParameterMapping(
                parameter_name="budget",
                context_keys=["budget", "price_range", "spending_limit"],
                confidence_threshold=0.8
            )
        }
