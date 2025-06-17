"""
Question generator for creating natural clarifying questions.

This module generates natural language clarifying questions for missing information
across different contexts and interaction styles.
"""


import uuid
from typing import Dict, List, Any

from .types import (
    ClarificationQuestion,
    QuestionStyle,
    RequestType,
    QuestionGenerationError
)


class ClarificationQuestionGenerator:
    """Generates natural language clarifying questions for missing information"""

    def __init__(self, model=None):
        """
        Initialize the question generator

        Args:
            model: LLM model for generating natural questions
        """
        self.model = model
        self._question_templates = self._load_question_templates()

    async def generate_question(
        self,
        request_type: RequestType,
        info_name: str,
        info_schema: Dict[str, Any],
        user_context: Dict[str, Any],
        conversation_context: str,
        intent: str,
        style: QuestionStyle = QuestionStyle.CONVERSATIONAL
    ) -> ClarificationQuestion:
        """
        Generate a natural clarifying question for missing information

        Args:
            request_type: Type of request (tool_call, reasoning, mixed)
            info_name: Name of the missing information
            info_schema: Schema/description of the required information
            user_context: User's context memory
            conversation_context: Recent conversation context
            intent: User's primary intent
            style: Question style preference

        Returns:
            ClarificationQuestion with natural language question
        """
        try:
            #  Info - TODO: add observability

            # Determine question approach based on context
            if self.model and await self._should_use_ai_generation(info_name, user_context):
                question_text = await self._generate_ai_question(
                    request_type, info_name, info_schema, user_context,
                    conversation_context, intent, style
                )
            else:
                question_text = self._generate_template_question(
                    request_type, info_name, info_schema, style
                )

            return ClarificationQuestion(
                question_id=str(uuid.uuid4()),
                question_text=question_text,
                parameter_name=info_name,
                parameter_type=info_schema.get("type", "string"),
                parameter_description=info_schema.get("description"),
                required=info_schema.get("required", True),
                validation_rules=info_schema.get("validation"),
                context_hints=self._generate_context_hints(info_name, user_context),
                style=style
            )

        except Exception as e:
            #  Error - TODO: add observability
            raise QuestionGenerationError(f"Failed to generate question: {e}")

    async def generate_clarification_plan(
        self,
        request_type: RequestType,
        intent: str,
        missing_info: List[str],
        info_requirements: Dict[str, Any],
        user_context: Dict[str, Any],
        style: QuestionStyle = QuestionStyle.CONVERSATIONAL
    ) -> List[ClarificationQuestion]:
        """
        Generate a complete question sequence for all missing information

        Args:
            request_type: Type of clarification request
            intent: User's primary intent
            missing_info: List of missing information items
            info_requirements: Requirements/schemas for each info item
            user_context: User's context memory
            style: Question style preference

        Returns:
            List of ClarificationQuestion objects in optimal order
        """
        try:
            #  Info - TODO: add observability

            questions = []

            # Prioritize questions based on importance and dependencies
            prioritized_info = self._prioritize_missing_info(
                missing_info, info_requirements, request_type
            )

            for info_name in prioritized_info:
                info_schema = info_requirements.get(info_name, {})

                question = await self.generate_question(
                    request_type=request_type,
                    info_name=info_name,
                    info_schema=info_schema,
                    user_context=user_context,
                    conversation_context="",  # Will be filled later
                    intent=intent,
                    style=style
                )

                questions.append(question)

            return questions

        except Exception as e:
            #  Error - TODO: add observability
            raise QuestionGenerationError(f"Failed to generate clarification plan: {e}")

    async def generate_reasoning_question(
        self,
        intent: str,
        missing_context: str,
        user_background: Dict[str, Any],
        style: QuestionStyle = QuestionStyle.CONVERSATIONAL
    ) -> ClarificationQuestion:
        """
        Generate questions for reasoning/advice scenarios

        Args:
            intent: User's primary intent
            missing_context: Description of missing context
            user_background: User's background information
            style: Question style preference

        Returns:
            ClarificationQuestion for reasoning context
        """
        try:
            #  Info - TODO: add observability

            if self.model:
                question_text = await self._generate_ai_reasoning_question(
                    intent, missing_context, user_background, style
                )
            else:
                question_text = self._generate_template_reasoning_question(
                    intent, missing_context, style
                )

            return ClarificationQuestion(
                question_id=str(uuid.uuid4()),
                question_text=question_text,
                parameter_name=missing_context,
                parameter_type="context",
                parameter_description=f"Context needed for {intent}",
                required=True,
                style=style
            )

        except Exception as e:
            #  Error - TODO: add observability
            raise QuestionGenerationError(f"Failed to generate reasoning question: {e}")

    # Private helper methods

    async def _should_use_ai_generation(self, info_name: str, user_context: Dict[str, Any]) -> bool:
        """Determine if AI generation is needed for this question"""
        # Use AI for complex or context-dependent questions
        complex_params = ["preferences", "requirements", "goals", "constraints"]
        return any(param in info_name.lower() for param in complex_params)

    async def _generate_ai_question(
        self,
        request_type: RequestType,
        info_name: str,
        info_schema: Dict[str, Any],
        user_context: Dict[str, Any],
        conversation_context: str,
        intent: str,
        style: QuestionStyle
    ) -> str:
        """Generate question using AI model"""
        if not self.model:
            return self._generate_template_question(request_type, info_name, info_schema, style)

        try:
            prompt = self._build_question_generation_prompt(
                request_type, info_name, info_schema, user_context,
                conversation_context, intent, style
            )

            response = await self.model.generate(prompt, max_tokens=100, temperature=0.7)

            # Extract just the question from the response
            question = response.strip()
            if question.endswith('?'):
                return question
            else:
                return question + "?"

        except Exception as e:
            #  Warning - TODO: add observability
            _ = e  # remove this after implementing observability
            return self._generate_template_question(request_type, info_name, info_schema, style)

    def _generate_template_question(
        self,
        request_type: RequestType,
        info_name: str,
        info_schema: Dict[str, Any],
        style: QuestionStyle
    ) -> str:
        """Generate question using templates"""
        templates = self._question_templates.get(request_type.value, {})
        param_templates = templates.get(info_name, {})

        # Get template for the specified style
        template = param_templates.get(style.value)
        if not template:
            template = param_templates.get(QuestionStyle.CONVERSATIONAL.value)

        if not template:
            # Fallback generic template
            template = self._get_generic_template(info_name, style)

        # Fill in template variables
        description = info_schema.get("description", info_name.replace("_", " "))
        return template.format(
            info_name=info_name,
            description=description,
            parameter=info_name.replace("_", " ")
        )

    async def _generate_ai_reasoning_question(
        self,
        intent: str,
        missing_context: str,
        user_background: Dict[str, Any],
        style: QuestionStyle
    ) -> str:
        """Generate reasoning question using AI"""
        if not self.model:
            return self._generate_template_reasoning_question(intent, missing_context, style)

        try:
            prompt = f"""
            Generate a natural clarifying question to gather context for providing {intent} advice.

            Missing context: {missing_context}
            User background: {user_background}
            Style: {style.value}

            Generate a single, clear question that would help gather the missing context.
            Make it sound {style.value} and helpful.
            """

            response = await self.model.generate(prompt, max_tokens=100, temperature=0.7)
            question = response.strip()

            return question if question.endswith('?') else question + "?"

        except Exception as e:
            #  Warning - TODO: add observability
            _ = e  # remove this after implementing observability
            return self._generate_template_reasoning_question(intent, missing_context, style)

    def _generate_template_reasoning_question(
        self,
        intent: str,
        missing_context: str,
        style: QuestionStyle
    ) -> str:
        """Generate reasoning question using templates"""
        templates = {
            QuestionStyle.CONVERSATIONAL: "I'd be happy to help with {intent}. Could you tell me more about {context}?",
            QuestionStyle.FORMAL: "To provide appropriate {intent} guidance, please provide information about {context}.",
            QuestionStyle.BRIEF: "What's your {context} for {intent}?"
        }

        template = templates.get(style, templates[QuestionStyle.CONVERSATIONAL])
        return template.format(intent=intent, context=missing_context.replace("_", " "))

    def _prioritize_missing_info(
        self,
        missing_info: List[str],
        info_requirements: Dict[str, Any],
        request_type: RequestType
    ) -> List[str]:
        """Prioritize missing information by importance and dependencies"""
        # Define priority order for common parameters
        priority_order = {
            RequestType.TOOL_CALL: [
                "location", "date", "time", "departure", "destination",
                "party_size", "passengers", "cuisine", "preferences"
            ],
            RequestType.REASONING: [
                "goals", "background", "constraints", "preferences",
                "timeline", "budget", "requirements"
            ]
        }

        order = priority_order.get(request_type, [])
        prioritized = []

        # First, add items in priority order
        for item in order:
            if item in missing_info:
                prioritized.append(item)

        # Then add remaining items
        for item in missing_info:
            if item not in prioritized:
                prioritized.append(item)

        return prioritized

    def _generate_context_hints(self, info_name: str, user_context: Dict[str, Any]) -> List[str]:
        """Generate helpful context hints for the question"""
        hints = []

        # Common hints based on parameter type
        hint_map = {
            "location": ["city or area", "specific address or general region"],
            "date": ["format: YYYY-MM-DD", "today, tomorrow, or specific date"],
            "time": ["format: HH:MM", "morning, afternoon, evening, or specific time"],
            "party_size": ["number of people", "just yourself or group size"],
            "cuisine": ["type of food", "Italian, Chinese, Mexican, etc."]
        }

        if info_name in hint_map:
            hints.extend(hint_map[info_name])

        return hints

    def _build_question_generation_prompt(
        self,
        request_type: RequestType,
        info_name: str,
        info_schema: Dict[str, Any],
        user_context: Dict[str, Any],
        conversation_context: str,
        intent: str,
        style: QuestionStyle
    ) -> str:
        """Build prompt for AI question generation"""
        return f"""
        Generate a natural clarifying question to collect missing information.

        Context:
        - Request type: {request_type.value}
        - Missing parameter: {info_name}
        - Parameter description: {info_schema.get('description', 'No description')}
        - User intent: {intent}
        - Question style: {style.value}
        - User context: {user_context}

        Requirements:
        - Ask for {info_name} in a {style.value} way
        - Make it sound natural and helpful
        - Keep it concise but clear
        - End with a question mark

        Generate only the question, nothing else.
        """

    def _get_generic_template(self, info_name: str, style: QuestionStyle) -> str:
        """Get generic template for unknown parameters"""
        templates = {
            QuestionStyle.CONVERSATIONAL: "Could you please provide your {parameter}?",
            QuestionStyle.FORMAL: "Please specify the {parameter}.",
            QuestionStyle.BRIEF: "{parameter}?"
        }
        return templates.get(style, templates[QuestionStyle.CONVERSATIONAL])

    def _load_question_templates(self) -> Dict[str, Any]:
        """Load predefined question templates"""
        return {
            "tool_call": {
                "location": {
                    "conversational": "What city or area would you like me to search in?",
                    "formal": "Please specify the location for your request.",
                    "brief": "Which location?"
                },
                "date": {
                    "conversational": "What date were you thinking?",
                    "formal": "Please provide the desired date.",
                    "brief": "Which date?"
                },
                "time": {
                    "conversational": "What time would work best for you?",
                    "formal": "Please specify the preferred time.",
                    "brief": "What time?"
                },
                "party_size": {
                    "conversational": "How many people will be joining you?",
                    "formal": "Please indicate the number of people.",
                    "brief": "How many people?"
                },
                "cuisine": {
                    "conversational": "What type of cuisine are you in the mood for?",
                    "formal": "Please specify your cuisine preference.",
                    "brief": "Which cuisine?"
                }
            },
            "reasoning": {
                "background": {
                    "conversational": "Could you tell me a bit about your background with this topic?",
                    "formal": "Please provide your relevant background information.",
                    "brief": "Your background?"
                },
                "goals": {
                    "conversational": "What are you hoping to achieve?",
                    "formal": "Please describe your objectives.",
                    "brief": "Your goals?"
                },
                "constraints": {
                    "conversational": "Are there any constraints or limitations I should know about?",
                    "formal": "Please specify any relevant constraints.",
                    "brief": "Any constraints?"
                }
            }
        }
