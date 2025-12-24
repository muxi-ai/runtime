import time
import json
import re
from typing import Dict, Optional
from dataclasses import dataclass

from ...services import observability


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
        self.clarification_config = (
            overlord.clarification_config if hasattr(overlord, "clarification_config") else None
        )

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

    async def handle_credential_error(self, error, request_id: str) -> ClarificationResult:
        """
        Handle AmbiguousCredentialError from MCP service.
        Creates credential selection clarification and stores state.

        Args:
            error: AmbiguousCredentialError with service, user_id, available_credentials
            request_id: Request ID for tracking

        Returns:
            ClarificationResult with action="clarify" and credential selection question
        """
        # Extract account names from available_credentials
        available_accounts = []
        if error.available_credentials:
            for cred in error.available_credentials:
                if isinstance(cred, dict):
                    available_accounts.append(cred.get("name", ""))
                elif isinstance(cred, str):
                    available_accounts.append(cred)

        # Format service name nicely
        service_display = error.service.capitalize()
        if error.service == "github":
            service_display = "GitHub"

        # Reorder accounts according to ordered_credentials if provided
        # ordered_credentials contains 1-based indices indicating preferred order
        # Example: [2, 1] means show credential #2 first, then credential #1
        display_accounts = available_accounts.copy()
        if hasattr(error, "ordered_credentials") and error.ordered_credentials:
            try:
                # Reorder using the indices (convert from 1-based to 0-based)
                display_accounts = [
                    available_accounts[idx - 1]
                    for idx in error.ordered_credentials
                    if 0 < idx <= len(available_accounts)
                ]
            except (IndexError, TypeError):
                # If reordering fails, use original order
                pass

        # Build the clarification question
        options_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(display_accounts)])
        question = (
            f"I found multiple {service_display} accounts for you. "
            f"Which account would you like to use?\n\n"
            f"Available accounts:\n{options_text}"
        )

        # Store state for credential mode
        state = {
            "request_id": request_id,
            "type": "ambiguous_credential",  # For overlord handler routing
            "mode": "credential",
            "service": error.service,  # Store as 'service' for overlord compatibility
            "mcp_service": error.service,
            "user_id": error.user_id,
            "available_credentials": error.available_credentials,  # Store full credentials
            "available_accounts": available_accounts,
            "original_request": "credential_selection",  # Will be updated by overlord
            "collected_info": [],
            "depth": 0,
            "max_depth": 1,  # Only one round for credential selection
            "started_at": time.time(),
        }

        await self._store_state(request_id, state)

        return ClarificationResult(action="clarify", question=question, mode="credential")

    async def handle_mcp_credential_request(
        self, service_id: str, user_id: str, request_id: str
    ) -> ClarificationResult:
        """
        Handle MissingCredentialError from MCP service.
        Creates redirect or dynamic credential request based on formation config.

        Args:
            service_id: Service that needs credentials (e.g., "github")
            user_id: User ID requesting access
            request_id: Request ID for tracking

        Returns:
            ClarificationResult with redirect message or dynamic credential prompt
        """
        # Format service name nicely
        service_display = service_id.capitalize()
        if service_id == "github":
            service_display = "GitHub"

        # Return redirect message with clarify action so we can detect help requests
        redirect_message = (
            f"For security, {service_display} credentials must be configured outside of this chat interface.\n"
            f"Please use your organization's credential management system to set up authentication.\n\n"
            f"(If you need help obtaining credentials, just ask!)"
        )

        return ClarificationResult(action="clarify", question=redirect_message, mode="redirect")

    async def needs_clarification(
        self, message: str, request_id: str, session_id: str = None, context: Optional[Dict] = None
    ) -> ClarificationResult:
        """
        Main entry point - analyzes if clarification is needed.
        Uses request_id as primary identifier.
        """
        # Check for existing clarification

        has_active = await self.has_active_clarification(request_id)

        if has_active:
            return await self.handle_response(request_id, message)

        # Analyze new request
        analysis = await self._analyze_request(message, context or {})

        if analysis["needs_clarification"]:
            # Start clarification - store in buffer memory
            await self._create_state(request_id, message, analysis["mode"], session_id)
            # Store the question we're asking and MCP service if detected
            state = await self._get_state(request_id)
            if state:
                state["last_question"] = analysis["question"]
                # Store MCP service if detected
                if analysis.get("mcp_service"):
                    state["mcp_service"] = analysis["mcp_service"]
                # Store user_id from context
                if context and context.get("user_id"):
                    state["user_id"] = context["user_id"]
                # Store available accounts if we found any
                if analysis.get("available_accounts"):
                    state["available_accounts"] = analysis["available_accounts"]
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

        # Special handling for redirect mode (missing credentials)
        if state.get("mode") == "redirect":
            # Check if user is asking for help
            if self._is_help_request(response):
                help_result = await self._provide_credential_help(state)
                # Update state to track we provided help
                state["help_provided"] = True
                await self._store_state(request_id, state)
                return help_result
            else:
                # User is presumably providing credentials or continuing
                # Clean up and let them proceed
                await self._cleanup_state(request_id)
                return ClarificationResult(
                    action="execute",
                    request=state.get("original_request", response),
                    context={"credential_configured": True},
                )

        # Special handling for credential selection mode
        if state.get("mode") == "credential" and state.get("available_accounts"):
            # First check if user is asking for help
            if self._is_help_request(response):
                return await self._provide_credential_help(state)

            selected_account = await self._parse_credential_selection(
                response, state["available_accounts"]
            )

            if selected_account:
                # Store the selected account in state
                state["selected_account"] = selected_account
                await self._store_state(request_id, state)

                # Build enhanced request and cleanup
                enhanced = self._build_enhanced_request(state)
                await self._cleanup_state(request_id)

                return ClarificationResult(
                    action="execute",
                    request=enhanced,
                    context={
                        "mcp_service": state.get("mcp_service"),
                        "selected_account": selected_account,
                        "user_id": state.get("user_id"),
                        "original_request": state.get("original_request"),
                    },
                )
            else:
                # Selection parsing failed - ask again
                return ClarificationResult(
                    action="clarify",
                    question="I couldn't understand your selection. Please specify the account by name or number.",
                    mode="credential",
                )

        # Update state for non-credential clarifications
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
        try:
            await self.buffer_memory.kv_set(
                key=key,
                value=state,
                ttl=None,  # No TTL - let FIFO handle cleanup
                namespace=self.namespace,
            )
            self.active_requests.add(request_id)
        except Exception as e:
            # Log the error with context
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "request_id": request_id,
                    "key": key,
                    "namespace": self.namespace,
                },
                description=f"Failed to store clarification state in buffer memory: {str(e)}",
            )

            # Fallback to in-memory storage
            if not hasattr(self, "_fallback_storage"):
                self._fallback_storage = {}
            self._fallback_storage[request_id] = state
            self.active_requests.add(request_id)
            return

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

        CRITICAL: Check for recall questions FIRST and search memory before asking for clarification.
        """
        # STEP 1: Check for recall questions and search memory
        # If this is a recall question (e.g., "What is my X?") and memory has the answer, skip clarification
        if await self._is_recall_question_with_answer(message, context):
            return {
                "needs_clarification": False,
                "reason": "recall_question_answered_from_memory",
                "mode": "direct",
                "question": None,
                "confidence": 1.0,
                "mcp_service": None,
            }

        # STEP 2: Continue with normal clarification analysis
        # Get formation capabilities (pre-computed during overlord initialization)
        capabilities = getattr(self.overlord, "capabilities", [])
        mcp_servers = getattr(self.overlord, "mcp_servers", [])

        # Build detailed MCP services description from formation config
        mcp_services_detail = []
        if hasattr(self.overlord, "formation_config") and self.overlord.formation_config:
            mcp_config = self.overlord.formation_config.get("mcp", {})
            servers_config = mcp_config.get("servers", [])

            for server in servers_config:
                # Get id and description from the YAML configuration
                server_id = server.get("id", "unknown")
                description = server.get("description", server_id)
                mcp_services_detail.append(f"- {server_id}: {description}")

        # Fallback if no config available
        if not mcp_services_detail and mcp_servers:
            mcp_services_detail = [f"- {s}" for s in mcp_servers]

        # Get credential handling configuration
        cred_config = (
            self.overlord.formation_config.get("user_credentials", {})
            if hasattr(self.overlord, "formation_config") and self.overlord.formation_config
            else {}
        )
        cred_mode = cred_config.get("mode", "redirect")
        redirect_message = cred_config.get(
            "redirect_message",
            "Please configure your API credentials in the external credential manager.",
        )

        # Get response style
        response_style = {
            "conversational": "natural, friendly, like a helpful colleague",
            "technical": "precise, specific, professional",
            "brief": "very concise, minimal words",
        }.get(self.style, "natural, friendly, like a helpful colleague")

        # Extract conversation for clarification analysis
        # IMPORTANT: Always include the current request + context for proper analysis
        if "=== CURRENT REQUEST ===" in message:
            # Use the full enhanced message - it has current request first, then context
            # This ensures the LLM sees both the current question AND history
            conversation = message
            # Extract just the current user message for cache differentiation
            current_message = message
            lines = message.split("\n")
            for i, line in enumerate(lines):
                if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.startswith("User:"):
                        current_message = next_line[5:].strip()
                        break
        else:
            # Fallback to raw message
            conversation = f"User: {message}"
            current_message = message

        # Check for available credentials for each MCP service BEFORE calling LLM
        # This allows the LLM to know when multiple credentials exist
        user_id = context.get("user_id", "0") if context else "0"
        credential_info = []

        if hasattr(self.overlord, "credential_resolver") and mcp_servers:
            for service in mcp_servers:
                try:
                    credentials = await self.overlord.credential_resolver.resolve(user_id, service)
                    if credentials:
                        # Handle both single credential (dict) and multiple credentials (list)
                        if isinstance(credentials, list):
                            account_names = [
                                cred.get("name", f"Account {i+1}")
                                for i, cred in enumerate(credentials)
                            ]
                            credential_info.append(
                                f"{service}: {len(credentials)} account(s) - {', '.join(account_names)}"
                            )
                        elif isinstance(credentials, dict) and credentials.get("name"):
                            # Single named credential
                            credential_info.append(
                                f"{service}: 1 account - {credentials.get('name')}"
                            )
                except Exception:
                    # Silently continue if credential check fails
                    pass

        available_credentials = (
            "\n".join(credential_info) if credential_info else "No credentials configured"
        )

        from ..prompts.loader import PromptLoader

        system_prompt = PromptLoader.get(
            "clarification_analysis.md",
            conversation=conversation,  # Full conversation history for context
            context=json.dumps(context) if context else "{}",
            capabilities=", ".join(capabilities) if capabilities else "Conversation",
            mcp_services="\n".join(mcp_services_detail) if mcp_services_detail else "None",
            available_credentials=available_credentials,
            response_style=response_style,
            cred_mode=cred_mode,
            redirect_message=(
                redirect_message if cred_mode == "redirect" else "Please provide your credential"
            ),
        )
        if not self.llm:
            # Fallback when no LLM available
            return {
                "needs_clarification": False,
                "reason": "no_llm",
                "mode": "direct",
                "question": None,
                "confidence": 0.0,
                "mcp_service": None,
            }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": current_message},  # Just current message for cache
        ]

        # Bypass cache if file processing results are present in the conversation
        # This prevents cached clarification responses from being returned when files are attached
        # Check for both the marker and the content prefix
        has_file_results = "FILE PROCESSING RESULTS" in conversation or "[File Processing Result]" in conversation
        response = await self.llm.chat(
            messages, temperature=0, max_tokens=250, caching=not has_file_results
        )
        
        # Check cancellation after LLM call
        from ..background.cancellation import check_cancellation_from_context
        if hasattr(self.overlord, "request_tracker"):
            await check_cancellation_from_context(self.overlord.request_tracker)
        
        content = response.content if hasattr(response, "content") else str(response)

        # Parse JSON
        try:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            result = json.loads(json_str)

            # If an MCP service was detected and needs clarification, check for available credentials
            if result.get("needs_clarification") and result.get("mcp_service"):
                mcp_service = result["mcp_service"]
                # Extract user_id from context or message
                user_id = context.get("user_id", "0") if context else "0"

                # Check if we have credential resolver to get available accounts
                available_accounts = []
                if hasattr(self.overlord, "credential_resolver"):
                    try:
                        credentials = await self.overlord.credential_resolver.resolve(
                            user_id, mcp_service
                        )
                        if credentials:
                            if isinstance(credentials, list):
                                available_accounts = [
                                    cred.get("name", f"Account {i+1}")
                                    for i, cred in enumerate(credentials)
                                ]
                            elif isinstance(credentials, dict) and credentials.get("name"):
                                available_accounts = [credentials.get("name")]
                    except Exception as e:
                        # Log the error for debugging
                        observability.observe(
                            event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                            level=observability.EventLevel.WARNING,
                            data={
                                "error": str(e),
                                "user_id": user_id,
                                "service": mcp_service,
                            },
                            description=f"Failed to get credentials for {mcp_service}: {e}",
                        )

                # If we have available accounts, include them in the question
                if available_accounts:
                    # Re-generate the question with available accounts
                    account_list = ", ".join(available_accounts[:-1])
                    if len(available_accounts) > 1:
                        account_list = f"{account_list} or {available_accounts[-1]}"
                    else:
                        account_list = available_accounts[0]

                    # Update the question to include available accounts
                    base_question = result.get(
                        "question", f"Which {mcp_service} account would you like to use?"
                    )
                    result["question"] = f"{base_question.rstrip('?')}? Available: {account_list}"
                    result["available_accounts"] = available_accounts

            return result
        except Exception:
            # Fallback if JSON parsing fails
            return {
                "needs_clarification": False,
                "reason": "clear",
                "mode": "direct",
                "question": None,
                "confidence": 0.5,
                "mcp_service": None,
            }

    async def _check_need_more(self, state: Dict) -> Dict:
        """
        Check if we need more clarification.
        """
        if not self.llm:
            # Fallback when no LLM available
            return {"needs_more": False, "question": None}

        from ..prompts.loader import PromptLoader

        system_prompt = PromptLoader.get(
            "clarification_need_more.md",
            original_request=state["original_request"],
            collected_info=state["collected_info"],
            mode=state["mode"],
            style=self.style,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Collected info: {state['collected_info']}"},
        ]
        response = await self.llm.chat(messages, temperature=0, max_tokens=150)
        
        # Check cancellation after LLM call
        from ..background.cancellation import check_cancellation_from_context
        if hasattr(self.overlord, "request_tracker"):
            await check_cancellation_from_context(self.overlord.request_tracker)
        
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

        from ..prompts.loader import PromptLoader

        system_prompt = PromptLoader.get(
            "clarification_context_switch.md",
            original_request=state["original_request"],
            last_question=last_question,
            response=response,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User response: {response}"},
        ]
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

        system_prompt = """Does this response indicate the user wants to stop clarification?

Look for phrases like "enough", "just do it", "stop asking", "never mind", etc.

Return just "true" or "false"."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": response},
        ]
        result = await self.llm.chat(messages, temperature=0, max_tokens=10)
        content = result.content if hasattr(result, "content") else str(result)
        return "true" in content.lower()

    def _is_help_request(self, response: str) -> bool:
        """
        Detect if user is asking for help instead of providing a credential.

        Args:
            response: User's response

        Returns:
            True if this appears to be a help request
        """
        help_patterns = [
            "how do i",
            "how to",
            "help",
            "don't know",
            "dont know",
            "what is",
            "where do i",
            "where can i",
            "can you help",
            "need help",
            "not sure",
        ]

        response_lower = response.lower()
        return any(pattern in response_lower for pattern in help_patterns)

    async def _provide_credential_help(self, state: Dict) -> ClarificationResult:
        """
        Provide helpful guidance for obtaining credentials.

        Args:
            state: Current clarification state

        Returns:
            ClarificationResult with help guidance
        """
        mcp_service = state.get("mcp_service", "")

        # Service-specific help messages
        help_messages = {
            "github": """To get a GitHub token:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Give it a name (e.g., "MUXI Runtime")
4. Select scopes: 'repo', 'read:user', 'user:email'
5. Click "Generate token"
6. Copy the token and configure it in your credential manager

After setting up your token, you can use it with MUXI.""",
            "linear": """To get a Linear API key:
1. Go to https://linear.app/settings/api
2. Click "Create key"
3. Give it a description (e.g., "MUXI Runtime")
4. Copy the API key
5. Configure it in your credential manager

After setting up your API key, you can use it with MUXI.""",
        }

        # Get service-specific help or generic help
        help_text = help_messages.get(
            mcp_service,
            f"""To configure credentials for {mcp_service}:
1. Obtain an API key or token from the service's settings
2. Configure it in your credential manager
3. You can then use it with MUXI

Please check {mcp_service}'s documentation for specific instructions on obtaining credentials.""",
        )

        # Return help as clarification (stay in credential mode)
        return ClarificationResult(
            action="clarify",
            question=help_text,
            mode="credential",
        )

    async def _parse_credential_selection(
        self, response: str, available_accounts: list
    ) -> Optional[str]:
        """
        Parse user's credential selection from response.
        Handles both numeric selection (1, 2) and name-based selection (lily, ranaroussi).

        Args:
            response: User's response to credential question
            available_accounts: List of available account names

        Returns:
            Selected account name or None if parsing failed
        """
        import re

        # Clean the response
        response_clean = response.strip()

        # Try numeric selection first (1, 2, etc.)
        numbers = re.findall(r"\b(\d+)\b", response_clean)
        if numbers:
            try:
                choice_index = int(numbers[0]) - 1  # Convert to 0-based index
                if 0 <= choice_index < len(available_accounts):
                    return available_accounts[choice_index]
            except (ValueError, IndexError):
                pass

        # Try name-based selection (fuzzy match)
        response_lower = response_clean.lower()
        for account in available_accounts:
            account_lower = account.lower()
            # Check if account name is in response or vice versa
            if account_lower in response_lower or response_lower in account_lower:
                return account

        # No match found
        return None

    def _build_enhanced_request(self, state: Dict) -> str:
        """
        Build enhanced request from original + collected info.
        """
        if state["mode"] == "credential":
            # For credential selection, return the original request
            # The actual credential caching is handled by the caller using context
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
            "other": 3,
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
            if any(
                pattern in lower_stripped
                for pattern in [
                    "product_id",
                    "user_id",
                    "session_id",
                    "request_id",
                    "order_id",
                    "transaction_id",
                    "customer_id",
                    "account_id",
                    "invoice_id",
                    "http://",
                    "https://",
                    ".com",
                    ".org",
                    ".net",  # URLs
                ]
            ):
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
                    lower_stripped.startswith(prefix)
                    for prefix in [
                        "key_",
                        "token_",
                        "api_",
                        "apikey",
                        "secret_",
                        "password",
                        "bearer",
                        "access_token",
                        "private_",
                        "auth_",
                    ]
                ) or any(
                    # Exact match for short prefixes to avoid false positives
                    lower_stripped == prefix or lower_stripped.startswith(prefix + "-")
                    for prefix in ["key", "token", "api", "secret", "auth"]
                )

                # Check for high entropy (mix of upper, lower, digits, special chars)
                has_upper = any(c.isupper() for c in stripped)
                has_lower = any(c.islower() for c in stripped)
                has_special = any(c in "-_+/=" for c in stripped)
                high_entropy = sum([has_upper, has_lower, has_digit, has_special]) >= 3

                # Return True only if it strongly resembles a credential
                # Require at least TWO indicators to reduce false positives
                indicators = sum([has_case_transition, has_credential_prefix, high_entropy])
                if indicators >= 2 or (has_credential_prefix and len(stripped) >= 32):
                    return True

        return False

    def can_accept_inline(self, auth_type: str, accept_inline: bool) -> bool:
        """
        Determine if a credential can be accepted inline based on auth type.

        Args:
            auth_type: The authentication type (api_key, basic, bearer, oauth, etc.)
            accept_inline: Service hint about whether inline acceptance is allowed

        Returns:
            True if the credential can be accepted inline, False otherwise
        """
        if auth_type == "api_key":
            return True  # API keys are always safe to accept inline

        if auth_type == "basic":
            return True  # Basic auth accepted but with security warning

        if auth_type == "bearer" and accept_inline:
            return True  # Bearer tokens only if service explicitly allows (e.g., PATs)

        if auth_type in ["oauth", "oauth2", "oauth2_flow"]:
            return False  # OAuth flows always require redirect

        # Default to redirect for unknown auth types
        return False

    async def request_inline_credential(
        self, service_id: str, auth_type: str, request_id: str
    ) -> str:
        """
        Generate a prompt for inline credential collection with appropriate warnings.

        Args:
            service_id: The service requesting credentials
            auth_type: The authentication type
            request_id: The current request ID

        Returns:
            A prompt string with appropriate security warnings
        """
        base_prompt = f"Please provide the {auth_type} for '{service_id}':"

        if auth_type == "basic":
            # Add security warning for basic auth
            return (
                "⚠️ Security Warning: Basic authentication transmits credentials in a reversible format.\n"
                "Only provide these credentials if you trust this environment.\n\n"
                f"{base_prompt}\n"
                "Format: username:password"
            )

        if auth_type == "api_key":
            return f"{base_prompt}\n\nNote: Your API key will be securely stored for this session."

        if auth_type == "bearer":
            return f"{base_prompt}\n\n" "Please provide your personal access token or bearer token."

        # Generic prompt for other types
        return base_prompt

    async def _get_service_auth_type(self, service_id: str) -> str:
        """
        Get the authentication type for a service.

        Args:
            service_id: The service identifier

        Returns:
            The authentication type string (defaults to 'unknown')
        """
        # Try to get from formation's mcp_servers list first
        if hasattr(self.overlord, "formation") and hasattr(self.overlord.formation, "mcp_servers"):
            for server in self.overlord.formation.mcp_servers:
                if server.get("id") == service_id:
                    auth = server.get("auth", {})
                    return auth.get("type", "unknown")

        # Try to get from MCP registry if available
        if hasattr(self.overlord, "mcp_registry"):
            service = self.overlord.mcp_registry.get(service_id)
            if service and hasattr(service, "auth"):
                return service.auth.get("type", "unknown")

        # Try to get from MCP coordinator
        if hasattr(self.overlord, "mcp_coordinator"):
            # Access service configuration
            if hasattr(self.overlord.mcp_coordinator, "config"):
                services = getattr(self.overlord.mcp_coordinator.config, "services", {})
                if service_id in services:
                    service_config = services[service_id]
                    if "auth" in service_config:
                        return service_config["auth"].get("type", "unknown")

        return "unknown"

    async def _get_service_accept_inline(self, service_id: str) -> bool:
        """
        Check if a service accepts inline credential collection.

        Args:
            service_id: The service identifier

        Returns:
            True if the service accepts inline credentials, False otherwise
        """
        # Check formation's mcp_servers FIRST (most direct source)
        if hasattr(self.overlord, "formation") and hasattr(self.overlord.formation, "mcp_servers"):
            for server in self.overlord.formation.mcp_servers:
                if server.get("id") == service_id:
                    auth = server.get("auth", {})
                    return auth.get("accept_inline", False)

        # Try to get from MCP registry if available
        if hasattr(self.overlord, "mcp_registry"):
            service = self.overlord.mcp_registry.get(service_id)
            if service and hasattr(service, "auth"):
                return service.auth.get("accept_inline", False)

        # Try to get from MCP coordinator
        if hasattr(self.overlord, "mcp_coordinator"):
            if hasattr(self.overlord.mcp_coordinator, "config"):
                services = getattr(self.overlord.mcp_coordinator.config, "services", {})
                if service_id in services:
                    service_config = services[service_id]
                    if "auth" in service_config:
                        return service_config["auth"].get("accept_inline", False)

        return False

    def _get_redirect_reason(self, auth_type: str) -> str:
        """
        Get a user-friendly reason for why we're redirecting.

        Args:
            auth_type: The authentication type

        Returns:
            A user-friendly explanation string
        """
        if auth_type in ["oauth", "oauth2", "oauth2_flow"]:
            return "OAuth authentication requires browser-based authorization flow."

        if auth_type == "bearer" and not self.can_accept_inline(auth_type, False):
            return (
                "This service requires bearer token authentication through external configuration."
            )

        if auth_type == "unknown":
            return "Authentication type could not be determined."

        return (
            f"{auth_type.capitalize()} authentication requires external configuration for security."
        )

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

    async def _is_recall_question_with_answer(self, message: str, context: Dict) -> bool:
        """
        Check if this is a recall question AND if we have the answer in memory.

        Recall questions are like:
        - "What is my name?"
        - "What is my favorite X?"
        - "What did I say about X?"
        - "What's my X?"

        Returns True if it's a recall question AND memory has the answer.
        """
        try:
            # Extract clean message if it's enhanced
            clean_message = message
            if "=== CURRENT REQUEST ===" in message:
                lines = message.split("\n")
                for i, line in enumerate(lines):
                    if line.strip() == "=== CURRENT REQUEST ===" and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith("User:"):
                            clean_message = next_line[5:].strip()
                            break

            # Check if it looks like a recall question using LLM (fast, focused prompt)
            recall_system_prompt = """Is this a recall/memory question about something the user previously stated?

Examples of recall questions:
- "What is my name?"
- "What's my favorite database?"
- "What did I tell you about X?"
- "What is my X?"

NOT recall questions:
- "What is FastAPI?" (asking about general knowledge)
- "How do I do X?" (asking for help)
- "Can you X?" (making a request)

Answer with just: YES or NO"""

            try:
                if self.llm:
                    response = await self.llm.chat(
                        [
                            {"role": "system", "content": recall_system_prompt},
                            {"role": "user", "content": clean_message},
                        ],
                        temperature=0,
                        max_tokens=10,
                    )
                    
                    # Check cancellation after LLM call
                    from ..background.cancellation import check_cancellation_from_context
                    if hasattr(self.overlord, "request_tracker"):
                        await check_cancellation_from_context(self.overlord.request_tracker)
                    
                    content = response.content if hasattr(response, "content") else str(response)

                    if "YES" not in content.upper():
                        # Not a recall question
                        return False
            except Exception:
                # If LLM call fails, use simple heuristics
                recall_patterns = ["what is my", "what's my", "what did i say", "what did i tell"]
                if not any(pattern in clean_message.lower() for pattern in recall_patterns):
                    return False

            # It IS a recall question - now check if we have the answer in memory
            user_id = context.get("user_id", "0") if context else "0"

            # Skip for anonymous users
            if not user_id or user_id == "0":
                return False

            # Search memory using the same API as chat_orchestrator
            if (
                hasattr(self.overlord, "persistent_memory_manager")
                and self.overlord.persistent_memory_manager
            ):
                try:
                    # Search the same collections that chat_orchestrator uses
                    collections_to_search = [
                        "activities",
                        "preferences",
                        "user_identity",
                        "relationships",
                        "work_projects",
                        "conversations",
                        "default",
                    ]

                    results = await self.overlord.persistent_memory_manager.search_long_term_memory(
                        query=clean_message,
                        k=3,  # Get top 3 relevant memories
                        user_id=user_id,
                        collections=collections_to_search,
                    )

                    # If we found results, we have an answer in memory
                    if results and len(results) > 0:
                        # Memory has the answer - skip clarification!
                        return True
                except Exception:
                    # If memory search fails, don't skip clarification
                    pass

            # Either not a recall question, or no answer in memory
            return False
        except Exception:
            # If ANY error occurs in recall detection, don't skip clarification
            # This prevents infinite loops or crashes
            return False
