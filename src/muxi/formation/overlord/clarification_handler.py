"""
Clarification handling delegation for the Overlord.

This module contains all clarification-related methods extracted from overlord.py
to reduce file size and improve organization. These methods handle:
- Agent clarification requests
- Credential clarification flows
- Multi-turn clarification sequences
- Token extraction and validation
- Async clarification processing
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, Optional, Tuple

from ...services import observability
from ...datatypes.response import MuxiResponse
from ...datatypes.clarification import ClarificationContext
from ..background.request_tracker import RequestStatus


class ClarificationHandler:
    """
    Handles all clarification-related operations for the Overlord.

    This class uses delegation pattern to handle clarification logic
    while keeping the main Overlord file manageable.
    """

    def __init__(self, overlord):
        """
        Initialize the ClarificationHandler with a reference to the Overlord.

        Args:
            overlord: The Overlord instance this handler serves
        """
        self.overlord = overlord

        # Cache frequently accessed attributes for performance
        self._pending_clarifications = overlord._pending_clarifications
        self.credential_resolver = overlord.credential_resolver
        self.clarification = overlord.clarification  # Use unified clarification system
        self.request_tracker = overlord.request_tracker

        # Create a lock to protect concurrent access to _pending_clarifications
        # This prevents race conditions when multiple async tasks access the dictionary
        self._clarifications_lock = asyncio.Lock()

        # Configuration
        self._clarification_ttl_seconds = getattr(overlord, '_clarification_ttl_seconds', 3600)
        self._clarification_cleanup_interval_seconds = getattr(overlord, '_clarification_cleanup_interval_seconds', 300)

    async def _get_clarification(self, session_id: str) -> Optional[Any]:
        """Thread-safe getter for pending clarifications."""
        async with self._clarifications_lock:
            return self._pending_clarifications.get(session_id)

    async def _set_clarification(self, session_id: str, value: Any) -> None:
        """Thread-safe setter for pending clarifications."""
        async with self._clarifications_lock:
            self._pending_clarifications[session_id] = value

    async def _delete_clarification(self, session_id: str) -> None:
        """Thread-safe deletion for pending clarifications."""
        async with self._clarifications_lock:
            if session_id in self._pending_clarifications:
                del self._pending_clarifications[session_id]

    async def _has_clarification(self, session_id: str) -> bool:
        """Thread-safe check for pending clarifications."""
        async with self._clarifications_lock:
            return session_id in self._pending_clarifications

    async def _get_all_clarifications(self) -> list:
        """Thread-safe getter for all pending clarifications."""
        async with self._clarifications_lock:
            # Return a copy to prevent external modification
            return list(self._pending_clarifications.items())

    async def check_agent_clarification_request(
        self, agent_response: MuxiResponse, user_id: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Check if agent response contains a clarification request.

        Args:
            agent_response: The response from the agent
            user_id: User identifier

        Returns:
            Clarification request metadata if found, None otherwise
        """
        try:
            # Check if response has clarification metadata
            if not hasattr(agent_response, "metadata") or not agent_response.metadata:
                return None

            metadata = agent_response.metadata
            if not isinstance(metadata, dict):
                return None

            # Check for agent clarification request structure
            if (
                metadata.get("needs_clarification")
                and metadata.get("clarification_type") == "information_request"
            ):
                return metadata

            return None

        except Exception as e:
            # Log error but don't block processing
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_PROCESSING_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "phase": "agent_clarification_check",
                },
                description=f"Error checking agent clarification request: {str(e)}",
            )
            return None

    async def handle_agent_clarification_request(
        self,
        clarification_metadata: Dict[str, Any],
        agent_response: MuxiResponse,
        original_message: str,
        agent_name: str,
        user_id: Any,
        session_id: Optional[str],
        request_id: Optional[str],
    ) -> MuxiResponse:
        """
        Handle agent clarification request.

        Args:
            clarification_metadata: Metadata from agent about clarification
            agent_response: The full agent response
            original_message: The original user message
            agent_name: Name of the agent requesting clarification
            user_id: User identifier
            session_id: Session identifier
            request_id: Request identifier

        Returns:
            MuxiResponse with clarification question
        """
        try:
            # Generate user-friendly clarification question
            question = await self.generate_user_clarification_question(
                clarification_metadata, agent_response.content
            )

            # Store pending clarification
            if session_id:
                await self._set_clarification(session_id, {
                    "type": "agent_clarification",
                    "agent_name": agent_name,
                    "original_message": original_message,
                    "metadata": clarification_metadata,
                    "timestamp": time.time(),
                    "user_id": user_id,
                })

            return MuxiResponse(
                role="assistant",
                content=question,
                metadata={
                    "clarification": True,
                    "agent_name": agent_name,
                    "clarification_type": "information_request",
                },
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.OVERLORD_PROCESSING_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "error": str(e),
                    "phase": "handle_agent_clarification",
                },
                description=f"Error handling agent clarification: {str(e)}",
            )
            # Fallback to agent's original response
            return agent_response

    async def generate_user_clarification_question(
        self, clarification_metadata: Dict[str, Any], agent_content: str
    ) -> str:
        """
        Generate a user-friendly clarification question.

        Args:
            clarification_metadata: Metadata about what needs clarification
            agent_content: The agent's response content

        Returns:
            User-friendly clarification question
        """
        try:
            missing_info = clarification_metadata.get("missing_information", [])

            # If agent provided a question, use it
            if clarification_metadata.get("question"):
                return clarification_metadata["question"]

            # Generate question based on missing information
            if missing_info:
                if len(missing_info) == 1:
                    return f"Could you please provide {missing_info[0]}?"
                else:
                    items = ", ".join(missing_info[:-1]) + f" and {missing_info[-1]}"
                    return f"Could you please provide the following information: {items}?"

            # Fallback to agent's content if it looks like a question
            if agent_content and "?" in agent_content:
                return agent_content

            # Generic fallback
            return "Could you please provide more details about your request?"

        except Exception:
            return "Could you please provide more details about your request?"

    async def process_agent_clarification_response(
        self,
        message: str,
        session_id: str,
        user_id: Any,
        request_id: Optional[str] = None
    ) -> Optional[MuxiResponse]:
        """
        Process a response to an agent clarification request.

        Args:
            message: User's response to clarification
            session_id: Session identifier
            user_id: User identifier
            request_id: Optional request identifier

        Returns:
            MuxiResponse if clarification is handled, None to continue normal processing
        """
        clarification_info = await self._get_clarification(session_id) or {}

        if clarification_info.get("type") != "agent_clarification":
            return None

        try:
            agent_name = clarification_info.get("agent_name")
            original_message = clarification_info.get("original_message")

            # Combine original message with clarification response
            enhanced_message = f"{original_message}\n\nAdditional information: {message}"

            # Clear the pending clarification
            await self._delete_clarification(session_id)

            # Re-route to the agent with enhanced message
            if agent_name and hasattr(self.overlord, 'run_agent'):
                return await self.overlord.run_agent(
                    message=enhanced_message,
                    agent_name=agent_name,
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id
                )

            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Failed to process agent clarification response: {str(e)}"
            )
            # Clear the clarification and continue
            await self._delete_clarification(session_id)
            return None

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
        if self.is_token_string(stripped):
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
                # Note: More specific prefixes to avoid false positives
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

    def _redact_tokens_in_message(self, message: str) -> tuple[str, bool]:
        """
        Scan and redact potential tokens in a message.

        Args:
            message: The message to scan for tokens

        Returns:
            Tuple of (redacted message, whether tokens were found)
        """
        if not message or not isinstance(message, str):
            return message, False

        tokens_found = False
        redacted = message

        # Check for known token patterns and redact them
        token_patterns = [
            (r"(ghp_[A-Za-z0-9]{36})", "[REDACTED_GITHUB_TOKEN]"),
            (r"(github_pat_[A-Za-z0-9_]+)", "[REDACTED_GITHUB_PAT]"),
            (r"(ghs_[A-Za-z0-9]{36})", "[REDACTED_GITHUB_SECRET]"),
            (r"(glpat-[A-Za-z0-9\-_]+)", "[REDACTED_GITLAB_TOKEN]"),
            (r"(sk-[A-Za-z0-9]{20,})", "[REDACTED_API_KEY]"),
            (r"(pk-[A-Za-z0-9]{20,})", "[REDACTED_PRIVATE_KEY]"),
            (r"(api-[A-Za-z0-9]{20,})", "[REDACTED_API_KEY]"),
            (r"(key-[A-Za-z0-9]{20,})", "[REDACTED_KEY]"),
        ]

        for pattern, replacement in token_patterns:
            if re.search(pattern, redacted):
                tokens_found = True
                redacted = re.sub(pattern, replacement, redacted)

        # Check if the entire message might be a token
        stripped = message.strip().strip('"').strip("'")
        if self.is_token_string(stripped):
            return "[REDACTED_TOKEN]", True

        # Check for potential tokens using heuristics (long strings without spaces)
        words = redacted.split()
        for i, word in enumerate(words):
            cleaned_word = word.strip().strip('"').strip("'").strip("`").strip(":")
            if len(cleaned_word) >= 20 and " " not in cleaned_word:
                # Check if it matches token-like patterns
                if re.match(r"^[A-Za-z0-9+/\-_]{20,}={0,2}$", cleaned_word):
                    words[i] = "[REDACTED_POTENTIAL_TOKEN]"
                    tokens_found = True
                elif re.match(r"^[A-Fa-f0-9]{32,}$", cleaned_word):
                    words[i] = "[REDACTED_HEX_TOKEN]"
                    tokens_found = True

        if tokens_found:
            redacted = " ".join(words)

        return redacted, tokens_found

    async def extract_token_from_text(self, message: str) -> Optional[str]:
        """
        Extract a credential token from a message using regex and LLM.

        Args:
            message: The message that may contain a token

        Returns:
            The extracted token if found, None otherwise
        """
        if not message or not isinstance(message, str):
            return None

        # First try regex patterns (faster and more reliable)
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

        # If no regex match, try LLM extraction
        # BUT FIRST: Check if message contains potential tokens and redact/skip if so
        try:
            if hasattr(self.overlord, 'routing_model'):
                # Redact any potential tokens from the ENTIRE message first
                redacted_full_message, tokens_found = self._redact_tokens_in_message(message)

                # If tokens were detected, skip LLM fallback to avoid leaking them
                if tokens_found:
                    observability.observe(
                        event_type=observability.SystemEvents.SERVICE_STARTED,
                        level=observability.EventLevel.DEBUG,
                        data={"reason": "potential_tokens_detected", "service": "token_extraction"},
                        description="Skipping LLM token extraction due to detected sensitive content",
                    )
                    return None

                # Now truncate the redacted message for the LLM prompt
                # This ensures no tokens beyond character 300 are leaked
                truncated_message = redacted_full_message[:300]

                prompt = f"""Extract ONLY the API token from this message. If there's no token, reply NONE.

Message: {truncated_message}

Token:"""

                # Use the routing model for extraction
                response = await self.overlord.routing_model.achat(prompt, max_tokens=100, temperature=0)
                extracted = response.content.strip()

                # Check if the LLM found a token
                if extracted and extracted.upper() != "NONE" and len(extracted) >= 10:
                    # Clean up common surrounding characters
                    cleaned = extracted.strip().strip('"').strip("'").strip("`").strip(":")
                    # Verify it looks like a token
                    if " " not in cleaned and len(cleaned) >= 20:
                        return cleaned

        except Exception as e:
            # Log error but don't fail
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.DEBUG,
                data={"error": str(e)},
                description=f"Failed to extract token using LLM: {str(e)}",
            )

        return None

    def is_token_string(self, token: str) -> bool:
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

    async def analyze_clarification_response(
        self, response: str, context: ClarificationContext
    ) -> Dict[str, Any]:
        """
        Use LLM to understand the user's response intent.

        This method analyzes a user's response to a clarification question to determine
        their intent and extract any parameters they provided.

        Args:
            response: The user's response to the clarification question
            context: The current clarification context

        Returns:
            Dictionary with intent analysis results including:
            - intent: ANSWER, REJECT, QUESTION, or CANCEL
            - params: Extracted parameters if any
            - explanation: Brief explanation of the analysis
        """
        try:
            # Get the last question asked if available
            last_question = ""
            if context.clarification_chain:
                last_item = context.clarification_chain[-1]
                last_question = last_item.get("question", "") or last_item.get("param", "")

            prompt = f"""Analyze this clarification response and determine the user's intent.

    Original request: {context.original_intent}
    Current question: {last_question}
    User response: {response}

    Classify the response as ONE of:
    1. ANSWER - User is providing the requested information
    2. REJECT - User is rejecting the options (e.g., "none of these", "different one")
    3. QUESTION - User is asking for clarification about the clarification
    4. CANCEL - User wants to stop/cancel the process

    Also extract any parameters if it's an ANSWER.

    Return in format:
    INTENT: [intent_type]
    PARAMS: [extracted parameters if any]
    EXPLANATION: [brief explanation]
    """

            # No regex, no pattern matching - pure LLM understanding
            if self.clarification and self.clarification.llm:
                result = await self.clarification.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.3
                )

                return self.parse_llm_intent(result.content)
            else:
                # Fallback to simple heuristic if no model available
                return {
                    "intent": "ANSWER",
                    "params": {"response": response},
                    "explanation": "No model available, treating as answer"
                }

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e)},
                description=f"Failed to analyze clarification response: {str(e)}"
            )
            # Default to treating as answer on error
            return {
                "intent": "ANSWER",
                "params": {"response": response},
                "explanation": f"Analysis failed: {str(e)}"
            }

    def parse_llm_intent(self, llm_response: str) -> Dict[str, Any]:
        """Parse the LLM's intent analysis response."""
        lines = llm_response.strip().split("\n")
        result = {
            "intent": "ANSWER",  # Default
            "params": {},
            "explanation": ""
        }

        for line in lines:
            if line.startswith("INTENT:"):
                intent = line.replace("INTENT:", "").strip()
                if intent in ["ANSWER", "REJECT", "QUESTION", "CANCEL"]:
                    result["intent"] = intent
            elif line.startswith("PARAMS:"):
                params_str = line.replace("PARAMS:", "").strip()
                if params_str and params_str != "None":
                    # Try to parse as JSON or key=value pairs
                    try:
                        result["params"] = json.loads(params_str)
                    except Exception:
                        # Fallback to simple parsing
                        result["params"] = {"extracted": params_str}
            elif line.startswith("EXPLANATION:"):
                result["explanation"] = line.replace("EXPLANATION:", "").strip()

        return result

    async def can_fulfill_intent(self, context: ClarificationContext) -> bool:
        """
        Check if we have enough info to fulfill the original intent.

        Delegates to the context's LLM-based can_fulfill method which provides
        language-agnostic assessment of parameter sufficiency.

        Args:
            context: The current clarification context

        Returns:
            True if we can fulfill the intent, False otherwise
        """
        try:
            # Use the overlord's model for assessment
            # According to schema/formation/README.md:
            # - overlord.llm.model takes precedence over formation defaults
            # - If not set, inherits from formation's text LLM model
            llm_model = None

            # The overlord has a proper model resolution that follows the hierarchy:
            # 1. overlord.llm.model (if configured)
            # 2. formation's text model (fallback)
            # Access through _text_model or _capability_models for proper resolution
            if self.overlord:
                # Try to get the overlord's text model (properly resolved)
                if hasattr(self.overlord, '_text_model'):
                    llm_model = self.overlord._text_model
                elif hasattr(self.overlord, '_capability_models') and self.overlord._capability_models:
                    llm_model = self.overlord._capability_models.get('text')
                elif hasattr(self.overlord, 'routing_model'):
                    # Fallback to routing_model if available (legacy)
                    llm_model = self.overlord.routing_model

            # If still no model, try the clarification system's model as last resort
            if not llm_model and self.clarification:
                if hasattr(self.clarification, 'llm'):
                    llm_model = self.clarification.llm

            # If no LLM model is available, we can't properly assess fulfillment
            if not llm_model:
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "session_id": context.session_id,
                        "error": "No LLM model available for fulfillment assessment"
                    },
                    description="Cannot assess fulfillment without LLM model - assuming incomplete"
                )
                # Conservative approach: assume we need more info if no LLM available
                return False

            # Use the context's improved LLM-based method
            # This provides consistent, language-agnostic assessment
            can_fulfill = await context.can_fulfill(llm_model=llm_model)

            # Log the decision for observability
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "session_id": context.session_id,
                    "can_fulfill": can_fulfill,
                    "params_count": len(context.collected_params),
                    "has_llm": llm_model is not None
                },
                description=f"Fulfillment check: {'Ready' if can_fulfill else 'Need more info'}"
            )

            return can_fulfill

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "session_id": context.session_id},
                description=f"Failed to check fulfillment capability: {str(e)}"
            )
            # Conservative: don't fulfill if unsure
            return False

    async def handle_rejection(
        self, message: str, context: ClarificationContext, analysis: Dict[str, Any]
    ) -> MuxiResponse:
        """
        Handle when user rejects options.

        This method handles the case where a user rejects the provided options
        and generates a follow-up clarification to understand their alternative preference.

        Args:
            message: The user's rejection message
            context: The current clarification context
            analysis: The intent analysis results

        Returns:
            MuxiResponse with the follow-up clarification question
        """
        try:
            # Get the last question for context
            last_question = ""
            if context.clarification_chain:
                last_item = context.clarification_chain[-1]
                last_question = last_item.get("question", "") or last_item.get("param", "")

            # Use LLM to understand what they want instead
            prompt = f"""The user rejected the provided options. Understand what they want instead.

    Original request: {context.original_intent}
    Options provided: {last_question}
    User said: {message}

    Generate a follow-up clarification question to understand their alternative preference.
    Be direct and specific.
    """

            if self.clarification and self.clarification.llm:
                question_response = await self.clarification.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.3
                )
                question = question_response.content.strip()
            else:
                question = "What would you like to do instead?"

            # Store as sub-clarification
            context.clarification_chain.append({
                "type": "sub_clarification",
                "parent_question": last_question,
                "question": question,
                "depth": context.depth
            })

            return MuxiResponse(
                content=question,
                metadata={"clarification": True, "depth": context.depth}
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e)},
                description=f"Failed to handle rejection: {str(e)}"
            )
            return MuxiResponse(
                content="I understand you want something different. Could you please specify what you'd like?",
                metadata={"clarification": True, "depth": context.depth}
            )

    async def handle_clarification_response_v2(
        self, message: str, session_id: str
    ) -> Optional[MuxiResponse]:
        """
        Handle clarification response with multi-turn support using ClarificationContext.

        This is the enhanced version that supports multi-turn clarifications,
        rejection handling, and intent preservation.

        Args:
            message: The user's response to a clarification
            session_id: The session identifier

        Returns:
            MuxiResponse with the next action (clarification, fulfillment, etc.)
            None if the clarification should be cleared and normal processing should continue
        """
        # Get or create ClarificationContext
        clarification_info = await self._get_clarification(session_id)
        if not clarification_info:
            return None

        # Check if it's already a ClarificationContext or old format
        if isinstance(clarification_info, ClarificationContext):
            context = clarification_info
        else:
            # Convert old format to new ClarificationContext
            context = ClarificationContext(
                original_intent=clarification_info.get("original_message", ""),
                session_id=session_id
            )
            # Copy existing data
            if "last_question" in clarification_info:
                context.add_qa_pair(
                    clarification_info["last_question"],
                    message,
                    "ANSWER"
                )
            # Replace with new context
            await self._set_clarification(session_id, context)

        # Use LLM to understand response type
        intent_analysis = await self.analyze_clarification_response(message, context)

        if intent_analysis["intent"] == "REJECT":
            # Handle rejection - push sub-clarification
            if not context.is_at_max_depth():
                context.increment_depth()
                return await self.handle_rejection(message, context, intent_analysis)
            else:
                # Too deep, force resolution
                return await self.force_resolution(context)

        elif intent_analysis["intent"] == "ANSWER":
            # Collect parameter
            for key, value in intent_analysis.get("params", {}).items():
                context.add_param(key, value)

            # Add Q&A to chain
            if context.clarification_chain:
                last_q = context.clarification_chain[-1].get("question", "")
                context.add_qa_pair(last_q, message, "ANSWER")

            # Check if we can fulfill
            if await self.can_fulfill_intent(context):
                # Clear clarification and return None to continue with fulfillment
                await self._delete_clarification(session_id)
                # Return None means continue processing with the combined message
                return None
            else:
                # Need more info
                return await self.ask_next_clarification(context)

        elif intent_analysis["intent"] == "QUESTION":
            # User asking for help with clarification
            return await self.provide_clarification_help(message, context)

        elif intent_analysis["intent"] == "CANCEL":
            # User cancelling
            await self._delete_clarification(session_id)
            return MuxiResponse(
                content="Understood, I've cancelled the clarification process.",
                metadata={"clarification_cancelled": True}
            )

        # Default: treat as answer
        return None

    async def force_resolution(self, context: ClarificationContext) -> MuxiResponse:
        """Force resolution when clarification depth limit is reached."""
        return MuxiResponse(
            content=(
                "I understand you're looking for something specific. "
                "Let me try to help with what information we have so far."
            ),
            metadata={"forced_resolution": True}
        )

    async def ask_next_clarification(self, context: ClarificationContext) -> MuxiResponse:
        """Ask the next clarification question based on collected params."""
        # This would be enhanced to intelligently determine what's still needed
        return MuxiResponse(
            content="Could you provide more details about what you'd like to do?",
            metadata={"clarification": True, "depth": context.depth}
        )

    async def provide_clarification_help(
        self, message: str, context: ClarificationContext
    ) -> MuxiResponse:
        """Provide help when user asks about the clarification itself."""
        return MuxiResponse(
            content=(
                "I'm trying to understand your request better. "
                "Could you please provide the information I asked about, "
                "or let me know if you'd like to do something different?"
            ),
            metadata={"clarification_help": True}
        )

    async def cleanup_stale_clarifications(self) -> None:
        """
        Clean up stale pending clarifications based on TTL.

        This method runs periodically to remove clarifications that have
        exceeded their TTL, preventing memory growth from abandoned or
        failed clarification flows.

        The method properly handles shutdown signals via asyncio.CancelledError
        for clean and prompt termination.
        """
        try:
            # Check shutting down flag in while condition for immediate exit
            while not (hasattr(self.overlord, '_shutting_down') and self.overlord._shutting_down):
                try:
                    # Sleep for cleanup interval - will raise CancelledError if task is cancelled
                    await asyncio.sleep(self._clarification_cleanup_interval_seconds)

                    # Re-check shutdown flag after sleep to exit immediately if shutdown started
                    if hasattr(self.overlord, '_shutting_down') and self.overlord._shutting_down:
                        break

                    current_time = time.time()
                    stale_sessions = []

                    # Create a snapshot of items to avoid RuntimeError during iteration
                    # This prevents issues if the dictionary is modified concurrently
                    pending_items = await self._get_all_clarifications()

                    # Find stale clarifications
                    for session_id, clarification_info in pending_items:
                        # Handle both old format and ClarificationContext
                        if isinstance(clarification_info, ClarificationContext):
                            timestamp = clarification_info.timestamp.timestamp() if clarification_info.timestamp else 0
                        else:
                            timestamp = clarification_info.get("timestamp", 0)

                        age_seconds = current_time - timestamp

                        if age_seconds > self._clarification_ttl_seconds:
                            stale_sessions.append(session_id)

                            observability.observe(
                                event_type=observability.SystemEvents.CLEANUP,
                                level=observability.EventLevel.INFO,
                                data={
                                    "session_id": session_id,
                                    "age_seconds": age_seconds,
                                    "ttl_seconds": self._clarification_ttl_seconds,
                                },
                                description=f"Removing stale clarification for session {session_id}",
                            )

                    # Remove stale entries (safe to modify now since we're not iterating)
                    for session_id in stale_sessions:
                        # Check if still exists before deletion (in case it was removed elsewhere)
                        await self._delete_clarification(session_id)

                    if stale_sessions:
                        observability.observe(
                            event_type=observability.SystemEvents.CLEANUP,
                            level=observability.EventLevel.INFO,
                            data={
                                "removed_count": len(stale_sessions),
                                "remaining_count": len(self._pending_clarifications),
                            },
                            description=f"Cleaned up {len(stale_sessions)} stale clarifications",
                        )

                except asyncio.CancelledError:
                    # Task was cancelled (likely due to shutdown) - clean exit
                    observability.observe(
                        event_type=observability.SystemEvents.CLEANUP,
                        level=observability.EventLevel.INFO,
                        description="Clarification cleanup task cancelled - shutting down cleanly",
                    )
                    raise  # Re-raise to properly propagate cancellation

                except Exception as e:
                    # Log error but continue cleanup loop
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"error": str(e)},
                        description=f"Error during clarification cleanup: {str(e)}",
                    )

        except asyncio.CancelledError:
            # Clean exit on cancellation
            pass
        finally:
            # Log cleanup task termination
            observability.observe(
                event_type=observability.SystemEvents.CLEANUP,
                level=observability.EventLevel.DEBUG,
                description="Clarification cleanup task terminated",
            )

    async def check_clarification_needs_async(
        self,
        message: str,
        user_id: Any,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Check if clarification is needed for an async request.

        Args:
            message: User message
            user_id: User identifier
            session_id: Optional session identifier
            request_id: Request identifier

        Returns:
            Tuple of (clarification_question, request_id) if clarification needed, None otherwise
        """
        if not self.clarification or not session_id:
            return None

        try:
            # Use the unified clarification system to check if clarification is needed
            context = {"user_id": user_id} if user_id else {}

            clarification_result = await self.clarification.needs_clarification(
                message=message,
                request_id=request_id,
                session_id=session_id,
                context=context
            )

            if clarification_result.action == "clarify":
                # Update request status to awaiting clarification
                if self.request_tracker:
                    await self.request_tracker.update_status(
                        request_id,
                        RequestStatus.AWAITING_CLARIFICATION,
                        clarification_question=clarification_result.question
                    )

                # Store pending clarification
                await self._set_clarification(session_id, {
                    "type": "async_clarification",
                    "request_id": request_id,
                    "original_message": message,
                    "mode": clarification_result.mode,
                    "user_id": user_id,
                    "created_at": time.time(),
                })

                return (clarification_result.question, request_id)

            return None

        except Exception as e:
            # Log error but don't block processing
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e)},
                description=f"Failed to check async clarification needs: {str(e)}",
            )
            return None

    async def process_async_clarification_response(
        self, request_id: str, clarification_response: str
    ) -> bool:
        """
        Process clarification response for an async request.

        Args:
            request_id: The async request ID awaiting clarification
            clarification_response: User's response to the clarification question

        Returns:
            True if processing was successfully resumed, False otherwise
        """
        try:
            # Get the request state
            request_state = await self.request_tracker.get_request(request_id)
            if not request_state:
                return False

            if request_state.status != RequestStatus.AWAITING_CLARIFICATION:
                return False

            # Store user's clarification response in buffer memory
            try:
                if hasattr(self.overlord, 'add_message_to_memory'):
                    await self.overlord.add_message_to_memory(
                        content=clarification_response,
                        role="user",
                        timestamp=time.time(),
                        agent_id="overlord",
                        user_id=request_state.user_id,
                        session_id=request_state.session_id,
                        request_id=request_id,
                    )
            except Exception:
                pass  # Continue even if memory storage fails

            # Get the original message and combine with clarification
            original_message = request_state.original_request or ""

            # Combine messages for processing
            enhanced_message = f"{original_message}\n\nAdditional information: {clarification_response}"

            # Update request status to processing
            await self.request_tracker.update_status(request_id, RequestStatus.PROCESSING)

            # Clear pending clarification
            if request_state.session_id:
                await self._delete_clarification(request_state.session_id)

            # Resume processing with enhanced message
            # This will be handled by the overlord's async processing
            asyncio.create_task(
                self.overlord._process_async_chat(
                    message=enhanced_message,
                    agent_name=request_state.agent_name,
                    user_id=request_state.user_id,
                    session_id=request_state.session_id,
                    request_id=request_id,
                )
            )

            return True

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "request_id": request_id},
                description=f"Failed to process async clarification response: {str(e)}",
            )
            return False
