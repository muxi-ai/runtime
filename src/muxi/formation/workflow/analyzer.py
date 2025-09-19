import asyncio
from typing import Optional, List, Dict, Any, Callable, Union
from enum import Enum

from ...datatypes.workflow import RequestAnalysis
from ...services.llm import LLM
import json


class ComplexityMethod(Enum):
    """Available complexity calculation methods"""

    HEURISTIC = "heuristic"  # Default rule-based analysis
    LLM = "llm"  # LLM-powered analysis
    CUSTOM = "custom"  # Custom scoring function
    HYBRID = "hybrid"  # Combination of methods


class RequestAnalyzer:
    """
    Analyze user requests to determine complexity and decomposition needs.

    The RequestAnalyzer examines user messages to determine if they require
    complex multi-agent workflows or can be handled by simple agent routing.
    It also detects when users want to preview and approve plans before execution.
    """

    def __init__(
        self,
        llm: Optional[LLM] = None,
        complexity_method: Union[ComplexityMethod, str] = ComplexityMethod.HEURISTIC,
        complexity_threshold: float = 7.0,
        custom_complexity_fn: Optional[Callable[[str, Optional[Dict[str, Any]]], float]] = None,
        complexity_weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize the request analyzer with enhanced configuration.

        Args:
            llm: Optional LLM for advanced analysis. If None, uses heuristic analysis.
            complexity_method: Method to use for complexity calculation
            complexity_threshold: Configurable threshold for decomposition (1-10)
            custom_complexity_fn: Custom function for complexity scoring
            complexity_weights: Weights for different complexity factors
        """
        self.llm = llm
        self.complexity_method = (
            ComplexityMethod(complexity_method)
            if isinstance(complexity_method, str)
            else complexity_method
        )
        self.complexity_threshold = complexity_threshold
        self.custom_complexity_fn = custom_complexity_fn

        # Default complexity weights for hybrid method
        self.complexity_weights = complexity_weights or {
            "word_count": 0.1,
            "indicator_keywords": 0.3,
            "multi_step": 0.2,
            "capabilities_count": 0.2,
            "sentence_complexity": 0.2,
        }

    async def analyze_request(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> RequestAnalysis:
        """
        Determine if request needs decomposition and extract requirements.

        Args:
            user_message: The user's request to analyze
            context: Optional conversation context for better analysis

        Returns:
            RequestAnalysis with complexity scoring and requirements
        """
        try:
            # Use configured complexity method
            if self.complexity_method == ComplexityMethod.CUSTOM and self.custom_complexity_fn:
                # Custom complexity function
                complexity_score = await self._custom_analyze_request(user_message, context)
                analysis = self._build_basic_analysis(user_message, complexity_score)
            elif self.complexity_method == ComplexityMethod.LLM and self.llm:
                # LLM-powered analysis
                analysis = await self._llm_analyze_request(user_message, context)
            elif self.complexity_method == ComplexityMethod.HYBRID:
                # Hybrid approach - combine multiple methods
                analysis = await self._hybrid_analyze_request(user_message, context)
            else:
                # Default to heuristic analysis
                analysis = self._heuristic_analyze_request(user_message)

            # Set approval based on explicit request (complexity threshold checked later in overlord)
            analysis.requires_approval = analysis.is_explicit_approval_request

            # Determine if decomposition is needed
            analysis.requires_decomposition = await self.should_decompose(analysis)

            return analysis

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            # Return safe fallback analysis
            return RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=[],
                required_capabilities=["general"],
                acceptance_criteria=["Request completed successfully"],
                confidence_score=0.3,
                is_scheduling_request=False,
                is_explicit_approval_request=False,
            )

    async def should_decompose(self, analysis: RequestAnalysis) -> bool:
        """
        Decide if request warrants multi-agent workflow.

        Args:
            analysis: Request analysis results

        Returns:
            True if request should be decomposed into workflow
        """
        # Always decompose if user explicitly requests plan preview
        if analysis.requires_approval:
            return True

        # Original complexity-based logic
        return (
            analysis.complexity_score >= self.complexity_threshold
            or len(analysis.implicit_subtasks) > 2
            or len(analysis.required_capabilities) > 1
        )

    def _heuristic_analyze_request(self, user_message: str) -> RequestAnalysis:
        """
        Analyze request using heuristic rules.

        Args:
            user_message: User's request to analyze

        Returns:
            Heuristic-based analysis results
        """
        message_lower = user_message.lower()

        # Complexity indicators
        complexity_indicators = {
            # High complexity (8-10)
            "comprehensive": 9,
            "analysis": 8,
            "research": 8,
            "report": 8,
            "strategy": 8,
            "plan": 7,
            "system": 7,
            "architecture": 9,
            "implement": 7,
            "develop": 7,
            "create": 6,
            "build": 7,
            "design": 7,
            "optimize": 8,
            "integrate": 8,
            "migrate": 9,
            "refactor": 8,
            # Medium complexity (5-7)
            "configure": 6,
            "setup": 5,
            "install": 4,
            "update": 5,
            "modify": 6,
            "fix": 5,
            "debug": 6,
            "test": 6,
            "deploy": 6,
            # Low complexity (1-4)
            "show": 3,
            "display": 3,
            "list": 2,
            "get": 2,
            "find": 3,
            "search": 3,
            "check": 3,
            "status": 2,
            "info": 2,
            "help": 1,
            "explain": 4,
            "what": 2,
            "how": 3,
            "where": 2,
            "when": 2,
            "who": 2,
        }

        # Calculate complexity score
        complexity_score = 5.0  # Base score
        words = message_lower.split()

        for word in words:
            if word in complexity_indicators:
                complexity_score = max(complexity_score, complexity_indicators[word])

        # Length-based adjustment
        if len(words) > 20:
            complexity_score += 1
        elif len(words) > 10:
            complexity_score += 0.5

        # Multi-step indicators
        multi_step_indicators = [
            "and then",
            "after that",
            "once",
            "first",
            "second",
            "finally",
            "also",
            "additionally",
        ]
        if any(indicator in message_lower for indicator in multi_step_indicators):
            complexity_score += 1

        # Capability detection
        required_capabilities = []
        capability_keywords = {
            "research": ["research", "investigate", "study", "analyze", "examine"],
            "writing": ["write", "create", "draft", "compose", "document"],
            "web_search": ["search", "find", "lookup", "google", "web"],
            "data_analysis": ["analyze", "process", "calculate", "statistics", "data"],
            "coding": ["code", "program", "script", "function", "implement"],
            "file_operations": ["file", "save", "load", "read", "write"],
            "communication": ["email", "message", "send", "notify", "contact"],
        }

        for capability, keywords in capability_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                required_capabilities.append(capability)

        if not required_capabilities:
            required_capabilities = ["general"]

        # Extract implicit subtasks
        implicit_subtasks = []
        if complexity_score >= 7:
            # Common task patterns
            if any(word in message_lower for word in ["research", "analyze"]):
                implicit_subtasks.append("Research and gather information")
            if any(word in message_lower for word in ["write", "create", "draft"]):
                implicit_subtasks.append("Create deliverable content")
            if any(word in message_lower for word in ["implement", "build", "develop"]):
                implicit_subtasks.append("Implementation work")
            if any(word in message_lower for word in ["test", "verify", "validate"]):
                implicit_subtasks.append("Testing and validation")

        # Generate acceptance criteria
        acceptance_criteria = []
        if "report" in message_lower:
            acceptance_criteria.append("Report contains comprehensive information")
        if "analysis" in message_lower:
            acceptance_criteria.append("Analysis includes actionable insights")
        if any(word in message_lower for word in ["implement", "build"]):
            acceptance_criteria.append("Implementation meets requirements")

        # Ensure at least one acceptance criterion
        if not acceptance_criteria:
            acceptance_criteria.append("Request completed successfully")

        # Clamp complexity score
        complexity_score = min(10.0, max(1.0, complexity_score))

        return RequestAnalysis(
            complexity_score=complexity_score,
            requires_decomposition=False,  # Will be set by should_decompose
            requires_approval=False,  # Will be set by requires_user_approval
            implicit_subtasks=implicit_subtasks,
            required_capabilities=required_capabilities,
            acceptance_criteria=acceptance_criteria,
            confidence_score=0.7,  # Heuristic confidence
            is_scheduling_request=False,  # Heuristic doesn't detect scheduling
            is_explicit_approval_request=False,  # Heuristic doesn't detect approval requests
        )

    async def _llm_analyze_request(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> RequestAnalysis:
        """
        Use LLM to analyze request complexity and requirements.

        Args:
            user_message: User's request
            context: Optional conversation context

        Returns:
            LLM-powered analysis results
        """
        analysis_prompt = self._create_analysis_prompt(user_message, context)

        try:
            response = await self.llm.generate_text(analysis_prompt, max_tokens=1000)
            return self._parse_llm_analysis(response)

        except Exception as e:
            # Log error and fall back to heuristic
            # TODO: add proper observability here
            _ = e  # Suppress unused variable warning
            return self._heuristic_analyze_request(user_message)

    def _create_analysis_prompt(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create prompt for LLM-based request analysis.

        Args:
            user_message: User's request
            context: Optional conversation context

        Returns:
            Analysis prompt for LLM
        """
        context_info = ""
        if context:
            context_info = f"\nConversation context: {context}"

        return f"""
Analyze this user request to determine its complexity and requirements:

User Request: "{user_message}" {context_info}

Please provide analysis in JSON format:

{{
  "complexity_score": [1-10 scale where 1=simple question, 10=complex multi-step project],
  "implicit_subtasks": [List the logical steps this request would require],
  "required_capabilities": [List capabilities needed like research, writing, coding, analysis],
  "acceptance_criteria": [List what would make this request successfully completed],
  "confidence_score": [0.0-1.0 how confident you are in this analysis],
  "is_scheduling_request": [true ONLY if user is ASKING you to CREATE/SET a schedule, reminder, or alert for future execution. Examples of TRUE: 'Remind me tomorrow at 3pm', 'At 3pm tell me a joke', 'At 15:30 today send the report', 'Schedule daily standup at 10am', 'Every Monday at 2pm team sync', 'In 2 hours take medicine', 'In 5 minutes generate a report', 'In 30 minutes check the logs', 'Set a reminder for next Friday', 'Send status update every hour', 'Run backup every night', 'Check metrics every 5 minutes', 'Generate summary every week', 'Tomorrow at 9am check emails', 'At noon send lunch reminder', 'At 5pm today log off reminder'. IMPORTANT: Any request with 'At [time]' followed by an action is a scheduling request. Recurring patterns with 'every [time unit]' are scheduling requests when followed by an action/request. The pattern is: [action/verb] + 'every' + [time period]. Common time units: minute, hour, day, week, month, morning, evening, night. Pay special attention to patterns like 'In X minutes/hours/days, do Y' which means schedule Y for X time from now. Also 'At [specific time] [action]' means schedule that action for that time. Examples of FALSE: 'Tell me about scheduling', 'I always remind myself', 'What time should I schedule?', 'The daily standup is at 10am' (statement, not request), 'What happened at 3pm?' (asking about past). Must be a request to CREATE a schedule, not a statement about schedules],
  "is_explicit_approval_request": [true ONLY if user is explicitly asking to see/review your plan or approach BEFORE you execute. This detects if they want to PREVIEW the approach, regardless of task complexity. Examples of TRUE: 'Show me your plan first', 'How would you approach this?', 'Walk me through your process', 'Let me see your strategy', 'Explain your method before starting', 'What steps would you take?', 'How are you going to handle this?'. Examples of FALSE: 'Create a report' (direct command), 'Fix this bug' (wants action), 'Help me understand Python' (wants information, not execution plan)],
  "reasoning": [Brief explanation of the analysis]
}}

CRITICAL: YOU MUST BE EXTREMELY CONSERVATIVE WITH SCORING!

FUNDAMENTAL RULE: Start at 1 and only increase if there's concrete work to do.

**Score 1-2: NO EXECUTION REQUIRED**
If the response is just text/advice/knowledge → 1-2
- Questions seeking information → 1
- Requests for recommendations → 1-2
- Asking for explanations → 1
- Seeking best practices → 1-2
TEST: Would a human answer this by just talking? → Score 1-2

**Score 3-4: SINGLE EXECUTION STEP**
REQUIRES actual system changes:
- Creating one specific file → 3
- Running one specific command → 3
- Making one code fix → 4

**Score 5-6: MODERATE WORK**
Multiple steps but one agent can handle:
- Writing a complete feature → 5-6
- Debugging a complex issue → 5-6

**Score 7-10: RARE - MULTI-AGENT PROJECTS**
- Complete applications → 8-9
- System-wide changes → 7-8

CRITICAL DECISION POINT:
Does this require DOING something or just SAYING something?
- Just saying → 1-2
- Doing one thing → 3-4
- Doing many things → 5+

START LOW: Begin with 1 and justify ANY increase!
"""

    def _parse_llm_analysis(self, response: str) -> RequestAnalysis:
        """
        Parse LLM analysis response into RequestAnalysis object.

        Args:
            response: Raw LLM response

        Returns:
            Parsed RequestAnalysis object
        """
        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)

                return RequestAnalysis(
                    complexity_score=float(data.get("complexity_score", 5.0)),
                    requires_decomposition=False,  # Will be set by should_decompose
                    requires_approval=False,  # Will be set by requires_user_approval
                    implicit_subtasks=data.get("implicit_subtasks", []),
                    required_capabilities=data.get("required_capabilities", ["general"]),
                    acceptance_criteria=data.get("acceptance_criteria", []),
                    confidence_score=float(data.get("confidence_score", 0.8)),
                    is_scheduling_request=data.get("is_scheduling_request", False),
                    is_explicit_approval_request=data.get("is_explicit_approval_request", False),
                )
            else:
                raise ValueError("No valid JSON found in response")

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            # Return fallback analysis
            return RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=[],
                required_capabilities=["general"],
                acceptance_criteria=[],
                confidence_score=0.3,
                is_scheduling_request=False,
                is_explicit_approval_request=False,
            )

    # Helper methods for testing

    def _calculate_heuristic_complexity(self, user_message: str) -> float:
        """Helper method for testing complexity calculation."""
        analysis = self._heuristic_analyze_request(user_message)
        return analysis.complexity_score

    def _identify_capabilities(self, user_message: str) -> List[str]:
        """Helper method for testing capability identification."""
        analysis = self._heuristic_analyze_request(user_message)
        return analysis.required_capabilities

    async def _custom_analyze_request(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Use custom complexity function to analyze request.

        Args:
            user_message: User's request
            context: Optional conversation context

        Returns:
            Complexity score (1-10)
        """
        if self.custom_complexity_fn:
            # Call custom function - handle both sync and async
            if asyncio.iscoroutinefunction(self.custom_complexity_fn):
                score = await self.custom_complexity_fn(user_message, context)
            else:
                score = self.custom_complexity_fn(user_message, context)

            # Ensure score is within bounds
            return min(10.0, max(1.0, float(score)))

        # Fallback to heuristic if custom function not available
        return self._calculate_heuristic_complexity(user_message)

    async def _hybrid_analyze_request(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> RequestAnalysis:
        """
        Hybrid analysis combining multiple methods with weighted scoring.

        Args:
            user_message: User's request
            context: Optional conversation context

        Returns:
            Hybrid analysis results
        """
        # Start with heuristic analysis
        heuristic_analysis = self._heuristic_analyze_request(user_message)
        heuristic_score = heuristic_analysis.complexity_score

        # Add LLM analysis if available
        llm_score = heuristic_score  # Default to heuristic if LLM not available
        if self.llm:
            try:
                llm_analysis = await self._llm_analyze_request(user_message, context)
                llm_score = llm_analysis.complexity_score

                # Merge capabilities and subtasks
                combined_capabilities = list(
                    set(
                        heuristic_analysis.required_capabilities
                        + llm_analysis.required_capabilities
                    )
                )
                combined_subtasks = list(
                    set(heuristic_analysis.implicit_subtasks + llm_analysis.implicit_subtasks)
                )

                heuristic_analysis.required_capabilities = combined_capabilities
                heuristic_analysis.implicit_subtasks = combined_subtasks
            except Exception:
                # Use heuristic score if LLM fails
                pass

        # Add custom scoring if available
        custom_score = heuristic_score
        if self.custom_complexity_fn:
            try:
                custom_score = await self._custom_analyze_request(user_message, context)
            except Exception:
                # Use heuristic score if custom fails
                pass

        # Calculate weighted average
        weights = self.complexity_weights
        weighted_score = (
            heuristic_score * weights.get("heuristic", 0.4)
            + llm_score * weights.get("llm", 0.4)
            + custom_score * weights.get("custom", 0.2)
        )

        # Update the analysis with hybrid score
        heuristic_analysis.complexity_score = min(10.0, max(1.0, weighted_score))
        heuristic_analysis.confidence_score = 0.9  # High confidence for hybrid method

        return heuristic_analysis

    def _build_basic_analysis(self, user_message: str, complexity_score: float) -> RequestAnalysis:
        """
        Build a basic RequestAnalysis from a complexity score.

        Args:
            user_message: User's request
            complexity_score: Calculated complexity score

        Returns:
            Basic RequestAnalysis object
        """
        # Extract basic capabilities from message
        message_lower = user_message.lower()
        capabilities = []

        if any(word in message_lower for word in ["research", "investigate", "analyze"]):
            capabilities.append("research")
        if any(word in message_lower for word in ["write", "create", "draft"]):
            capabilities.append("writing")
        if any(word in message_lower for word in ["code", "program", "implement"]):
            capabilities.append("coding")

        if not capabilities:
            capabilities = ["general"]

        return RequestAnalysis(
            complexity_score=complexity_score,
            requires_decomposition=False,  # Will be set later
            requires_approval=False,  # Will be set later
            implicit_subtasks=[],
            required_capabilities=capabilities,
            acceptance_criteria=["Request completed successfully"],
            confidence_score=0.8,
        )
