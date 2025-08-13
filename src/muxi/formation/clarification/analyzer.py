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
        style: Optional[str] = None,
    ) -> InformationAnalysis:
        """
        Analyze request for missing information needs

        Args:
            user_message: The user's original message
            intent: The identified user intent
            available_tools: List of available tool names
            user_context: User's context memory
            style: Optional clarification style/approach to use (e.g., 'conversational', 'technical')

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
                # Pass style parameter for consistency and future extensibility
                # Even though tool analysis doesn't currently use style, this maintains
                # API consistency and prepares for future tone adaptation in tool flows
                tool_analysis = await self.analyze_tool_requirements(
                    potential_tool, {}, user_context, style
                )
                missing_info.extend(tool_analysis.missing_required_params)
                available_info.update(tool_analysis.available_info)
                confidence_scores.update(tool_analysis.confidence_scores)
                suggestions.extend(tool_analysis.suggestions)
            else:
                # Analyze as reasoning request
                reasoning_analysis = await self.analyze_reasoning_requirements(
                    intent, user_message, user_context, style
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
        self,
        tool_name: str,
        provided_params: Dict[str, Any],
        user_context: Dict[str, Any],
        style: Optional[str] = None,
    ) -> ToolInformationAnalysis:
        """
        Analyze tool-specific parameter requirements

        Args:
            tool_name: Name of the tool being analyzed
            provided_params: Parameters already provided by user
            user_context: User's context memory
            style: Optional clarification style (currently unused but maintained for API consistency)

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
        self,
        intent: str,
        user_message: str,
        user_context: Dict[str, Any],
        style: Optional[str] = None,
    ) -> ReasoningInformationAnalysis:
        """
        Analyze information needed for effective reasoning/advice

        Args:
            intent: The user's identified intent
            user_message: Original user message
            user_context: User's context memory
            style: Optional clarification style/approach to use (e.g., 'conversational', 'technical')

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
                context_gaps = await self._analyze_generic_context_needs(
                    user_message, user_context, style
                )
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

    def _needs_basic_clarification(self, user_message: str) -> bool:
        """
        Check if a message needs basic clarification based on simple heuristics.

        Returns True if the message is very short or ends with a dangling preposition.

        Args:
            user_message: The user's message to analyze

        Returns:
            bool: True if basic clarification is needed
        """
        message_words = user_message.strip().split()
        return len(message_words) < 3 or user_message.strip().endswith(
            ("with a", "with the", "for a", "for the")
        )

    async def _analyze_generic_context_needs(
        self, user_message: str, user_context: Dict[str, Any], style: Optional[str] = None
    ) -> List[str]:
        """Analyze generic context needs using LLM"""
        context_gaps = []

        # If we have an LLM model, use it to analyze if the request is ambiguous
        if self.model:
            try:
                # Adjust instructions based on style
                style_instructions = {
                    "conversational": "Use a friendly, conversational tone. Ask naturally as if chatting with a colleague.",  # noqa: E501
                    "formal": "Use professional, formal language. Be polite but direct.",
                    "brief": "Be extremely concise. Use minimal words, no pleasantries.",
                }

                style_guidance = style_instructions.get(style, style_instructions["conversational"])

                # Construct messages with proper role separation for better prompt safety and clarity
                # System message contains instructions and cannot be influenced by user input
                system_message = (
                    "You are a request analyzer. Determine if a user message contains a REQUEST that needs action."
                    "\n\nIMPORTANT: The message may contain structured context sections like:"
                    "\n- === CONVERSATION CONTEXT === (contains previous conversation history)"
                    "\n- === CURRENT REQUEST === (contains the actual user request)"
                    "\n- === USER PROFILE === (contains user information)"
                    "\n- === ACTIVE MEMORIES === (contains relevant memory context)"
                    "\n\nWhen these sections are present:"
                    "\n1. Focus on the === CURRENT REQUEST === section for the actual user request"
                    "\n2. Use ALL other sections as available context"
                    "\n3. If information is already provided in ANY section, DO NOT ask for clarification about it"
                    "\n4. Example: If 'order #12345' appears in CONVERSATION CONTEXT, don't ask 'which order?'"
                    "\n\nCRITICAL RULES:"
                    "\n1. INFORMATIONAL STATEMENTS ARE NOT REQUESTS - If the user is just providing context or "
                    "information, return CLEAR"
                    "\n2. Only actual questions or action requests need clarification if incomplete"
                    "\n3. Be VERY conservative - when in doubt, return CLEAR"
                    "\n4. REQUESTS WITH OUTPUT FORMAT INSTRUCTIONS ARE COMPLETE - If user specifies how they want "
                    "the output (e.g., 'as JSON', 'reply with only', 'return as'), the request is CLEAR"
                    "\n5. NEVER ask for clarification about information already present in context sections"
                    "\n\nReturn CLEAR for:"
                    "\n- Any informational statement (e.g., 'I'm working on X', 'My budget is Y')"
                    "\n- Any complete question (e.g., 'What database should I use?')"
                    "\n- Any actionable request with reasonable context"
                    "\n- Any request that specifies output format (e.g., 'reply as JSON', 'return only the code')"
                    "\n- Greetings or social messages (e.g., 'Hi', 'Hello', 'Thanks')"
                    "\n- Any request where needed information exists in the context sections"
                    "\n\nONLY return NEEDS_CLARIFICATION if:"
                    "\n- The message is an incomplete question or request"
                    "\n- The message asks for action but critical details are missing AND not in context"
                    "\n- The message is grammatically broken AND appears to be a request"
                    "\n\nResponse format:"
                    "\nCLEAR (for statements, complete questions, or actionable requests)"
                    "\nNEEDS_CLARIFICATION: [short question] (only for incomplete requests)"
                    "\n\nExamples that MUST return CLEAR:"
                    '\n- "I\'m working on an e-commerce platform using React and Node.js" -> CLEAR '
                    '(informational statement)'
                    '\n- "Hi" -> CLEAR (greeting)'
                    '\n- "I\'m a software developer" -> CLEAR (informational statement)'
                    '\n- "My budget is $5000 and timeline is 2 weeks" -> CLEAR (informational statement)'
                    '\n- "What database should I use?" -> CLEAR (complete question)'
                    '\n- "create a linear issue with system usage info" -> CLEAR (actionable request)'
                    '\n- "Write a Python function to sort a list" -> CLEAR (actionable request)'
                    '\n- "Get system info and return as JSON" -> CLEAR (has output format)'
                    '\n- "Create an issue. Reply with JSON only" -> CLEAR (has output format)'
                    "\n\nExamples that need clarification:"
                    '\n- "can you help me with" -> NEEDS_CLARIFICATION: What would you like help with?'
                    '\n- "fix the" -> NEEDS_CLARIFICATION: What needs to be fixed?'
                    '\n- "create a" -> NEEDS_CLARIFICATION: What would you like me to create?'
                    f"\n\n{style_guidance}"
                    "\n\nREMEMBER: Requests with output format instructions are COMPLETE and should return CLEAR."
                )

                # Separate user message to prevent prompt injection and improve clarity
                # User input is isolated and cannot modify the system instructions
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ]
                response = await self.model.chat(messages, max_tokens=100, temperature=0.3)

                # Extract the actual content from the response
                if response:
                    # Handle different response formats
                    if isinstance(response, str):
                        content = response
                    elif hasattr(response, 'content'):
                        content = response.content
                    elif isinstance(response, dict) and 'content' in response:
                        content = response['content']
                    elif isinstance(response, dict) and 'choices' in response:
                        # Handle OpenAI-style response
                        content = response['choices'][0]['message']['content']
                    else:
                        # Fallback to string conversion
                        content = str(response)

                    # Normalize and check for clarification need
                    normalized_content = content.strip().upper() if content else ""
                    if "NEEDS_CLARIFICATION:" in normalized_content:
                        # Extract the clarification question (case-insensitive split)
                        parts = content.split("NEEDS_CLARIFICATION:", 1)
                        if len(parts) > 1:
                            clarification_question = parts[1].strip()
                            context_gaps.append(clarification_question)

            except Exception:
                # If LLM fails, fall back to simple heuristic
                if self._needs_basic_clarification(user_message):
                    context_gaps.append("specific_details")
        else:
            # No LLM available - only catch obviously incomplete messages
            if self._needs_basic_clarification(user_message):
                context_gaps.append("specific_details")

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
