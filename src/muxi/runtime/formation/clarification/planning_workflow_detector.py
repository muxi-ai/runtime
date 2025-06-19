"""
Planning Workflow Detection for Phase 4B

Detects implicit planning requests that include information gathering components.
Identifies scenarios where users want to make decisions but need data first.
Uses pure LLM detection for multilingual support.
"""

from typing import Optional

from ...datatypes.clarification import PlanningWorkflowRequest, PlanningWorkflowType, ClarificationContext


class PlanningWorkflowDetector:
    """
    Detects implicit planning workflows in user messages using pure LLM analysis.

    Identifies patterns like:
    - "I want to X. Can you check Y and Z?"
    - "Help me choose X. Research Y first."
    - "Book/Buy/Plan X. Find information about Y."

    Supports all languages through LLM understanding.
    """

    def __init__(self, model=None):
        """
        Initialize planning workflow detector.

        Args:
            model: Required AI model for planning workflow detection.
                   If None, all detection attempts will return None.
        """
        self.model = model
        if not model:
            #  Warning - TODO: add observability
            _ = None  # remove this after implementing observability
            #     "PlanningWorkflowDetector initialized without model - "
            #     "all detection will fail"
            # )

    async def detect(
        self, message: str, context: Optional[ClarificationContext] = None
    ) -> Optional[PlanningWorkflowRequest]:
        """
        Detect if a message contains a planning workflow request using LLM analysis.

        Args:
            message: User's message to analyze (any language)
            context: Optional clarification context for additional signals

        Returns:
            PlanningWorkflowRequest if detected, None otherwise
        """
        if not self.model:
            #  Debug - TODO: add observability
            return None

        try:
            #  Debug - TODO: add observability

            # Use pure LLM detection for multilingual support
            workflow_request = await self._detect_with_llm(message, context)

            if workflow_request:
                #  Info - TODO: add observability
                _ = None  # remove this after implementing observability
                #     f"Detected planning workflow: {workflow_request.workflow_type} "
                #     f"(confidence: {workflow_request.confidence})"
                # )

            return workflow_request

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            return None

    async def _detect_with_llm(
        self, message: str, context: Optional[ClarificationContext] = None
    ) -> Optional[PlanningWorkflowRequest]:
        """Use LLM model for comprehensive planning workflow detection"""

        # Prepare context information if available
        context_info = ""
        if context:
            if context.user_context:
                context_info = f"\nUser context: {context.user_context}"
            if context.conversation_history:
                recent_messages = context.conversation_history[-3:]  # Last 3 messages
                context_info += f"\nRecent conversation: {recent_messages}"

        prompt = f"""
        Analyze this user message to determine if it represents a planning workflow request.

        A planning workflow request has these characteristics:
        1. User wants to make a decision or plan something (book, buy, choose, invest, etc.)
        2. User needs information gathered first (research, checking, comparing data)
        3. User expects follow-up questions or guidance after getting the information
        4. The request implies future planning conversation beyond just getting data

        Examples across languages:
        - English: "I want to book a trip to New York in August. Can you check weather and fares?"
        - Spanish: "Quiero reservar un viaje a Nueva York en agosto.
          ¿Puedes verificar el clima y las tarifas?"
        - French: "Je veux réserver un voyage à New York en août.
          Peux-tu vérifier la météo et les tarifs?"
        - German: "Ich möchte eine Reise nach New York im August buchen.
          Können Sie Wetter und Tarife prüfen?"

        Message to analyze: "{message}"{context_info}

        Respond with JSON only:
        {{
            "is_planning_workflow": boolean,
            "workflow_type": "travel_planning|investment_planning|business_planning|product_selection|event_planning|general_planning",
            "planning_goal": "brief description of what user wants to plan/decide",
            "information_requests": ["list", "of", "information", "user", "needs"],
            "detected_tools": ["list", "of", "likely", "tools", "needed"],
            "context_hints": {{
                "locations": ["if", "any", "mentioned"],
                "timeframes": ["if", "any", "mentioned"],
                "budget_mentions": ["if", "any", "mentioned"]
            }},
            "confidence": 0.0-1.0,
            "reasoning": "brief explanation of why this is/isn't a planning workflow"
        }}

        Only detect true planning workflows where user expects continued planning conversation.
        Minimum confidence threshold: 0.6
        """

        try:
            response = await self.model.generate(prompt, temperature=0.1, max_tokens=500)

            # Parse LLM response
            import json

            result = json.loads(response.strip())

            if result.get("is_planning_workflow") and result.get("confidence", 0) >= 0.6:
                workflow_type_map = {
                    "travel_planning": PlanningWorkflowType.TRAVEL_PLANNING,
                    "investment_planning": PlanningWorkflowType.INVESTMENT_PLANNING,
                    "business_planning": PlanningWorkflowType.BUSINESS_PLANNING,
                    "product_selection": PlanningWorkflowType.PRODUCT_SELECTION,
                    "event_planning": PlanningWorkflowType.EVENT_PLANNING,
                    "general_planning": PlanningWorkflowType.GENERAL_PLANNING,
                }

                workflow_type = workflow_type_map.get(
                    result.get("workflow_type"), PlanningWorkflowType.GENERAL_PLANNING
                )

                return PlanningWorkflowRequest(
                    workflow_type=workflow_type,
                    planning_goal=result.get("planning_goal", ""),
                    information_requests=result.get("information_requests", []),
                    original_message=message,
                    detected_tools=result.get("detected_tools", []),
                    context_hints=result.get("context_hints", {}),
                    confidence=result.get("confidence", 0.6),
                )
            else:
                #  Debug - TODO: add observability
                _ = None  # remove this after implementing observability
                #     f"Planning workflow not detected. "
                #     f"Reasoning: {result.get('reasoning', 'No reasoning provided')}"
                # )

        except Exception as e:
            #  Warning - TODO: add observability
            _ = e  # remove this after implementing observability

        return None
