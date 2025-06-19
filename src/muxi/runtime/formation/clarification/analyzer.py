"""
Information analyzer for detecting missing information requirements.

This module analyzes requests and detects missing information for both tools and reasoning,
as specified in the intelligent parameter collection implementation plan.
"""

from typing import Dict, List, Optional, Any

from ...datatypes.clarification import (
    InformationAnalysis,
    ToolInformationAnalysis,
    ReasoningInformationAnalysis,
    InformationAnalysisError,
)


class InformationAnalyzer:
    """Analyzes requests and detects missing information for tools and reasoning"""

    def __init__(self, model=None):
        """
        Initialize the analyzer with an optional model for intent analysis

        Args:
            model: LLM model for analyzing user intent and context needs
        """
        self.model = model
        self._intent_cache = {}

    async def analyze_request(
        self,
        user_message: str,
        intent: str,
        available_tools: List[str],
        user_context: Dict[str, Any],
    ) -> InformationAnalysis:
        """
        Analyze request for missing information needs

        Args:
            user_message: The user's original message
            intent: The identified user intent
            available_tools: List of available tool names
            user_context: User's context memory

        Returns:
            InformationAnalysis with missing info, suggestions, and confidence
        """
        try:
            #  Info - TODO: add observability

            missing_info = []
            available_info = {}
            confidence_scores = {}
            suggestions = []
            reasoning_context_needed = None

            # Check if this looks like a tool-oriented request
            potential_tool = await self._identify_potential_tool(user_message, available_tools)

            if potential_tool:
                # Analyze as tool request
                tool_analysis = await self.analyze_tool_requirements(
                    potential_tool, {}, user_context
                )
                missing_info.extend(tool_analysis.missing_required_params)
                available_info.update(tool_analysis.available_info)
                confidence_scores.update(tool_analysis.confidence_scores)
                suggestions.extend(tool_analysis.suggestions)
            else:
                # Analyze as reasoning request
                reasoning_analysis = await self.analyze_reasoning_requirements(
                    intent, user_message, user_context
                )
                missing_info.extend(reasoning_analysis.context_gaps)
                available_info.update(reasoning_analysis.available_info)
                confidence_scores.update(reasoning_analysis.confidence_scores)
                suggestions.extend(reasoning_analysis.suggestions)
                reasoning_context_needed = reasoning_analysis.reasoning_context_needed

            can_proceed = len(missing_info) == 0 or all(
                confidence_scores.get(info, 0.0) > 0.7 for info in missing_info
            )

            return InformationAnalysis(
                missing_info=missing_info,
                available_info=available_info,
                confidence_scores=confidence_scores,
                suggestions=suggestions,
                can_proceed=can_proceed,
                reasoning_context_needed=reasoning_context_needed,
            )

        except Exception as e:
            #  Error - TODO: add observability
            raise InformationAnalysisError(f"Failed to analyze request: {e}")

    async def analyze_tool_requirements(
        self, tool_name: str, provided_params: Dict[str, Any], user_context: Dict[str, Any]
    ) -> ToolInformationAnalysis:
        """
        Analyze tool-specific parameter requirements

        Args:
            tool_name: Name of the tool being analyzed
            provided_params: Parameters already provided by user
            user_context: User's context memory

        Returns:
            ToolInformationAnalysis with missing parameters and confidence scores
        """
        try:
            #  Info - TODO: add observability

            # Get tool schema (this would typically come from MCP service)
            tool_schema = await self._get_tool_schema(tool_name)

            missing_required = []
            missing_optional = []
            parameter_confidence = {}
            available_info = {}

            # Check required parameters
            required_params = tool_schema.get("required", [])
            for param in required_params:
                if param not in provided_params:
                    # Try to find in user context
                    context_value = self._find_in_context(param, user_context)
                    if context_value:
                        available_info[param] = context_value
                        parameter_confidence[param] = 0.8
                    else:
                        missing_required.append(param)
                        parameter_confidence[param] = 0.0

            # Check optional parameters
            all_params = tool_schema.get("properties", {}).keys()
            for param in all_params:
                if param not in required_params and param not in provided_params:
                    context_value = self._find_in_context(param, user_context)
                    if context_value:
                        available_info[param] = context_value
                        parameter_confidence[param] = 0.6
                    else:
                        missing_optional.append(param)

            suggestions = self._generate_tool_suggestions(tool_name, missing_required)

            return ToolInformationAnalysis(
                tool_name=tool_name,
                tool_schema=tool_schema,
                missing_required_params=missing_required,
                missing_optional_params=missing_optional,
                parameter_confidence=parameter_confidence,
                missing_info=missing_required + missing_optional,
                available_info=available_info,
                confidence_scores=parameter_confidence,
                suggestions=suggestions,
                can_proceed=len(missing_required) == 0,
            )

        except Exception as e:
            #  Error - TODO: add observability
            raise InformationAnalysisError(f"Failed to analyze tool requirements: {e}")

    async def analyze_reasoning_requirements(
        self, intent: str, user_message: str, user_context: Dict[str, Any]
    ) -> ReasoningInformationAnalysis:
        """
        Analyze information needed for effective reasoning/advice

        Args:
            intent: The user's identified intent
            user_message: Original user message
            user_context: User's context memory

        Returns:
            ReasoningInformationAnalysis with context gaps and requirements
        """
        try:
            #  Info - TODO: add observability

            context_gaps = []
            user_background_needed = []
            complexity_level = "simple"

            # Analyze based on intent category
            if "investment" in intent.lower() or "financial" in intent.lower():
                context_gaps, user_background_needed = self._analyze_financial_intent(user_context)
                complexity_level = "complex"
            elif "technical" in intent.lower() or "explain" in intent.lower():
                context_gaps, user_background_needed = self._analyze_explanation_intent(
                    user_message, user_context
                )
                complexity_level = "moderate"
            elif "recommendation" in intent.lower() or "advice" in intent.lower():
                context_gaps, user_background_needed = self._analyze_advice_intent(
                    user_message, user_context
                )
                complexity_level = "moderate"
            else:
                # Generic analysis
                context_gaps = self._analyze_generic_context_needs(user_message, user_context)
                complexity_level = "simple"

            available_info = self._extract_available_context(user_context, context_gaps)
            confidence_scores = {gap: 0.0 for gap in context_gaps}
            suggestions = self._generate_reasoning_suggestions(intent, context_gaps)

            return ReasoningInformationAnalysis(
                intent=intent,
                context_gaps=context_gaps,
                user_background_needed=user_background_needed,
                complexity_level=complexity_level,
                missing_info=context_gaps + user_background_needed,
                available_info=available_info,
                confidence_scores=confidence_scores,
                suggestions=suggestions,
                can_proceed=len(context_gaps) == 0,
                reasoning_context_needed=f"Need context for {intent} advice",
            )

        except Exception as e:
            #  Error - TODO: add observability
            raise InformationAnalysisError(f"Failed to analyze reasoning requirements: {e}")

    async def enrich_with_context(
        self, missing_info: List[str], user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fill missing information from user context where possible

        Args:
            missing_info: List of missing information items
            user_context: User's context memory

        Returns:
            Dictionary of information that could be filled from context
        """
        enriched_info = {}

        for info_item in missing_info:
            context_value = self._find_in_context(info_item, user_context)
            if context_value:
                enriched_info[info_item] = context_value

        return enriched_info

    # Private helper methods

    async def _identify_potential_tool(
        self, user_message: str, available_tools: List[str]
    ) -> Optional[str]:
        """Identify if the message suggests using a specific tool"""
        message_lower = user_message.lower()

        # Simple keyword matching (in production, this would use LLM analysis)
        tool_keywords = {
            "book": ["book", "reserve", "schedule"],
            "search": ["search", "find", "lookup"],
            "weather": ["weather", "forecast", "temperature"],
            "calendar": ["calendar", "meeting", "appointment"],
            "email": ["email", "send", "message"],
        }

        for tool in available_tools:
            tool_lower = tool.lower()
            if tool_lower in message_lower:
                return tool

            # Check keywords
            keywords = tool_keywords.get(tool_lower, [])
            if any(keyword in message_lower for keyword in keywords):
                return tool

        return None

    async def _get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """Get tool schema - in production this would come from MCP service"""
        # Mock schemas for common tools
        schemas = {
            "book_restaurant": {
                "properties": {
                    "location": {"type": "string", "description": "City or area"},
                    "date": {"type": "string", "description": "Date for reservation"},
                    "time": {"type": "string", "description": "Time for reservation"},
                    "party_size": {"type": "integer", "description": "Number of people"},
                    "cuisine": {"type": "string", "description": "Type of cuisine"},
                },
                "required": ["location", "date", "time", "party_size"],
            },
            "book_flight": {
                "properties": {
                    "departure": {"type": "string", "description": "Departure location"},
                    "destination": {"type": "string", "description": "Destination location"},
                    "departure_date": {"type": "string", "description": "Departure date"},
                    "return_date": {"type": "string", "description": "Return date"},
                    "passengers": {"type": "integer", "description": "Number of passengers"},
                },
                "required": ["departure", "destination", "departure_date", "passengers"],
            },
        }

        return schemas.get(tool_name, {"properties": {}, "required": []})

    def _find_in_context(self, param_name: str, user_context: Dict[str, Any]) -> Optional[Any]:
        """Find parameter value in user context"""
        # Direct match
        if param_name in user_context:
            return self._extract_context_value(user_context[param_name])

        # Parameter mappings
        mappings = {
            "location": ["city", "current_location", "location", "address"],
            "date": ["preferred_date", "date", "when"],
            "time": ["preferred_time", "time", "when"],
            "party_size": ["group_size", "people", "party_size"],
            "cuisine": ["favorite_cuisine", "cuisine_preference", "food_preference"],
        }

        possible_keys = mappings.get(param_name, [param_name])
        for key in possible_keys:
            if key in user_context:
                return self._extract_context_value(user_context[key])

        return None

    def _extract_context_value(self, context_item: Any) -> Any:
        """Extract value from context item structure"""
        if isinstance(context_item, dict):
            return context_item.get("value", context_item)
        return context_item

    def _analyze_financial_intent(self, user_context: Dict[str, Any]) -> tuple:
        """Analyze financial advice context needs"""
        context_gaps = []
        background_needed = []

        if "risk_tolerance" not in user_context:
            context_gaps.append("risk_tolerance")
        if "investment_timeline" not in user_context:
            context_gaps.append("investment_timeline")
        if "financial_goals" not in user_context:
            context_gaps.append("financial_goals")
        if "current_portfolio" not in user_context:
            background_needed.append("current_portfolio")
        if "income_level" not in user_context:
            background_needed.append("income_level")

        return context_gaps, background_needed

    def _analyze_explanation_intent(self, user_message: str, user_context: Dict[str, Any]) -> tuple:
        """Analyze explanation context needs"""
        context_gaps = []
        background_needed = []

        if "technical_background" not in user_context:
            background_needed.append("technical_background")
        if "experience_level" not in user_context:
            background_needed.append("experience_level")
        if "specific_interest" not in user_context:
            context_gaps.append("specific_interest")

        return context_gaps, background_needed

    def _analyze_advice_intent(self, user_message: str, user_context: Dict[str, Any]) -> tuple:
        """Analyze advice context needs"""
        context_gaps = []
        background_needed = []

        if "goals" not in user_context:
            context_gaps.append("goals")
        if "constraints" not in user_context:
            context_gaps.append("constraints")
        if "preferences" not in user_context:
            background_needed.append("preferences")

        return context_gaps, background_needed

    def _analyze_generic_context_needs(
        self, user_message: str, user_context: Dict[str, Any]
    ) -> List[str]:
        """Analyze generic context needs"""
        # Basic analysis for generic requests
        context_gaps = []

        if len(user_message.split()) < 5:  # Very brief message
            context_gaps.append("more_details")

        return context_gaps

    def _extract_available_context(
        self, user_context: Dict[str, Any], context_gaps: List[str]
    ) -> Dict[str, Any]:
        """Extract available context information"""
        available = {}
        for gap in context_gaps:
            value = self._find_in_context(gap, user_context)
            if value:
                available[gap] = value
        return available

    def _generate_tool_suggestions(self, tool_name: str, missing_params: List[str]) -> List[str]:
        """Generate suggestions for missing tool parameters"""
        suggestions = []
        for param in missing_params:
            suggestions.append(f"Please provide {param} for {tool_name}")
        return suggestions

    def _generate_reasoning_suggestions(self, intent: str, context_gaps: List[str]) -> List[str]:
        """Generate suggestions for reasoning context gaps"""
        suggestions = []
        for gap in context_gaps:
            suggestions.append(f"Need {gap} to provide better {intent} advice")
        return suggestions

    async def analyze_tool_call(
        self,
        tool_name: str,
        provided_params: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
        user_context: Dict[str, Any],
    ) -> ToolInformationAnalysis:
        """
        Analyze a specific tool call for missing information.

        Args:
            tool_name: Name of the tool being called
            provided_params: Parameters provided in the tool call
            available_tools: List of available tools with their schemas
            user_context: User context for enrichment

        Returns:
            ToolInformationAnalysis with validation results
        """
        # Find the tool schema
        tool_schema = None
        for tool in available_tools:
            if tool.get("name") == tool_name:
                tool_schema = tool
                break

        if not tool_schema:
            # Tool not found - assume it can proceed
            return ToolInformationAnalysis(
                missing_info=[],
                available_info=provided_params,
                confidence_scores={},
                suggestions=[],
                can_proceed=True,
                tool_name=tool_name,
                tool_schema={},
                missing_required_params=[],
                missing_optional_params=[],
                parameter_confidence={},
            )

        # Get tool requirements
        required_params = tool_schema.get("parameters", {}).get("required", [])
        all_params = tool_schema.get("parameters", {}).get("properties", {})

        # Check for missing required parameters
        missing_required = []
        missing_optional = []
        parameter_confidence = {}

        for param in required_params:
            if param not in provided_params:
                missing_required.append(param)
                parameter_confidence[param] = 0.0
            else:
                parameter_confidence[param] = 1.0

        # Check optional parameters
        for param, param_info in all_params.items():
            if param not in required_params and param not in provided_params:
                missing_optional.append(param)
                parameter_confidence[param] = 0.0
            elif param in provided_params:
                parameter_confidence[param] = 1.0

        # Generate suggestions for missing parameters
        suggestions = []
        for param in missing_required:
            param_info = all_params.get(param, {})
            description = param_info.get("description", f"the {param}")
            suggestions.append(f"Please specify {description}")

        # Can proceed if no missing required parameters
        can_proceed = len(missing_required) == 0

        return ToolInformationAnalysis(
            missing_info=missing_required,
            available_info=provided_params,
            confidence_scores=parameter_confidence,
            suggestions=suggestions,
            can_proceed=can_proceed,
            tool_name=tool_name,
            tool_schema=tool_schema,
            missing_required_params=missing_required,
            missing_optional_params=missing_optional,
            parameter_confidence=parameter_confidence,
        )
