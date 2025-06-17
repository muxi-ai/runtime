"""
Proactive Clarification Intent Detector

This module detects when users make explicit requests for proactive questioning,
multi-step planning assistance, or guided information gathering.
Uses pure LLM detection for multilingual support.
"""

from typing import Optional

from .types import ProactiveRequest, ProactiveRequestType, MultiStepPlan


class ProactiveClarificationIntentDetector:
    """Detects explicit turn-taking and proactive questioning requests using pure LLM analysis"""

    def __init__(self, model=None):
        """
        Initialize the proactive intent detector

        Args:
            model: Required LLM model for proactive intent detection.
                   If None, all detection attempts will return None.
        """
        self.model = model
        if not model:
            #  Proactive detector warning - TODO: add observability
            _ = None  # remove this after implementing observability
            #     "ProactiveClarificationIntentDetector initialized without model - "
            #     "all detection will fail"
            # )

    async def detect_proactive_request(self, message: str) -> Optional[ProactiveRequest]:
        """
        Detect if message contains explicit request for proactive clarification using LLM

        Args:
            message: User's message to analyze (any language)

        Returns:
            ProactiveRequest if detected, None otherwise
        """
        if not self.model:
            #  Proactive detector debug - TODO: add observability
            return None

        try:
            #  Proactive detector debug - TODO: add observability

            # Use pure LLM detection for multilingual support
            proactive_request = await self._detect_with_llm(message)

            if proactive_request:
                #  Proactive detector info - TODO: add observability
                return proactive_request

            return None

        except Exception as e:
            #  Proactive detector error - TODO: add observability
            _ = e  # remove this after implementing observability
            return None

    async def _detect_with_llm(self, message: str) -> Optional[ProactiveRequest]:
        """Use LLM model to detect proactive clarification requests"""

        prompt = f"""
        Analyze this user message to determine if it contains an explicit request for
        proactive clarification, guided questioning, or multi-step planning assistance.

        Proactive request types:
        1. GUIDED_QUESTIONING: User explicitly asks for questions/interview to gather info
        2. PLAN_FEEDBACK: User presents a multi-step plan and asks for feedback/thoughts
        3. CONTEXT_FIRST: User asks to understand their situation/background before proceeding
        4. STEP_BY_STEP: User requests step-by-step guidance or walk-through
        5. COMPREHENSIVE_ADVICE: User asks for thorough analysis with multiple considerations

        Examples across languages:
        - English: "Ask me questions until you understand my investment goals"
        - Spanish: "Hazme preguntas hasta que entiendas mis objetivos de inversión"
        - French: "Posez-moi des questions jusqu'à ce que vous compreniez mes objectifs
          d'investissement"
        - German: "Stellen Sie mir Fragen, bis Sie meine Anlageziele verstehen"

        - English: "I want to start a business, then get funding. What do you think?"
        - Spanish: "Quiero empezar un negocio, luego conseguir financiación. ¿Qué piensas?"
        - French: "Je veux créer une entreprise, puis obtenir un financement.
          Qu'en pensez-vous?"

        Message to analyze: "{message}"

        Respond with JSON only:
        {{
            "is_proactive": boolean,
            "request_type": "guided_questioning|plan_feedback|context_first|step_by_step|comprehensive_advice",
            "goal": "what the user wants to achieve",
            "completion_criteria": "what would indicate the request is complete",
            "confidence": 0.0-1.0,
            "reasoning": "brief explanation of why this is/isn't a proactive request"
        }}

        Only detect EXPLICIT requests for proactive interaction, not implicit ones.
        Minimum confidence threshold: 0.7
        """

        try:
            response = await self.model.generate(prompt, max_tokens=300, temperature=0.1)

            # Parse LLM response
            import json

            try:
                result = json.loads(response.strip())
                if result.get("is_proactive", False) and result.get("confidence", 0) >= 0.7:
                    request_type_map = {
                        "guided_questioning": ProactiveRequestType.GUIDED_QUESTIONING,
                        "plan_feedback": ProactiveRequestType.PLAN_FEEDBACK,
                        "context_first": ProactiveRequestType.CONTEXT_FIRST,
                        "step_by_step": ProactiveRequestType.STEP_BY_STEP,
                        "comprehensive_advice": ProactiveRequestType.COMPREHENSIVE_ADVICE,
                    }

                    request_type = request_type_map.get(result.get("request_type"))
                    if request_type:
                        return ProactiveRequest(
                            request_type=request_type,
                            goal=result.get("goal", "general assistance"),
                            original_message=message,
                            completion_criteria=result.get(
                                "completion_criteria", "request fulfilled"
                            ),
                            confidence=result.get("confidence", 0.7),
                        )
                else:
                    #  Proactive detector debug - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"Proactive request not detected. "
                    #     f"Reasoning: {result.get('reasoning', 'No reasoning provided')}"
                    # )

            except json.JSONDecodeError:
                #  Proactive detector warning - TODO: add observability
                _ = None  # remove this after implementing observability

        except Exception as e:
            #  Proactive detector warning - TODO: add observability
            _ = e  # remove this after implementing observability

        return None

    async def parse_multi_step_plan(self, message: str) -> Optional[MultiStepPlan]:
        """
        Parse multi-step plans from user messages using LLM analysis

        Args:
            message: User message containing a potential plan (any language)

        Returns:
            MultiStepPlan if detected, None otherwise
        """
        if not self.model:
            #  Proactive detector debug - TODO: add observability
            return None

        try:
            #  Proactive detector debug - TODO: add observability

            prompt = f"""
            Analyze this message to extract a multi-step plan if present.

            Look for sequential steps, goals, or processes that the user has outlined.
            Plans can be in any language and format (numbered, sequential words, etc.).

            Examples:
            - "First I'll research the market, then create a business plan, finally get funding"
            - "1. Study for certification 2. Apply for jobs 3. Negotiate salary"
            - "Primero investigaré el mercado, luego crearé un plan de negocios"

            Message: "{message}"

            Respond with JSON only:
            {{
                "has_plan": boolean,
                "steps": ["step 1", "step 2", "step 3"],
                "goal": "overall goal of the plan",
                "confidence": 0.0-1.0,
                "reasoning": "brief explanation"
            }}

            Minimum 2 steps required to be considered a plan.
            Minimum confidence threshold: 0.7
            """

            response = await self.model.generate(prompt, max_tokens=400, temperature=0.1)

            import json

            try:
                result = json.loads(response.strip())
                if (
                    result.get("has_plan", False)
                    and len(result.get("steps", [])) >= 2
                    and result.get("confidence", 0) >= 0.7
                ):

                    plan = MultiStepPlan(
                        steps=result.get("steps", []),
                        goal=result.get("goal", "achieve multi-step plan"),
                        original_message=message,
                        confidence=result.get("confidence", 0.7),
                    )

                    #  Proactive detector info - TODO: add observability
                    return plan
                else:
                    #  Proactive detector debug - TODO: add observability
                    _ = None  # remove this after implementing observability
                    #     f"Multi-step plan not detected. "
                    #     f"Reasoning: {result.get('reasoning', 'No reasoning provided')}"
                    # )

            except json.JSONDecodeError:
                #  Proactive detector warning - TODO: add observability
                _ = None  # remove this after implementing observability

        except Exception as e:
            #  Proactive detector error - TODO: add observability
            _ = e  # remove this after implementing observability

        return None
