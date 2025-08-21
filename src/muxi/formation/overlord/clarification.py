# src/muxi/formation/clarification/unified.py

import time
import json
import re
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class ClarificationResult:
    action: str  # "clarify" or "execute"
    question: Optional[str] = None
    request: Optional[str] = None
    context: Optional[Dict] = None
    mode: Optional[str] = None


class UnifiedClarificationSystem:
    """
    Complete clarification system in one class.
    Handles all clarification types via LLM-based decision making.
    State managed in buffer memory with request_id as key.
    """

    def __init__(self, overlord):
        self.overlord = overlord

        # Buffer memory for state management
        self.buffer_memory = overlord.buffer_memory if hasattr(overlord, "buffer_memory") else None
        self.namespace = "clarification"
        self.active_requests = set()

        # Configuration - store reference to config object for hierarchy lookup
        self.clarification_config = overlord.clarification_config if hasattr(overlord, "clarification_config") else None

        # Extract configuration values
        if self.clarification_config:
            # Get values from config - max_questions may be None if not explicitly set
            self.max_questions = getattr(self.clarification_config, "max_questions", None)

            # Parse max_rounds - can be dict or single value
            max_rounds_raw = getattr(self.clarification_config, "max_rounds", None)
            if max_rounds_raw:
                if isinstance(max_rounds_raw, dict):
                    # Already a dict with mode-specific limits
                    self.max_rounds = max_rounds_raw
                else:
                    # Single value - convert to dict with "other" key
                    self.max_rounds = {"other": max_rounds_raw}
            else:
                self.max_rounds = None

            self.timeout = getattr(self.clarification_config, "timeout_seconds", 300)
            style_enum = getattr(self.clarification_config, "style", None)
            self.style = style_enum.value if style_enum else "conversational"
        else:
            # No configuration available - rely on sensible defaults in _get_max_depth
            self.max_questions = None
            self.max_rounds = None
            self.timeout = 300
            self.style = "conversational"

        # Get LLM reference - use extraction_model which has proper fallback to text model
        self.llm = overlord.extraction_model

    async def needs_clarification(
        self, message: str, request_id: str, session_id: str = None, context: Optional[Dict] = None
    ) -> ClarificationResult:
        """
        Main entry point - analyzes if clarification is needed.
        Uses request_id as primary identifier.
        """
        # Check for existing clarification
        if await self.has_active_clarification(request_id):
            return await self.handle_response(request_id, message)

        # Analyze new request
        analysis = await self._analyze_request(message, context or {})

        if analysis["needs_clarification"]:
            # Start clarification - store in buffer memory
            await self._create_state(request_id, message, analysis["mode"], session_id)
            # Store the question we're asking
            state = await self._get_state(request_id)
            if state:
                state["last_question"] = analysis["question"]
                await self._store_state(request_id, state)
            return ClarificationResult(
                action="clarify", question=analysis["question"], mode=analysis["mode"]
            )

        # No clarification needed
        return ClarificationResult(action="execute", request=message, mode="direct")

    async def handle_response(self, request_id: str, response: str) -> ClarificationResult:
        """
        Handle clarification response and determine next action.
        """
        state = await self._get_state(request_id)
        if not state:
            # No active clarification
            return ClarificationResult(action="execute", request=response)

        # Update state
        state["collected_info"].append(response)
        state["depth"] += 1

        # Store updated state back to buffer
        await self._store_state(request_id, state)

        # Check termination conditions
        if state["depth"] >= state["max_depth"]:
            # Max depth reached - cleanup immediately
            enhanced = self._build_enhanced_request(state)
            await self._cleanup_state(request_id)  # Explicit cleanup, don't wait for TTL
            return ClarificationResult(
                action="execute", request=enhanced, context={"collected": state["collected_info"]}
            )

        if self._check_timeout(state):
            # Timeout - cleanup immediately
            enhanced = self._build_enhanced_request(state)
            await self._cleanup_state(request_id)  # Explicit cleanup, don't wait for TTL
            return ClarificationResult(
                action="execute", request=enhanced, context={"timeout": True}
            )

        # Check for context switch (user doing something else)
        context_switch = await self._check_context_switch(state, response)
        if context_switch:
            # User wants to do something different
            # Cancel clarification and process new request
            await self._cleanup_state(request_id)  # Clean up clarification
            return ClarificationResult(
                action="execute",
                request=response,  # Process their new request
                context={"clarification_cancelled": True, "reason": "context_switch"},
            )

        # Check if user wants to stop clarification
        stop_check = await self._check_stop_intent(response)
        if stop_check:
            enhanced = self._build_enhanced_request(state)
            await self._cleanup_state(request_id)  # Explicit cleanup, don't wait for TTL
            return ClarificationResult(
                action="execute", request=enhanced, context={"user_stopped": True}
            )

        # Determine if we need more clarification
        need_more = await self._check_need_more(state)

        if need_more["needs_more"]:
            # Update state in buffer with the new question
            state["last_question"] = need_more["question"]
            await self._store_state(request_id, state)
            return ClarificationResult(
                action="clarify", question=need_more["question"], mode=state["mode"]
            )
        else:
            # Got enough information - cleanup immediately
            enhanced = self._build_enhanced_request(state)
            await self._cleanup_state(request_id)  # Explicit cleanup, don't wait for TTL
            return ClarificationResult(
                action="execute", request=enhanced, context={"collected": state["collected_info"]}
            )

    async def handle_credential_error(self, error: Any, request_id: str) -> ClarificationResult:
        """
        Handle AmbiguousCredentialError using request_id.
        """
        # Create credential selection state in buffer memory
        state = {
            "depth": 0,
            "original_request": getattr(error, "original_request", ""),
            "collected_info": [],
            "max_depth": 1,
            "mode": "credential",
            "context": {
                "service": error.service,
                "options": error.available_credentials,
                "error": error,
            },
            "started_at": time.time(),
            "request_id": request_id,
        }

        await self._store_state(request_id, state)

        # Generate question using configured style
        style_guidance = {
            "conversational": "Make it natural and friendly. One sentence.",
            "technical": "Be precise and technical.",
            "brief": "Be very concise.",
        }.get(self.style, "Make it natural and friendly.")

        prompt = f"""
        Generate a question for selecting a credential.
        Style: {self.style}

        Service: {error.service}
        Available options: {[opt['name'] for opt in error.available_credentials]}

        {style_guidance}
        """

        if not self.llm:
            # Fallback question when no LLM available
            options_text = "\n".join(
                [f"{i+1}. {opt['name']}" for i, opt in enumerate(error.available_credentials)]
            )
            question = f"Which {error.service} account would you like to use?\n{options_text}"
        else:
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm.chat(messages, temperature=0.3)
            question = response.content if hasattr(response, "content") else str(response)

        return ClarificationResult(action="clarify", question=question, mode="credential")

    async def has_active_clarification(self, request_id: str) -> bool:
        """Check if request has active clarification in buffer."""
        state = await self._get_state(request_id)
        return state is not None

    async def cancel_clarification(self, request_id: str) -> bool:
        """Cancel active clarification and clean buffer."""
        if await self.has_active_clarification(request_id):
            await self._cleanup_state(request_id)
            return True
        return False

    async def get_state(self, request_id: str) -> Optional[Dict]:
        """Get clarification state for debugging."""
        return await self._get_state(request_id)

    # Private methods - Buffer Memory Operations

    async def _store_state(self, request_id: str, state: Dict):
        """Store state in buffer memory with request_id as key"""
        if not self.buffer_memory:
            # Fallback to in-memory storage if buffer memory not available
            if not hasattr(self, "_fallback_storage"):
                self._fallback_storage = {}
            self._fallback_storage[request_id] = state
            self.active_requests.add(request_id)
            return

        state["request_id"] = request_id

        # Use consistent prefixed key
        key = f"clarification:{request_id}"
        await self.buffer_memory.kv_set(
            key=key,
            value=state,
            ttl=None,  # No TTL - let FIFO handle cleanup
            namespace=self.namespace
        )

        self.active_requests.add(request_id)

    async def _get_state(self, request_id: str) -> Optional[Dict]:
        """Retrieve state from buffer memory"""
        if not self.buffer_memory:
            # Use fallback storage
            if hasattr(self, "_fallback_storage"):
                return self._fallback_storage.get(request_id)
            return None

        # Use consistent prefixed key
        key = f"clarification:{request_id}"
        return await self.buffer_memory.kv_get(key, namespace=self.namespace)

    async def _cleanup_state(self, request_id: str):
        """Remove state from buffer memory"""
        if not self.buffer_memory:
            # Use fallback storage
            if hasattr(self, "_fallback_storage") and request_id in self._fallback_storage:
                del self._fallback_storage[request_id]
            self.active_requests.discard(request_id)
            return

        # Use consistent prefixed key
        key = f"clarification:{request_id}"
        await self.buffer_memory.kv_delete(key, namespace=self.namespace)
        self.active_requests.discard(request_id)

    async def _create_state(self, request_id: str, message: str, mode: str, session_id: str = None):
        """Create new clarification state in buffer."""
        state = {
            "depth": 0,
            "original_request": message,
            "collected_info": [],
            "max_depth": self._get_max_depth(mode),
            "mode": mode,
            "context": {},
            "started_at": time.time(),
            "request_id": request_id,
            "session_id": session_id,  # For stats only
        }

        await self._store_state(request_id, state)

    # Private methods - Analysis and Generation

    async def _analyze_request(self, message: str, context: Dict) -> Dict:
        """
        Analyze request using LLM - no pattern matching.
        """
        # Get formation capabilities
        capabilities = []
        if hasattr(self.overlord, "formation"):
            if hasattr(self.overlord.formation, "mcp_servers"):
                capabilities.extend(self.overlord.formation.mcp_servers.keys())
            if hasattr(self.overlord.formation, "agents"):
                capabilities.extend([a.name for a in self.overlord.formation.agents])

        response_style = {
            "conversational": "natural, friendly, like a helpful colleague",
            "technical": "precise, specific, professional",
            "brief": "very concise, minimal words"
        }.get(self.style, "natural, friendly, like a helpful colleague")

        # Extract conversation context if it exists, otherwise use the full message
        if "=== CONVERSATION CONTEXT (Most Recent First) ===" in message:
            conversation = message.split("=== CONVERSATION CONTEXT (Most Recent First) ===")[-1].strip()
        elif "=== CURRENT REQUEST ===" in message:
            # Use the entire enhanced message if no conversation context
            conversation = message
        else:
            # Fallback to raw message
            conversation = f"User: {message}"

        prompt = f"""
Analyze this transcript to determine if clarification is needed regarding the user most recent request.

=== CONVERSATION TRANSCRIPT ===
{conversation}

=== AVAILABLE CONTEXT ===
{json.dumps(context) if context else "{}"}

=== SYSTEM CAPABILITIES ===
{", ".join(capabilities) if capabilities else "Conversation"}

=== INSTRUCTIONS ===
Be {response_style}.

Determine:
1. Is the request clear enough to attempt execution?
2. What mode of interaction does the user want?
3. If clarification needed, what should we ask?

IMPORTANT RULES:
- If the request is clear enough to make an attempt, don't clarify
- If user provides code or specific error, that's usually enough
- For vague requests like "help me" or "fix this", DO clarify
- If we lack the tools/capabilities, don't clarify (fail fast)
- Detect if user wants brainstorming/planning vs direct action

Return JSON:
{{
    "needs_clarification": boolean,
    "reason": "ambiguous|missing_info|no_capability|clear",
    "mode": "direct|brainstorm|planning",
    "question": "clarification question in the specified style or null",
    "confidence": 0.0 to 1.0
}}
        """

        if not self.llm:
            # Fallback when no LLM available
            return {
                "needs_clarification": False,
                "reason": "no_llm",
                "mode": "direct",
                "question": None,
                "confidence": 0.0,
            }

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.chat(messages, temperature=0, max_tokens=200)
        content = response.content if hasattr(response, "content") else str(response)

        # Parse JSON
        try:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            return json.loads(json_str)
        except Exception:
            # Fallback if JSON parsing fails
            return {
                "needs_clarification": False,
                "reason": "clear",
                "mode": "direct",
                "question": None,
                "confidence": 0.5,
            }

    async def _check_need_more(self, state: Dict) -> Dict:
        """
        Check if we need more clarification.
        """
        if not self.llm:
            # Fallback when no LLM available
            return {"needs_more": False, "question": None}

        prompt = f"""
        Determine if we need more clarification.

        Original request: {state['original_request']}
        Information collected so far: {state['collected_info']}
        Mode: {state['mode']}

        Do we have enough to proceed? If not, what should we ask next?

        Question Style: {self.style}
        Style Guidelines:
        - conversational: Natural, friendly, like a helpful colleague
        - technical: Precise, specific, professional
        - brief: Very concise, minimal words

        Return JSON:
        {{
            "needs_more": boolean,
            "question": "next question in the specified style or null"
        }}

        Be practical - if we have enough to make progress, don't over-clarify.
        """

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.chat(messages, temperature=0, max_tokens=150)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            return json.loads(json_str)
        except Exception:
            return {"needs_more": False, "question": None}

    async def _check_context_switch(self, state: Dict, response: str) -> bool:
        """
        Check if user is trying to do something else (context switch).
        Uses LLM to detect when user wants to break out of clarification.
        """
        if not self.llm:
            return False  # Assume no context switch without LLM

        # Get the last question we asked
        last_question = state.get("last_question", "a clarification question")

        prompt = f"""
        We're in a clarification dialog about: {state['original_request']}
        We asked: "{last_question}"
        The user responded: "{response}"

        Determine if the user is:
        1. Answering our specific question (even if briefly)
        2. Asking for something completely different/unrelated

        Examples of context switches:
        - We ask "Which account?" → User says "tell me a joke"
        - We ask "What language?" → User says "what's the weather?"
        - We ask "Which file?" → User says "create a new project"

        Examples of NOT context switches (these ARE answers):
        - We ask "What is the second source?" → User says "REST API endpoint"
        - We ask "Which account?" → User says "the first one"
        - We ask "What language?" → User says "Python"
        - We ask "Which file?" → User says "never mind"

        IMPORTANT: Short answers like "REST API endpoint" or "PostgreSQL database" are
        typically ANSWERS to our question, not context switches.

        Return "answering" if related to our question, "different" if unrelated.
        """

        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.chat(messages, temperature=0, max_tokens=20)
        content = result.content if hasattr(result, "content") else str(result)
        return "different" in content.lower()

    async def _check_stop_intent(self, response: str) -> bool:
        """
        Check if user wants to stop clarification.
        Different from context switch - this is when user wants to stop but stay on topic.
        """
        if not self.llm:
            return False  # Assume no stop intent without LLM

        prompt = f"""
        Does this response indicate the user wants to stop clarification?

        User said: {response}

        Look for phrases like "enough", "just do it", "stop asking", "never mind", etc.

        Return just "true" or "false".
        """

        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.chat(messages, temperature=0, max_tokens=10)
        content = result.content if hasattr(result, "content") else str(result)
        return "true" in content.lower()

    def _build_enhanced_request(self, state: Dict) -> str:
        """
        Build enhanced request from original + collected info.
        """
        if state["mode"] == "credential":
            # For credential selection, return the selection
            if state["collected_info"]:
                return state["collected_info"][-1]
            return state["original_request"]

        if state["mode"] in ["brainstorm", "planning"]:
            # For interactive modes, build context
            parts = [
                f"Goal: {state['original_request']}",
                f"Discussion: {'; '.join(state['collected_info'])}",
            ]
            return "\n".join(parts)

        # For direct mode, enhance the request
        if state["collected_info"]:
            info = "; ".join(state["collected_info"])
            return f"{state['original_request']}. Additional context: {info}"

        return state["original_request"]

    def _get_max_depth(self, mode: str) -> int:
        """
        Get max depth for mode using 4-level configuration hierarchy:
        1. max_rounds.{specific_mode} (highest priority)
        2. max_rounds.other (mode fallback)
        3. max_questions (backward compatibility)
        4. Sensible defaults (final fallback)
        """
        # Sensible defaults (used when no config available)
        defaults = {
            "direct": 3,
            "brainstorm": 10,
            "planning": 7,
            "execution": 3,
            "credential": 2,  # Updated from 1 to 2
            "other": 3
        }

        # Check for new max_rounds configuration (highest priority)
        if self.max_rounds and isinstance(self.max_rounds, dict):
            # 1. Check mode-specific max_rounds
            if mode in self.max_rounds:
                return self.max_rounds[mode]
            # 2. Check "other" fallback in max_rounds
            if "other" in self.max_rounds:
                return self.max_rounds["other"]

        # 3. Check old max_questions for backward compatibility
        if self.max_questions is not None:
            return self.max_questions

        # 4. Final fallback to sensible defaults
        return defaults.get(mode, defaults["other"])

    def _check_timeout(self, state: Dict) -> bool:
        """Check if clarification has timed out."""
        elapsed = time.time() - state["started_at"]
        return elapsed > self.timeout

    # Token detection utilities (migrated from ClarificationHandler)

    async def looks_like_credential_token(self, message: str) -> bool:
        """
        Check if a message appears to contain a credential token.

        Args:
            message: The message to check

        Returns:
            True if the message likely contains a token
        """
        if not message or not isinstance(message, str):
            return False

        # Check for common token patterns
        token_patterns = [
            r"ghp_[A-Za-z0-9]{36}",  # GitHub personal access token
            r"github_pat_[A-Za-z0-9_]+",  # GitHub PAT (new format)
            r"ghs_[A-Za-z0-9]{36}",  # GitHub server token
            r"glpat-[A-Za-z0-9\-_]+",  # GitLab token
            r"sk-[A-Za-z0-9]+",  # OpenAI and similar
            r"token:[A-Za-z0-9]+",  # Generic token format
            r"api[_-]?key[:\s]+[A-Za-z0-9]+",  # API key patterns
        ]

        for pattern in token_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        # Check if the entire message is a token-like string
        stripped = message.strip().strip('"').strip("'")
        if self._is_token_string(stripped):
            return True

        # Additional heuristic for potential tokens not caught by patterns
        # Only flag as credential if it meets multiple criteria to reduce false positives
        if " " not in stripped and 20 <= len(stripped) <= 200:
            # Skip common ID patterns that are unlikely to be credentials
            lower_stripped = stripped.lower()

            # Common non-credential patterns to exclude
            if any(pattern in lower_stripped for pattern in [
                'product_id', 'user_id', 'session_id', 'request_id', 'order_id',
                'transaction_id', 'customer_id', 'account_id', 'invoice_id',
                'http://', 'https://', '.com', '.org', '.net'  # URLs
            ]):
                return False

            # Require both letters and digits
            has_letter = any(c.isalpha() for c in stripped)
            has_digit = any(c.isdigit() for c in stripped)

            if has_letter and has_digit:
                # Check for case transitions (common in tokens like "aB3cD4eF")
                has_case_transition = False
                for i in range(len(stripped) - 1):
                    if stripped[i].isalpha() and stripped[i + 1].isalpha():
                        if stripped[i].islower() != stripped[i + 1].islower():
                            has_case_transition = True
                            break

                # Check for known credential-like prefixes (case-insensitive)
                has_credential_prefix = any(
                    lower_stripped.startswith(prefix) for prefix in [
                        'key_', 'token_', 'api_', 'apikey', 'secret_', 'password',
                        'bearer', 'access_token', 'private_', 'auth_'
                    ]
                ) or any(
                    # Exact match for short prefixes to avoid false positives
                    lower_stripped == prefix or lower_stripped.startswith(prefix + '-')
                    for prefix in ['key', 'token', 'api', 'secret', 'auth']
                )

                # Check for high entropy (mix of upper, lower, digits, special chars)
                has_upper = any(c.isupper() for c in stripped)
                has_lower = any(c.islower() for c in stripped)
                has_special = any(c in '-_+/=' for c in stripped)
                high_entropy = sum([has_upper, has_lower, has_digit, has_special]) >= 3

                # Return True only if it strongly resembles a credential
                # Require at least TWO indicators to reduce false positives
                indicators = sum([has_case_transition, has_credential_prefix, high_entropy])
                if indicators >= 2 or (has_credential_prefix and len(stripped) >= 32):
                    return True

        return False

    async def extract_token_from_text(self, message: str) -> Optional[str]:
        """
        Extract a credential token from a message using regex patterns.

        Args:
            message: The message that may contain a token

        Returns:
            The extracted token if found, None otherwise
        """
        if not message or not isinstance(message, str):
            return None

        # Try regex patterns for known token formats
        token_patterns = [
            (r"(ghp_[A-Za-z0-9]{36})", "github"),
            (r"(github_pat_[A-Za-z0-9_]+)", "github"),
            (r"(ghs_[A-Za-z0-9]{36})", "github"),
            (r"(glpat-[A-Za-z0-9\-_]+)", "gitlab"),
            (r"(sk-[A-Za-z0-9]+)", "openai"),
        ]

        for pattern, service in token_patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)

        # If no regex match, check if entire message is a token
        stripped = message.strip().strip('"').strip("'")
        if self._is_token_string(stripped):
            return stripped

        return None

    def _is_token_string(self, token: str) -> bool:
        """Check if a string is itself a token (no surrounding text)."""
        # Check length - tokens are usually at least 20 characters
        if len(token) < 20:
            return False

        # Check for common token patterns
        # GitHub personal access tokens
        if token.startswith(("ghp_", "github_pat_", "ghs_")):
            return True

        # GitLab tokens
        if token.startswith(("glpat-", "gldt-", "glrt-")):
            return True

        # Generic API key patterns
        if token.startswith(("sk-", "pk-", "api-", "key-")):
            return True

        # Check if it looks like a base64 or hex encoded string
        # Base64 pattern
        if re.match(r"^[A-Za-z0-9+/]{20,}={0,2}$", token):
            return True
        # Hex pattern
        if re.match(r"^[A-Fa-f0-9]{32,}$", token):
            return True

        # Check if it has no spaces and reasonable length (likely a token)
        if " " not in token and 20 <= len(token) <= 200:
            # Additional heuristic: has mix of letters and numbers
            has_letter = any(c.isalpha() for c in token)
            has_digit = any(c.isdigit() for c in token)
            if has_letter and has_digit:
                return True

        return False
