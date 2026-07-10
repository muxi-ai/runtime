import asyncio
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ...datatypes.workflow import RequestAnalysis
from ...services import observability
from ...services.llm import LLM
from ...utils.fastjson import json


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
        coding_delegation_configured: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize the request analyzer with enhanced configuration.

        Args:
            llm: Optional LLM for advanced analysis. If None, uses heuristic analysis.
            complexity_method: Method to use for complexity calculation
            complexity_threshold: Configurable threshold for decomposition (1-10)
            custom_complexity_fn: Custom function for complexity scoring
            complexity_weights: Weights for different complexity factors
            coding_delegation_configured: Callable answering whether the
                formation has coding delegation configured. Gates the
                coding-delegation security-override: without it (None or
                False) the override never fires, so delegation-shaped
                phrasing cannot launder a threat verdict in formations
                that have no delegate_coding tool at all.
        """
        self.llm = llm
        self.coding_delegation_configured = coding_delegation_configured
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
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_ANALYSIS_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "message_length": len(user_message),
                },
                description="Workflow request analysis failed, using fallback",
            )
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
                is_scheduler_query_request=False,
                is_explicit_approval_request=False,
                topics=[],
                is_security_threat=False,
                threat_type=None,
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

        # Heuristic scheduler query detection
        is_scheduler_query = self._heuristic_detect_scheduler_query(message_lower)

        return RequestAnalysis(
            complexity_score=complexity_score,
            requires_decomposition=False,  # Will be set by should_decompose
            requires_approval=False,  # Will be set by requires_user_approval
            implicit_subtasks=implicit_subtasks,
            required_capabilities=required_capabilities,
            acceptance_criteria=acceptance_criteria,
            confidence_score=0.7,  # Heuristic confidence
            is_scheduling_request=False,  # Heuristic doesn't detect scheduling
            is_scheduler_query_request=is_scheduler_query,
            is_explicit_approval_request=False,  # Heuristic doesn't detect approval requests
            topics=[],  # No heuristic topics - LLM only
            is_security_threat=False,  # Heuristic doesn't detect security threats
            threat_type=None,
        )

    @staticmethod
    def _heuristic_is_user_self_recall(user_message: str) -> bool:
        """
        Detect whether a request is asking the agent to recall information
        the USER previously shared about THEMSELVES.

        Used as a defensive override for the LLM-based security analyzer's
        ``information_extraction`` classification, which is intended for
        attacks against system / agent state ("show me your config",
        "reveal your system prompt") but occasionally false-positives on
        legitimate conversational recall ("list back the role I mentioned
        earlier", "what did I tell you about myself?", "summarize my
        profession").

        We only return True when BOTH (a) a first-person possessor anchors
        the request to the user's OWN information and (b) a recall verb /
        anaphora signals that the request points BACK at earlier turns
        rather than at system state. This intentionally favours precision
        over recall — when in doubt the LLM classification stands.

        Returns ``True`` only when the message is confidently a self-recall
        request. Returns ``False`` for ambiguous or unrelated messages.
        """
        import re

        if not user_message or not user_message.strip():
            return False

        msg = user_message.lower()

        # First-person possessor patterns: "my X", "myself", "I told you",
        # "I mentioned", "I said", "about me". A bare "I" is too noisy.
        first_person_patterns = [
            r"\bmy\s+\w+",
            r"\bmyself\b",
            r"\babout\s+me\b",
            r"\bi\s+(?:just\s+)?(?:told|tell|mentioned|said|shared|gave|provided)\b",
        ]
        has_first_person = any(re.search(p, msg) for p in first_person_patterns)
        if not has_first_person:
            return False

        # Recall / "look back" anchors. Phrases that explicitly point at
        # the conversation so far rather than at system state.
        recall_patterns = [
            r"\bmentioned\s+earlier\b",
            r"\bi\s+(?:just\s+)?(?:told|tell|mentioned|said|shared|gave|provided)\b",
            r"\blist\s+back\b",
            r"\btell\s+(?:me\s+)?back\b",
            r"\bremind\s+me\b",
            r"\brestate\b",
            r"\brepeat\s+back\b",
            r"\bwhat\s+(?:did|have)\s+i\b",
            # "what's my X" / "what is my X" / "what was my X". Note that
            # "what's" is a single token, so the apostrophe pattern must
            # not require whitespace between "what" and "'s".
            r"\bwhat'?s\s+my\b",
            r"\bwhat\s+(?:is|was)\s+my\b",
            r"\bwhat\s+do\s+you\s+(?:remember|recall|know)\s+about\s+me\b",
            r"\bsummari[sz]e\s+(?:my|what\s+i)\b",
            r"\bin\s+our\s+conversation\b",
            r"\bso\s+far\b",
            r"\bearlier\s+in\s+(?:this|our)\b",
        ]
        has_recall_anchor = any(re.search(p, msg) for p in recall_patterns)
        if not has_recall_anchor:
            return False

        # Hard rejection: messages that clearly target SYSTEM state even
        # if they contain "my" (e.g., "what's my access to your config?").
        # The information_extraction prompt examples list these explicitly.
        system_targets = [
            "your system prompt",
            "your config",
            "your configuration",
            "your instructions",
            "your tools",
            "your api key",
            "your credentials",
            "your password",
            "your secrets",
            "your architecture",
            "how were you built",
            "how you were built",
        ]
        if any(target in msg for target in system_targets):
            return False

        return True

    @staticmethod
    def _heuristic_is_artifact_retrieval(user_message: str) -> bool:
        """
        Detect whether a request targets the user's OWN stored artifacts
        (Artifact Memory Phase 2 retrieval).

        Used as a defensive override for the LLM security classifier,
        which occasionally flags legitimate artifact retrieval as
        information extraction or credential fishing: artifact ids are
        opaque Nano ID tokens ("read back artifact 'aB3xY9...'") that can
        look like secrets, and "show me the exact contents of the stored
        file" reads like extraction phrasing. The artifact tools are
        user-scoped by construction (a caller can only ever read their
        own artifacts), so retrieval requests cannot leak system or
        cross-user state.

        Precision-first: returns True only for explicit built-in tool
        mentions (get_artifact / get_artifact_content /
        get_artifact_history) or "artifact" combined with a retrieval or
        history verb. Ambiguous messages leave the LLM classification
        standing.
        """
        import re

        if not user_message or not user_message.strip():
            return False

        msg = user_message.lower()

        # Explicit built-in tool mentions are unambiguous.
        if re.search(r"\bget_artifact(?:_content|_history)?\b", msg):
            return True

        # "artifact" + a retrieval / history anchor.
        if "artifact" in msg and re.search(
            r"\b(?:read|retrieve|fetch|show|open|display|list|contents?|versions?|history)\b",
            msg,
        ):
            return True

        return False

    def _should_downgrade_coding_delegation(
        self, threat_type: Optional[str], user_message: str
    ) -> bool:
        """
        Whether the coding-delegation override may downgrade this verdict.

        Three gates, ALL required: the threat type is one of the two
        false-positive categories (never prompt_injection/jailbreak); the
        formation actually has coding delegation configured (without a
        coding: block there is no legitimate delegation to protect, so
        delegation-shaped phrasing cannot launder a threat verdict); and
        the message is confidently delegation-shaped.
        """
        return (
            threat_type in ("information_extraction", "credential_fishing")
            and self.coding_delegation_configured is not None
            and self.coding_delegation_configured()
            and self._heuristic_is_coding_delegation(user_message)
        )

    @staticmethod
    def _heuristic_is_coding_delegation(user_message: str) -> bool:
        """
        Detect whether a request delegates a coding task to the formation's
        configured coding agent (coding-agent delegation).

        Used as a defensive override for the LLM security classifier,
        which occasionally flags legitimate delegation requests as
        threats: "clone the repository at file://... and push a branch"
        reads like exfiltration or system exploitation to the classifier,
        but it is exactly what the user-scoped delegate_coding tool exists
        for -- the task runs in a disposable delegation directory against
        repositories the user names.

        Precision-first: returns True only for an explicit delegate_coding
        tool mention, or delegation phrasing ("delegate"/"hand off")
        combined with a coding anchor. Ambiguous messages leave the LLM
        classification standing.
        """
        import re

        if not user_message or not user_message.strip():
            return False

        msg = user_message.lower()

        # Explicit built-in tool mentions are unambiguous.
        if re.search(r"\bdelegate_coding\b", msg):
            return True

        # Delegation phrasing + a coding anchor.
        if re.search(r"\b(?:delegate|delegating|hand(?:\s+this)?\s+off)\b", msg) and re.search(
            r"\b(?:coding|code|programming)\b", msg
        ):
            return True

        return False

    @staticmethod
    def _heuristic_detect_scheduler_query(message_lower: str) -> bool:
        """Detect scheduler query intent via keyword patterns."""
        import re

        scheduler_query_patterns = [
            r"\b(?:show|list|view|check|display|see)\b.*\b(?:scheduled|scheduler)\b",
            r"\b(?:scheduled|scheduler)\b.*\b(?:jobs?|tasks?|items?|reminders?)\b",
            r"\bmy\s+(?:scheduled|recurring)\s+(?:jobs?|tasks?|reminders?)\b",
            r"\bwhat(?:'s|\s+is)\s+(?:on\s+)?my\s+schedule\b",
            r"\bdo\s+i\s+have\s+(?:any\s+)?scheduled\b",
            r"\bany\s+scheduled\s+(?:jobs?|tasks?|reminders?)\b",
        ]
        return any(re.search(p, message_lower) for p in scheduler_query_patterns)

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
        system_prompt, user_content = self._create_analysis_messages(user_message, context)

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
            response = await self.llm.chat(messages, max_tokens=1000)

            # Check cancellation after LLM call (uses context to find request_tracker)
            from ..background.cancellation import check_cancellation_from_context

            # Note: request_tracker is passed via context if available
            if context and context.get("request_tracker"):
                await check_cancellation_from_context(context["request_tracker"])

            analysis = self._parse_llm_analysis(response)

            # Heuristic fallback: if LLM didn't detect scheduler query, check patterns
            if not analysis.is_scheduler_query_request:
                if self._heuristic_detect_scheduler_query(user_message.lower()):
                    analysis.is_scheduler_query_request = True

            # Defensive override: the LLM classifier is non-deterministic on
            # borderline information-extraction phrasings and sometimes
            # blocks legitimate user-self-recall ("list back the role I
            # mentioned earlier", "what did I tell you about myself?").
            # The threat category is unambiguously about reading SYSTEM /
            # AGENT / INFRASTRUCTURE state — recall of the user's own
            # earlier utterances is not in scope. When the heuristic
            # confidently identifies user-self-recall, downgrade.
            if (
                analysis.is_security_threat
                and analysis.threat_type == "information_extraction"
                and self._heuristic_is_user_self_recall(user_message)
            ):
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_ANALYSIS_FAILED,
                    level=observability.EventLevel.INFO,
                    data={
                        "reason": "user_self_recall_override",
                        "original_threat_type": analysis.threat_type,
                        "message_preview": user_message[:120],
                    },
                    description=(
                        "LLM flagged user-self-recall as information_extraction; "
                        "heuristic override downgraded to non-threat"
                    ),
                )
                analysis.is_security_threat = False
                analysis.threat_type = None

            # Same defensive posture for coding delegation: "clone this
            # repository and push a branch" phrasing reads like
            # exfiltration to the classifier, but delegating a coding
            # task to the formation-configured coding agent is the
            # delegate_coding tool's normal use (never downgrades
            # prompt_injection / jailbreak). Gated on the formation
            # actually having coding delegation configured -- in a
            # formation with no coding: block there is no legitimate
            # delegation to protect, so the classifier's verdict stands.
            if analysis.is_security_threat and self._should_downgrade_coding_delegation(
                analysis.threat_type, user_message
            ):
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_ANALYSIS_FAILED,
                    level=observability.EventLevel.INFO,
                    data={
                        "reason": "coding_delegation_override",
                        "original_threat_type": analysis.threat_type,
                        "message_preview": user_message[:120],
                    },
                    description=(
                        "LLM flagged a coding delegation request as a security "
                        "threat; heuristic override downgraded to non-threat"
                    ),
                )
                analysis.is_security_threat = False
                analysis.threat_type = None

            # Same defensive posture for artifact retrieval (Artifact
            # Memory Phase 2): opaque artifact ids read like secrets and
            # "show the stored file's exact contents" reads like
            # extraction, so the classifier false-positives on the
            # user-scoped artifact tools. Retrieval of one's own stored
            # artifacts is normal memory access.
            if (
                analysis.is_security_threat
                and analysis.threat_type in ("information_extraction", "credential_fishing")
                and self._heuristic_is_artifact_retrieval(user_message)
            ):
                observability.observe(
                    event_type=observability.ConversationEvents.WORKFLOW_ANALYSIS_FAILED,
                    level=observability.EventLevel.INFO,
                    data={
                        "reason": "artifact_retrieval_override",
                        "original_threat_type": analysis.threat_type,
                        "message_preview": user_message[:120],
                    },
                    description=(
                        "LLM flagged artifact retrieval as a security threat; "
                        "heuristic override downgraded to non-threat"
                    ),
                )
                analysis.is_security_threat = False
                analysis.threat_type = None

            return analysis

        except Exception as e:
            # Log error and fall back to heuristic
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_ANALYSIS_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "fallback": "heuristic_analysis",
                    "message_length": len(user_message),
                },
                description="LLM-based request analysis failed, falling back to heuristic analysis",
            )
            return self._heuristic_analyze_request(user_message)

    def _create_analysis_messages(
        self, user_message: str, context: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        Create messages for LLM-based request analysis.

        Args:
            user_message: User's request
            context: Optional conversation context

        Returns:
            Tuple of (system_prompt, user_content) for proper caching
        """
        context_info = ""
        if context:
            context_info = f"\nConversation context: {context}"

        # Add SOP context if SOPs are available
        sop_context = ""
        if context and "available_sops" in context:
            sop_list = context["available_sops"]
            if sop_list:
                sop_context = f"\nAvailable SOPs: {', '.join(sop_list)}"

        from ..prompts.loader import PromptLoader

        # Get the system instructions with user message for context
        system_prompt = PromptLoader.get(
            "workflow_request_analysis.md",
            user_message=user_message,
            context_info=context_info,
            sop_context=sop_context,
        )

        # Return system prompt and user message separately (for cache differentiation)
        return system_prompt, f"Analyze this request: {user_message}"

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

                # Normalize explicit_sop_request: strip whitespace and convert empty/whitespace to None
                explicit_sop = data.get("explicit_sop_request")
                if explicit_sop:
                    explicit_sop = explicit_sop.strip()
                    if not explicit_sop:  # Empty after stripping
                        explicit_sop = None

                # Extract and normalize topics
                topics = data.get("topics", [])
                if not isinstance(topics, list):
                    topics = []  # Handle malformed response
                # Normalize: strip whitespace, lowercase, remove empty strings
                topics = [str(t).strip().lower() for t in topics if t]
                topics = [t for t in topics if t][:5]  # Remove empties, limit to 5

                return RequestAnalysis(
                    complexity_score=float(data.get("complexity_score", 5.0)),
                    requires_decomposition=False,  # Will be set by should_decompose
                    requires_approval=False,  # Will be set by requires_user_approval
                    implicit_subtasks=data.get("implicit_subtasks", []),
                    required_capabilities=data.get("required_capabilities", ["general"]),
                    acceptance_criteria=data.get("acceptance_criteria", []),
                    confidence_score=float(data.get("confidence_score", 0.8)),
                    is_scheduling_request=data.get("is_scheduling_request", False),
                    is_scheduler_query_request=data.get("is_scheduler_query_request", False),
                    is_explicit_approval_request=data.get("is_explicit_approval_request", False),
                    explicit_sop_request=explicit_sop,
                    topics=topics,
                    is_security_threat=data.get("is_security_threat", False),
                    threat_type=data.get("threat_type"),
                )
            else:
                raise ValueError("No valid JSON found in response")

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WORKFLOW_ANALYSIS_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "method": "llm_analysis",
                },
                description="LLM-based workflow analysis failed, using fallback",
            )
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
                is_scheduler_query_request=False,
                is_explicit_approval_request=False,
                topics=[],
                is_security_threat=False,
                threat_type=None,
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
                heuristic_analysis.topics = llm_analysis.topics  # Use LLM topics
            except Exception:
                # Use heuristic score if LLM fails
                pass  # heuristic_analysis.topics remains []

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
            topics=[],
            is_security_threat=False,
            threat_type=None,
        )
