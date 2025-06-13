import asyncio
from typing import Optional, List, Dict, Any
# Loguru import removed - add observability import

from .types import RequestAnalysis
from ...llm import LLM


class RequestAnalyzer:
    """
    Analyze user requests to determine complexity and decomposition needs.

    The RequestAnalyzer examines user messages to determine if they require
    complex multi-agent workflows or can be handled by simple agent routing.
    It also detects when users want to preview and approve plans before execution.
    """

    def __init__(self, llm: Optional[LLM] = None):
        """
        Initialize the request analyzer.

        Args:
            llm: Optional LLM for advanced analysis. If None, uses heuristic analysis.
        """
        self.llm = llm
        self.complexity_threshold = 7.0  # Configurable threshold for decomposition

    async def analyze_request(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
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
            # Check for approval requirement first
            requires_approval = await self.requires_user_approval(user_message)

            if self.llm:
                # Use LLM-powered analysis for more sophisticated understanding
                analysis = await self._llm_analyze_request(user_message, context)
            else:
                # Fall back to heuristic analysis
                analysis = self._heuristic_analyze_request(user_message)

            # Override approval requirement if detected
            analysis.requires_approval = requires_approval

            # Determine if decomposition is needed
            analysis.requires_decomposition = await self.should_decompose(analysis)

            #  Debug - add observability event
                f"Request analysis: complexity={analysis.complexity_score:.1f}, "
                f"decomposition={analysis.requires_decomposition}, "
                f"approval={analysis.requires_approval}"
            )

            return analysis

        except Exception as e:
            #  Error - add observability event
            # Return safe fallback analysis
            return RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=requires_approval,
                implicit_subtasks=[],
                required_capabilities=["general"],
                acceptance_criteria=[],
                confidence_score=0.3
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
            analysis.complexity_score >= self.complexity_threshold or
            len(analysis.implicit_subtasks) > 2 or
            len(analysis.required_capabilities) > 1
        )

    async def requires_user_approval(
        self,
        user_message: str,
        analysis: Optional[RequestAnalysis] = None
    ) -> bool:
        """
        Detect if user wants to review plan before execution.

        Approval triggers:
        - "Please let me know how you're going to do this"
        - "Show me your plan first"
        - "What's your approach?"
        - "Let me approve the plan before you start"
        - "How would you handle this?"
        - "Walk me through your process"

        Args:
            user_message: User's message to analyze
            analysis: Optional analysis results for additional context

        Returns:
            True if user wants plan approval workflow
        """
        approval_phrases = [
            "let me know how you're going to",
            "show me your plan",
            "what's your approach",
            "let me approve",
            "how would you handle",
            "walk me through",
            "what's your process",
            "how are you going to",
            "show me how you'll",
            "explain your method",
            "outline your strategy",
            "describe your approach",
            "what steps will you take",
            "how do you plan to",
            "what's your methodology",
            "break down your process"
        ]

        message_lower = user_message.lower()
        return any(phrase in message_lower for phrase in approval_phrases)

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
            "who": 2
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
            "and then", "after that", "once", "first", "second",
            "finally", "also", "additionally"
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
            "communication": ["email", "message", "send", "notify", "contact"]
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

        # Clamp complexity score
        complexity_score = min(10.0, max(1.0, complexity_score))

        return RequestAnalysis(
            complexity_score=complexity_score,
            requires_decomposition=False,  # Will be set by should_decompose
            requires_approval=False,  # Will be set by requires_user_approval
            implicit_subtasks=implicit_subtasks,
            required_capabilities=required_capabilities,
            acceptance_criteria=acceptance_criteria,
            confidence_score=0.7  # Heuristic confidence
        )

    async def _llm_analyze_request(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
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
            response = await self.llm.generate(analysis_prompt, max_tokens=1000)
            return self._parse_llm_analysis(response)

        except Exception as e:
            #  Warning - add observability event
            return self._heuristic_analyze_request(user_message)

    def _create_analysis_prompt(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None
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

User Request: "{user_message}"{context_info}

Please provide analysis in JSON format:

{{
    "complexity_score": [1-10 scale where 1=simple question, 10=complex multi-step project],
    "implicit_subtasks": [List the logical steps this request would require],
    "required_capabilities": [List capabilities needed like research, writing, coding, analysis],
    "acceptance_criteria": [List what would make this request successfully completed],
    "confidence_score": [0.0-1.0 how confident you are in this analysis],
    "reasoning": [Brief explanation of the analysis]
}}

Analysis Guidelines:
- Simple questions (1-3): "What is X?", "Show me Y", basic information requests
- Medium tasks (4-6): Single-agent tasks requiring some work
- Complex workflows (7-10): Multi-step processes requiring coordination

Focus on identifying:
1. How many logical steps are involved
2. What different types of expertise are needed
3. Whether this requires multiple agents working together
4. The overall scope and depth of work required
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
            import json

            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)

                return RequestAnalysis(
                    complexity_score=float(data.get('complexity_score', 5.0)),
                    requires_decomposition=False,  # Will be set by should_decompose
                    requires_approval=False,  # Will be set by requires_user_approval
                    implicit_subtasks=data.get('implicit_subtasks', []),
                    required_capabilities=data.get('required_capabilities', ["general"]),
                    acceptance_criteria=data.get('acceptance_criteria', []),
                    confidence_score=float(data.get('confidence_score', 0.8))
                )
            else:
                raise ValueError("No valid JSON found in response")

        except Exception as e:
            #  Error - add observability event
            # Return fallback analysis
            return RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=[],
                required_capabilities=["general"],
                acceptance_criteria=[],
                confidence_score=0.3
            )

    # Helper methods for testing
    def _detect_approval_request(self, user_message: str) -> bool:
        """Helper method for testing approval detection."""
        return asyncio.run(self.requires_user_approval(user_message))

    def _calculate_heuristic_complexity(self, user_message: str) -> float:
        """Helper method for testing complexity calculation."""
        analysis = self._heuristic_analyze_request(user_message)
        return analysis.complexity_score

    def _identify_capabilities(self, user_message: str) -> List[str]:
        """Helper method for testing capability identification."""
        analysis = self._heuristic_analyze_request(user_message)
        return analysis.required_capabilities
