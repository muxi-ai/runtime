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
from ..clarification import ClarificationContext
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
        self.clarification_analyzer = overlord.clarification_analyzer
        self.clarification_manager = overlord.clarification_manager
        self.clarification_question_generator = overlord.clarification_question_generator
        self.request_tracker = overlord.request_tracker

        # Configuration
        self._clarification_ttl_seconds = getattr(overlord, '_clarification_ttl_seconds', 3600)
        self._clarification_cleanup_interval_seconds = getattr(overlord, '_clarification_cleanup_interval_seconds', 300)

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
                self._pending_clarifications[session_id] = {
                    "type": "agent_clarification",
                    "agent_name": agent_name,
                    "original_message": original_message,
                    "metadata": clarification_metadata,
                    "timestamp": time.time(),
                    "user_id": user_id,
                }

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
        clarification_info = self._pending_clarifications.get(session_id, {})

        if clarification_info.get("type") != "agent_clarification":
            return None

        try:
            agent_name = clarification_info.get("agent_name")
            original_message = clarification_info.get("original_message")

            # Combine original message with clarification response
            enhanced_message = f"{original_message}\n\nAdditional information: {message}"

            # Clear the pending clarification
            del self._pending_clarifications[session_id]

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
            if session_id in self._pending_clarifications:
                del self._pending_clarifications[session_id]
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

        # Additional heuristic: long string without spaces
        # Basic heuristic: no spaces and reasonable length
        if " " not in stripped and 20 <= len(stripped) <= 200:
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
                # Redact any potential tokens before sending to LLM
                redacted_message, tokens_found = self._redact_tokens_in_message(message[:300])

                # If tokens were detected, skip LLM fallback to avoid leaking them
                if tokens_found:
                    observability.observe(
                        event_type=observability.EventEvents.AGENT_EVENT,
                        level=observability.EventLevel.DEBUG,
                        data={"reason": "potential_tokens_detected"},
                        description="Skipping LLM token extraction due to detected sensitive content",
                    )
                    return None

                prompt = f"""Extract ONLY the API token from this message. If there's no token, reply NONE.

Message: {redacted_message}

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
            if self.clarification_analyzer and self.clarification_analyzer.model:
                result = await self.clarification_analyzer.model.chat(
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

        Uses LLM to determine if the collected parameters are sufficient
        to fulfill the original user request.

        Args:
            context: The current clarification context

        Returns:
            True if we can fulfill the intent, False otherwise
        """
        try:
            # First try simple heuristic
            if not context.collected_params:
                return False

            # Use LLM for complex cases
            prompt = f"""Determine if we have enough information to fulfill this request.

    Original request: {context.original_intent}
    Collected parameters: {json.dumps(context.collected_params)}

    Can we proceed with fulfilling this request? Consider:
    - Do we have the minimum required information?
    - Can missing parameters use reasonable defaults?

    Return: YES or NO with brief explanation
    """

            if self.clarification_analyzer and self.clarification_analyzer.model:
                result = await self.clarification_analyzer.model.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0.3
                )

                return "YES" in result.content.upper()
            else:
                # Fallback: if we have any params, assume we can try
                return len(context.collected_params) > 0

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"error": str(e)},
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

            if self.clarification_analyzer and self.clarification_analyzer.model:
                question_response = await self.clarification_analyzer.model.chat(
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
        clarification_info = self._pending_clarifications.get(session_id)
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
            self._pending_clarifications[session_id] = context

        # Use LLM to understand response type
        intent_analysis = await self.analyze_clarification_response(message, context)

        if intent_analysis["intent"] == "REJECT":
            # Handle rejection - push sub-clarification
            if context.depth < 2:  # Max 2 levels
                context.depth += 1
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
                del self._pending_clarifications[session_id]
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
            del self._pending_clarifications[session_id]
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
        """
        while True:
            try:
                # Sleep for cleanup interval
                await asyncio.sleep(self._clarification_cleanup_interval_seconds)

                current_time = time.time()
                stale_sessions = []

                # Create a snapshot of items to avoid RuntimeError during iteration
                # This prevents issues if the dictionary is modified concurrently
                pending_items = list(self._pending_clarifications.items())

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
                    if session_id in self._pending_clarifications:
                        del self._pending_clarifications[session_id]

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

            except Exception as e:
                # Log error but continue cleanup loop
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e)},
                    description=f"Error during clarification cleanup: {str(e)}",
                )

            # Safety check: break if overlord is shutting down
            if hasattr(self.overlord, '_shutting_down') and self.overlord._shutting_down:
                break

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
        if not self.clarification_analyzer or not session_id:
            return None

        try:
            # Analyze for missing information
            user_context = {}
            if hasattr(self.overlord, 'user_context_manager'):
                user_context = await self.overlord.user_context_manager.get_user_context(user_id)

            available_tools = []
            if hasattr(self.overlord, 'mcp_coordinator'):
                tool_registry = self.overlord.mcp_coordinator.get_tool_registry()
                for server_tools in tool_registry.values():
                    available_tools.extend(server_tools.keys())

            analysis_result = await self.clarification_analyzer.analyze_request(
                user_message=message,
                intent="general",
                available_tools=available_tools,
                user_context=user_context,
            )

            if analysis_result and analysis_result.missing_info:
                # Generate clarification question
                question = "Could you please provide more details?"
                if self.clarification_question_generator:
                    missing_context = (
                        analysis_result.missing_info[0]
                        if analysis_result.missing_info
                        else "more details"
                    )
                    question_obj = await self.clarification_question_generator.generate_reasoning_question(
                        intent="general",
                        missing_context=missing_context,
                        user_background={},
                    )
                    question = question_obj.question_text

                # Update request status to awaiting clarification
                if self.request_tracker:
                    await self.request_tracker.update_status(
                        request_id, RequestStatus.AWAITING_CLARIFICATION, clarification_question=question
                    )

                # Store pending clarification
                self._pending_clarifications[session_id] = {
                    "type": "async_clarification",
                    "request_id": request_id,
                    "original_message": message,
                    "missing_info": analysis_result.missing_info,
                    "user_id": user_id,
                    "created_at": time.time(),
                }

                return (question, request_id)

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
            if request_state.session_id and request_state.session_id in self._pending_clarifications:
                del self._pending_clarifications[request_state.session_id]

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
