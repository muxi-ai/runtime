import time
import json
import re
from typing import Dict, Optional, Any
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

    async def needs_clarification(
        self, message: str, request_id: str, session_id: str = None, context: Optional[Dict] = None
    ) -> ClarificationResult:
        """
        Main entry point - analyzes if clarification is needed.
        Uses request_id as primary identifier.
        """
        # Check for existing clarification
        print(f"🔍 DEBUG needs_clarification: request_id={request_id}, message='{message}'")
        
        has_active = await self.has_active_clarification(request_id)
        print(f"🔍 DEBUG has_active_clarification = {has_active}")
        
        if has_active:
            print(f"🔍 DEBUG: Routing to handle_response for existing clarification")
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

    async def store_accepted_credential(self, user_id: str, service_name: str,
                                        credential_data: str, auth_type: str) -> bool:
        """
        Store credential after inline acceptance.

        Args:
            user_id: The user identifier
            service_name: The service name for the credential
            credential_data: The raw credential data from user
            auth_type: The authentication type

        Returns:
            True if storage was successful, False otherwise
        """
        try:
            # Parse credential based on auth_type
            parsed_cred = self.parse_credential(credential_data, auth_type)

            # Check if credential repository is available
            if hasattr(self.overlord, 'credential_repository'):
                # Store via repository
                await self.overlord.credential_repository.store(
                    user_id=user_id,
                    service=service_name,
                    credential_data=parsed_cred
                )

                # Credential stored successfully
                return True
            else:
                # Repository not available
                return False

        except Exception:
            # Failed to store credential - never log actual credentials
            return False

    def parse_credential(self, credential_data: str, auth_type: str) -> dict:
        """
        Parse credential data based on authentication type.

        Args:
            credential_data: Raw credential string from user
            auth_type: The authentication type

        Returns:
            Parsed credential dictionary

        Raises:
            ValueError: If credential format is invalid
        """
        credential_data = credential_data.strip()

        if auth_type == "api_key":
            # API keys are stored as-is
            return {
                "type": "api_key",
                "value": credential_data
            }

        elif auth_type == "basic":
            # Parse "username:password" format
            if ':' not in credential_data:
                raise ValueError("Basic auth must be in format: username:password")

            parts = credential_data.split(':', 1)  # Split only on first colon
            return {
                "type": "basic",
                "username": parts[0],
                "password": parts[1]
            }

        elif auth_type == "bearer":
            # Store bearer token value
            # Remove "Bearer " prefix if present
            token = credential_data
            if token.lower().startswith("bearer "):
                token = token[7:]

            return {
                "type": "bearer",
                "token": token
            }

        else:
            # Generic storage for unknown types
            return {
                "type": auth_type,
                "value": credential_data
            }

    async def get_service_credential(self, user_id: str, service_name: str) -> Optional[dict]:
        """
        Retrieve credential for MCP service use.

        Args:
            user_id: The user identifier
            service_name: The service name

        Returns:
            Credential data if found, None otherwise
        """
        try:
            if hasattr(self.overlord, 'credential_repository'):
                # Retrieve from repository
                credential = await self.overlord.credential_repository.get(
                    user_id=user_id,
                    service=service_name
                )

                if credential:
                    # Update last used timestamp
                    await self.overlord.credential_repository.update_last_used(
                        user_id=user_id,
                        service=service_name
                    )

                    # Update successful

                return credential

        except Exception:
            # Failed to retrieve credential
            pass

        return None

    async def check_stored_credential(self, user_id: str, service_name: str) -> bool:
        """
        Check if a credential is already stored for a service.

        Args:
            user_id: The user ID
            service_name: The service name

        Returns:
            True if credential exists, False otherwise
        """
        credential = await self.get_service_credential(user_id, service_name)
        return credential is not None

    async def handle_response(self, request_id: str, response: str) -> ClarificationResult:
        """
        Handle clarification response and determine next action.
        """
        print(f"🔍 DEBUG handle_response: request_id={request_id}")
        print(f"🔍 DEBUG handle_response: response='{response}'")
        
        state = await self._get_state(request_id)
        print(f"🔍 DEBUG handle_response: state={state}")
        
        if not state:
            print("❌ DEBUG: No state found for request_id")
            # No active clarification
            return ClarificationResult(action="execute", request=response)

        # Check if this is a credential response
        if state.get("type") == "credential" and state.get("auth_type") and state.get("service_id"):
            # Store the credential
            user_id = state.get("user_id", "0")  # Default to "0" for single-user mode
            service_id = state["service_id"]
            auth_type = state["auth_type"]

            # Attempt to store the credential
            success = await self.store_accepted_credential(user_id, service_id, response, auth_type)

            if success:
                # Credential stored successfully - cleanup and return success
                await self._cleanup_state(request_id)
                return ClarificationResult(
                    action="credential_stored",
                    request=state["original_request"],
                    context={
                        "service_id": service_id,
                        "credential_stored": True,
                        "message": f"Credential for {service_id} has been securely stored."
                    }
                )
            else:
                # Storage failed - cleanup and return error
                await self._cleanup_state(request_id)
                return ClarificationResult(
                    action="error",
                    request=state["original_request"],
                    context={
                        "service_id": service_id,
                        "error": "Failed to store credential. Please try again or configure externally.",
                    },
                )

        # Check if user is requesting to add new credentials
        print(f"🔍 DEBUG: About to check credential request with state: {state}")
        print(f"🔍 DEBUG: state.get('mcp_service') = {state.get('mcp_service')}")
        print(f"🔍 DEBUG: state.get('user_id') = {state.get('user_id')}")
        
        is_credential_request = await self._check_credential_request(state, response)
        print(f"🔍 DEBUG: is_credential_request = {is_credential_request}")

        # Log for debugging
        if is_credential_request:
            observability.observe(
                event_type=observability.SystemEvents.CLARIFICATION_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "request_id": request_id,
                    "credential_request_detected": True,
                    "mcp_service": state.get("mcp_service"),
                    "user_response": response[:100],
                },
                description="Credential request detected in clarification response"
            )

        if is_credential_request:
            # Check if we have an MCP service context
            mcp_service = state.get("mcp_service")

            if mcp_service:
                # We know which service this is for - use the proper handler
                user_id = state.get("user_id", "0")

                # Call the existing credential handler with the service context
                result = await self.handle_mcp_credential_request(
                    service_id=mcp_service, user_id=user_id, request_id=request_id
                )

                # Handle the result based on action
                if result.action == "message" and result.mode == "redirect":
                    # Redirect mode - clean up and return message
                    await self._cleanup_state(request_id)
                    return result
                elif result.action == "clarify":
                    # Dynamic mode asking for credentials - update state
                    state["type"] = "credential"
                    state["service_id"] = mcp_service
                    state["auth_type"] = await self._get_service_auth_type(mcp_service)
                    await self._store_state(request_id, state)
                    return result
            else:
                # No MCP service context - fall back to generic redirect if configured
                cred_config = (
                    self.overlord.formation_config.get("user_credentials", {})
                    if hasattr(self.overlord, "formation_config") and self.overlord.formation_config
                    else {}
                )
                mode = cred_config.get("mode", "redirect")

                if mode == "redirect":
                    redirect_message = cred_config.get(
                        "redirect_message",
                        "For security, credentials must be configured outside of this chat interface.",
                    )
                    await self._cleanup_state(request_id)
                    return ClarificationResult(
                        action="message",
                        question=redirect_message,
                        mode="redirect",
                        context={"credential_redirect": True},
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

    async def handle_mcp_credential_request(
        self, service_id: str, user_id: str, request_id: str
    ) -> ClarificationResult:
        """
        Handle credential request for MCP service based on configuration mode.

        Args:
            service_id: The MCP service requesting credentials
            user_id: The user ID for whom credentials are needed
            request_id: The current request ID

        Returns:
            ClarificationResult with redirect message or credential prompt
        """
        # Access user_credentials config (top-level, not under clarification)
        cred_config = (
            self.overlord.formation_config.get("user_credentials", {})
            if hasattr(self.overlord, "formation_config") and self.overlord.formation_config
            else {}
        )
        mode = cred_config.get("mode", "redirect")

        if mode == "redirect":
            # Always redirect in redirect mode
            redirect_message = cred_config.get(
                "redirect_message",
                "For security, credentials must be configured outside of this chat interface.\n"
                "Please use your organization's credential management system to set up authentication.",
            )

            # Add service context to the message
            full_message = f"{redirect_message}\n\nService '{service_id}' requires authentication."

            # Return redirect message without starting clarification
            return ClarificationResult(action="message", question=full_message, mode="redirect")

        # Dynamic mode handling
        if mode == "dynamic":
            # Get service metadata to determine auth type
            auth_type = await self._get_service_auth_type(service_id)
            accept_inline = await self._get_service_accept_inline(service_id)

            if self.can_accept_inline(auth_type, accept_inline):
                # Request credential inline with appropriate warnings
                prompt = await self.request_inline_credential(service_id, auth_type, request_id)

                # Start clarification flow for credential collection
                await self._create_state(request_id, f"Provide {auth_type} for {service_id}", "credential")
                state = await self._get_state(request_id)
                if state:
                    state["service_id"] = service_id
                    state["auth_type"] = auth_type
                    state["user_id"] = user_id  # Store user_id for credential storage
                    state["max_depth"] = 1  # Single question for credential
                    await self._store_state(request_id, state)

                return ClarificationResult(
                    action="clarify",
                    question=prompt,
                    mode="dynamic"
                )
            else:
                # Cannot accept inline, redirect instead
                redirect_message = cred_config.get(
                    "redirect_message",
                    "For security, credentials must be configured outside of this chat interface.\n"
                    "Please use your organization's credential management system to set up authentication.",
                )

                # Add context about why we're redirecting
                reason = self._get_redirect_reason(auth_type)
                full_message = f"{redirect_message}\n\n{reason}\n\nService '{service_id}' requires authentication."

                return ClarificationResult(action="message", question=full_message, mode="redirect")

        # Unknown mode, fall back to redirect
        redirect_message = cred_config.get(
            "redirect_message",
            "For security, credentials must be configured outside of this chat interface.\n"
            "Please use your organization's credential management system to set up authentication.",
        )

        full_message = f"{redirect_message}\n\nService '{service_id}' requires authentication."

        return ClarificationResult(action="message", question=full_message, mode="redirect")

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
        print(f"🔍 DEBUG has_active_clarification: request_id={request_id}, state={state}")
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
                event_type=observability.SystemEvents.MEMORY_OPERATION_FAILED,
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
        """
        # Get formation capabilities (pre-computed during overlord initialization)
        capabilities = getattr(self.overlord, "capabilities", [])
        mcp_servers = getattr(self.overlord, "mcp_servers", [])

        # Get response style
        response_style = {
            "conversational": "natural, friendly, like a helpful colleague",
            "technical": "precise, specific, professional",
            "brief": "very concise, minimal words",
        }.get(self.style, "natural, friendly, like a helpful colleague")

        # Extract conversation context if it exists, otherwise use the full message
        if "=== CONVERSATION CONTEXT (Most Recent First) ===" in message:
            conversation = message.split("=== CONVERSATION CONTEXT (Most Recent First) ===")[
                -1
            ].strip()
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

=== MCP SERVICES AVAILABLE ===
{", ".join(mcp_servers) if mcp_servers else "None"}

=== INSTRUCTIONS ===
Be {response_style}.

Determine:
1. Is the request clear enough to attempt execution?
2. What mode of interaction does the user want?
3. If clarification needed, what should we ask?
4. Which MCP service (if any) is this request about?

IMPORTANT RULES:
- If the request is clear enough to make an attempt, don't clarify
- If user provides code or specific error, that's usually enough
- For vague requests like "help me" or "fix this", DO clarify
- If we lack the tools/capabilities, don't clarify (fail fast)
- Detect if user wants brainstorming/planning vs direct action

MCP SERVICE DETECTION:
- Only set mcp_service if the request clearly needs one of the available MCP services
- Set to null if not relevant or not asking about MCP service

Return JSON:
{{
    "needs_clarification": boolean,
    "reason": "ambiguous|missing_info|no_capability|clear",
    "mode": "direct|brainstorm|planning",
    "question": "clarification question in the specified style or null",
    "confidence": 0.0 to 1.0,
    "mcp_service": "service_name or null"
}}
        """
        print(prompt)
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

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.chat(messages, temperature=0, max_tokens=250)
        content = response.content if hasattr(response, "content") else str(response)
        print(content)

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
                        credentials = await self.overlord.credential_resolver.get_user_credentials(
                            user_id, mcp_service
                        )
                        if credentials:
                            available_accounts = [
                                cred.get("name", f"Account {i+1}") for i, cred in enumerate(credentials)
                            ]
                    except Exception as e:
                        # Log the error for debugging
                        observability.observe(
                            event_type=observability.SystemEvents.CLARIFICATION_COMPLETED,
                            level=observability.EventLevel.WARNING,
                            data={
                                "error": str(e),
                                "user_id": user_id,
                                "service": mcp_service,
                            },
                            description=f"Failed to get credentials for {mcp_service}: {e}"
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
                    base_question = result.get("question", f"Which {mcp_service} account would you like to use?")
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

    async def _check_credential_request(self, state: Dict, response: str) -> bool:
        """
        Check if the user is requesting to add new credentials.
        Uses LLM to detect credential addition requests.
        """
        print(f"🔍 DEBUG _check_credential_request called")
        print(f"🔍 DEBUG state: {state}")
        print(f"🔍 DEBUG response: '{response}'")
        
        if not self.llm:
            print("❌ DEBUG: No LLM available for credential request detection")
            return False  # Can't detect without LLM

        # Get the last question we asked
        last_question = state.get("last_question", "a clarification question")
        print(f"🔍 DEBUG last_question: '{last_question}'")

        prompt = f"""
        We're in a clarification dialog about: {state['original_request']}
        We asked: "{last_question}"
        The user responded: "{response}"

        Determine if the user is requesting to ADD NEW CREDENTIALS, API keys, or accounts.

        Examples of credential requests (return "yes"):
        - "I need to add a new Xero account with different credentials"
        - "I want to use a different API key"
        - "Let me add a new account"
        - "I need to configure new credentials"
        - "None of the above, I want to add a new account"
        - "I'd like to set up a different token"

        Examples of NOT credential requests (return "no"):
        - "Use the first account"
        - "My account is newuser123" (just providing a username, not asking to add credentials)
        - "The second one"
        - "Never mind"

        Return "yes" if user wants to ADD/CONFIGURE new credentials, "no" otherwise.
        """

        messages = [{"role": "user", "content": prompt}]
        print(f"🔍 DEBUG sending prompt to LLM: {prompt}")
        
        result = await self.llm.chat(messages, temperature=0, max_tokens=20)
        content = result.content if hasattr(result, "content") else str(result)
        
        print(f"🔍 DEBUG LLM response: '{content}'")
        
        is_credential_request = "yes" in content.lower()
        print(f"🔍 DEBUG final result: {is_credential_request}")
        
        return is_credential_request

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

    async def request_inline_credential(self, service_id: str, auth_type: str, request_id: str) -> str:
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
            return (
                f"{base_prompt}\n\n"
                "Please provide your personal access token or bearer token."
            )

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
        if hasattr(self.overlord, 'mcp_registry'):
            service = self.overlord.mcp_registry.get(service_id)
            if service and hasattr(service, 'auth'):
                return service.auth.get('type', 'unknown')

        # Try to get from MCP coordinator
        if hasattr(self.overlord, 'mcp_coordinator'):
            # Access service configuration
            if hasattr(self.overlord.mcp_coordinator, 'config'):
                services = getattr(self.overlord.mcp_coordinator.config, 'services', {})
                if service_id in services:
                    service_config = services[service_id]
                    if 'auth' in service_config:
                        return service_config['auth'].get('type', 'unknown')

        return 'unknown'

    async def _get_service_accept_inline(self, service_id: str) -> bool:
        """
        Check if a service accepts inline credential collection.

        Args:
            service_id: The service identifier

        Returns:
            True if the service accepts inline credentials, False otherwise
        """
        # Try to get from MCP registry if available
        if hasattr(self.overlord, 'mcp_registry'):
            service = self.overlord.mcp_registry.get(service_id)
            if service and hasattr(service, 'auth'):
                return service.auth.get('accept_inline', False)

        # Try to get from MCP coordinator
        if hasattr(self.overlord, 'mcp_coordinator'):
            if hasattr(self.overlord.mcp_coordinator, 'config'):
                services = getattr(self.overlord.mcp_coordinator.config, 'services', {})
                if service_id in services:
                    service_config = services[service_id]
                    if 'auth' in service_config:
                        return service_config['auth'].get('accept_inline', False)

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
            return "This service requires bearer token authentication through external configuration."

        if auth_type == "unknown":
            return "Authentication type could not be determined."

        return f"{auth_type.capitalize()} authentication requires external configuration for security."

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
