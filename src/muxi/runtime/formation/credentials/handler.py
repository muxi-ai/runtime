"""
Credential handling logic for the formation system.
Moved from overlord.py to proper separation of concerns.
"""

from typing import Dict, Optional, Any
import logging
import traceback

logger = logging.getLogger(__name__)


class CredentialHandler:
    """
    Handles credential detection, validation, and processing.
    Separated from overlord for better architecture.
    """

    def __init__(self, overlord):
        """Initialize with reference to overlord for accessing services."""
        self.overlord = overlord
        self._pending = {}  # session_id -> {service, service_id, auth_type, timestamp}

    async def _get_configured_llm(self, cache_suffix: str = "default", max_tokens: int = 100):
        """
        Get properly configured LLM instance using overlord or formation configuration.

        Args:
            cache_suffix: Suffix for cache key to allow different configs
            max_tokens: Maximum tokens for response

        Returns:
            Configured LLM instance or None if no model available
        """
        # Get text model config from overlord's capability models
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            return None

        model_name = text_model_config.get("model")
        if not model_name:
            return None

        cache_key = f"credential_{cache_suffix}_{model_name}"

        # Check cache first
        if cache_key in self.overlord._model_cache:
            return self.overlord._model_cache[cache_key]

        # Create new model instance with proper configuration
        try:
            # Filter out params we're setting explicitly to avoid duplicate kwargs
            settings = {k: v for k, v in text_model_config.get("settings", {}).items()
                       if k not in ["temperature", "max_tokens"]}
            llm = await self.overlord.create_model(
                model=model_name,
                api_key=text_model_config.get("api_key"),
                temperature=0.7,  # Reasonable default for credential operations
                max_tokens=max_tokens,
                **settings,
            )
            self.overlord._model_cache[cache_key] = llm
            return llm
        except Exception as e:
            logger.error(f"Failed to create configured LLM: {e}")
            return None

    async def detect_credential_need(self, message: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Use LLM to detect if message needs credentials and determine the type.

        Detection Logic:
        1. Explicit credential request → CREDENTIAL_REQUEST
        2. Service use with existing creds → None (let normal flow handle)
        3. Service use without creds → SERVICE_USE
        4. Unrelated to credentials → None

        Args:
            message: User's message
            user_id: User ID for checking existing credentials

        Returns:
            Dict with detection results or None if no credential need detected:
            {
                "type": "SERVICE_USE" | "CREDENTIAL_REQUEST",
                "service": "github" | "jira" | etc.,
                "service_id": "github-mcp" | etc.,
                "needs_credentials": bool,
                "accept_inline": bool,
                "auth_type": str
            }
        """
        # Get text model for credential detection
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            return None

        model_name = text_model_config.get("model")
        cache_key = f"credential_detection_{model_name}"

        if cache_key in self.overlord._model_cache:
            llm = self.overlord._model_cache[cache_key]
        else:
            # Filter out params we're setting explicitly to avoid duplicate kwargs
            settings = {k: v for k, v in text_model_config.get("settings", {}).items()
                       if k not in ["temperature", "max_tokens"]}
            llm = await self.overlord.create_model(
                model=model_name,
                api_key=text_model_config.get("api_key"),
                temperature=0.0,
                max_tokens=100,
                **settings,
            )
            self.overlord._model_cache[cache_key] = llm

        # Get available services that use user credentials
        available_services = list(self.overlord._mcp_servers_with_user_credentials.values())
        if not available_services:
            return None

        services_str = ", ".join([s["service"] for s in available_services])

        system_prompt = f"""Analyze user messages to determine if they require credentials for external services.

Available credential services: {services_str}

Detection rules:
1. CREDENTIAL_REQUEST - User explicitly wants to add/update/configure credentials:
   - "I need to add a new GitHub account"
   - "Add new GitHub account with different credentials"
   - "I want to use a different API key"
   - "Let me add a new account"
   - "Configure GitHub auth"
   - "I need to set up new credentials"

2. SERVICE_USE - User wants to perform operations DIRECTLY on a specific service:
   IMPORTANT: The service name MUST be explicitly mentioned in the message!
   YES examples (service explicitly mentioned):
   - "List my GitHub repositories" (mentions GitHub)
   - "Create a GitHub issue" (mentions GitHub)
   - "Show my Jira tickets" (mentions Jira)
   - "Check my GitHub pull requests" (mentions GitHub)

   NO examples (no service mentioned - return NONE):
   - "Create a PDF document" (PDF creation, not a service operation)
   - "Generate a report" (document generation, not a service operation)
   - "Compile these ideas" (general task, not a service operation)
   - "Summarize this into a document" (document creation, not a service operation)
   - "Create a file" (file creation, not a service operation)

3. NONE - Neither credential management nor service use:
   - Document creation (PDF, reports, summaries)
   - General file operations
   - Brainstorming or conceptual work
   - Any request that doesn't explicitly mention a credential service

CRITICAL: If the user message does NOT explicitly mention one of the available services ({services_str}),
then return type: "NONE". Document creation is NOT a service operation.

Respond in JSON format:
{{
    "type": "SERVICE_USE|CREDENTIAL_REQUEST|NONE",
    "service": "service_name or null",
    "confidence": 0.0-1.0
}}"""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)

            # Parse JSON response
            # Extract JSON from response if it contains other text
            import json

            # Use find/rfind for safe substring search
            json_start = response.find("{")
            json_end = response.rfind("}")

            if json_start >= 0 and json_end >= 0 and json_end >= json_start:
                json_str = response[json_start:json_end + 1]
                try:
                    detection = json.loads(json_str)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(
                        f"Failed to parse LLM JSON response: {e}. Response: {response[:200]}"
                    )
                    return None
            else:
                logger.debug(f"No valid JSON found in LLM response: {response[:200]}")
                return None

            if detection["type"] == "NONE":
                return None

            # Check confidence threshold - only proceed with high confidence
            confidence = detection.get("confidence", 0.0)
            if confidence < 0.8:  # Require high confidence for credential detection
                return None

            # Find the matching service configuration
            detected_service = detection.get("service")
            if not detected_service:
                return None

            # Look for service in available services
            service_config = None
            for config in available_services:
                if config["service"] == detected_service:
                    service_config = config
                    break

            if not service_config:
                # Service not configured in formation
                return None

            # For CREDENTIAL_REQUEST - always handle
            if detection["type"] == "CREDENTIAL_REQUEST":
                return {
                    "type": "CREDENTIAL_REQUEST",
                    "service": detected_service,
                    "service_id": service_config["server_id"],
                    "needs_credentials": True,
                    "accept_inline": service_config.get("accept_inline", False),
                    "auth_type": service_config.get("auth_type", "bearer"),
                    "confidence": detection.get("confidence", 0.0),
                }

            # For SERVICE_USE - check if user has credentials
            if detection["type"] == "SERVICE_USE":
                # Check if user has any credentials for this service
                has_credentials = await self._user_has_credentials(user_id, detected_service)

                if not has_credentials:
                    # User needs credentials - trigger credential addition flow
                    return {
                        "type": "CREDENTIAL_REQUEST",  # Treat as credential request
                        "service": detected_service,
                        "service_id": service_config["server_id"],
                        "needs_credentials": True,
                        "accept_inline": service_config.get("accept_inline", False),
                        "auth_type": service_config.get("auth_type", "bearer"),
                        "confidence": detection.get("confidence", 0.0),
                    }

                # User has credentials - let normal flow handle selection
                return None

        except Exception as e:
            # Failed to detect credential need via LLM
            logger.error(f"Failed to detect credential need: {e}", exc_info=True)
            return None

    async def _user_has_credentials(self, user_id: str, service: str) -> bool:
        """
        Check if user has any credentials for the given service.

        Args:
            user_id: User identifier
            service: Service name (e.g., "github")

        Returns:
            True if user has at least one credential for the service
        """
        try:
            # Check if we have credential resolver
            if hasattr(self.overlord, "credential_resolver"):
                resolver = self.overlord.credential_resolver

                # Try to get credentials for this user and service
                credentials = await resolver.resolve(user_id, service)

                # If credentials is not None and not empty list, user has credentials
                if credentials is not None:
                    if isinstance(credentials, list):
                        return len(credentials) > 0
                    else:
                        return True  # Single credential

            return False

        except Exception:
            return False

    async def validate_credential(
        self, service: str, service_id: str, credential: str, timeout: float = 5.0
    ) -> bool:
        """
        Validate a credential by attempting to connect to its MCP server.

        Args:
            service: The service name (e.g., "github")
            service_id: The MCP server ID (e.g., "github-mcp")
            credential: The credential to validate
            timeout: Connection timeout in seconds

        Returns:
            True if credential is valid, False otherwise
        """
        # Get the server configuration from registered servers
        if (
            not hasattr(self.overlord.mcp_service, "connections")
            or service_id not in self.overlord.mcp_service.connections
        ):
            print(f"Server {service_id} not found in MCP service connections")
            return False

        config = self.overlord.mcp_service.connections[service_id]

        # Get auth type from configuration (default to bearer for GitHub)
        auth_type = config.get("auth_type", "bearer")

        # Create temporary credentials object with proper structure
        if auth_type == "bearer":
            temp_credentials = {"type": "bearer", "token": credential}
        else:
            # For other auth types, might need different structure
            temp_credentials = {service: credential}

        # For GitHub, do a simple API test instead of full MCP connection
        if service == "github" and auth_type == "bearer":
            import aiohttp
            import asyncio

            try:
                # Simple GitHub API call to test the token
                async with aiohttp.ClientSession() as session:
                    headers = {"Authorization": f"Bearer {credential}"}
                    url = "https://api.github.com/user"

                    async with session.get(
                        url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        if response.status == 200:
                            print(f"Credential validation successful for {service}")
                            return True
                        elif response.status == 401:
                            print(f"Credential validation failed for {service}: unauthorized")
                            return False
                        else:
                            print(
                                f"Credential validation failed for {service}: status {response.status}"
                            )
                            return False
            except asyncio.TimeoutError:
                print(f"Credential validation timed out after {timeout}s")
                return False
            except Exception as e:
                print(f"Credential validation failed for {service}: {e}")
                return False

        # For other services, fallback to MCP connection test (but with strict timeout)
        from muxi.runtime.services.mcp.handler import MCPHandler
        import asyncio

        handler = MCPHandler(model=None, tool_registry=self.overlord.mcp_service.tool_registry)
        validation_name = f"{service_id}_validation"

        try:
            success = await asyncio.wait_for(
                handler.connect_server(
                    name=validation_name,
                    url=config.get("url"),
                    command=config.get("command"),
                    args=config.get("args"),
                    credentials=temp_credentials,
                    request_timeout=int(timeout),
                    server_id=service_id,
                ),
                timeout=timeout,
            )

            if success:
                print(f"Credential validation successful for {service}")
                return True
            else:
                print(f"Credential validation failed for {service}")
                return False

        except asyncio.TimeoutError:
            print(f"Credential validation timed out after {timeout}s")
            return False
        except Exception as e:
            print(f"Credential validation failed for {service}: {e}")
            return False
        finally:
            # Always try to disconnect and cleanup resources
            try:
                await asyncio.wait_for(handler.disconnect_server(validation_name), timeout=1.0)
            except Exception as cleanup_error:
                # Log but don't raise - cleanup is best effort
                logger.debug(f"Failed to disconnect MCP handler during cleanup: {cleanup_error}")

    async def handle_credential_response(self, message: str, session_id: str, user_id: str):
        """Handle response to credential prompt - with retry loop."""
        if session_id not in self._pending:
            return None

        # Check for cancellation first
        if await self._is_cancellation(message):
            self._pending.pop(session_id)  # Clear state
            return await self._generate_cancellation_message()

        # Check for help request (user asking for guidance)
        if await self._is_help_request(message):
            # DON'T clear pending state - user will provide credentials after help
            pending = self._pending[session_id]
            help_response = await self._generate_help_response(pending["service"])
            return help_response

        # DON'T pop - keep state for retry on failure!
        pending = self._pending[session_id]

        # Check for timeout (>5 minutes)
        import time

        if time.time() - pending["timestamp"] > 300:
            self._pending.pop(session_id)  # Clear stale state
            return None  # Ignore stale requests

        try:
            # Extract credential from natural language
            credential = await self._extract_credential_from_text(message)

            # Check if this token already exists BEFORE validating
            is_duplicate = await self.overlord.credential_resolver.check_duplicate(
                user_id=user_id, service=pending["service"], credentials=credential
            )

            if is_duplicate:
                print(f"Token already stored for {pending['service']} - skipping validation")
                # Clear pending state
                self._pending.pop(session_id, None)
                # Generate duplicate message and return just the message
                duplicate_message = await self._generate_duplicate_message(pending["service"])
                return duplicate_message

            # Use a SHORT timeout for validation only
            # Validation should be quick - just testing if credentials work
            validation_timeout = 5.0  # 5 seconds is plenty for auth validation
            print(f"Using timeout of {validation_timeout} seconds for credential validation")

            # VALIDATE FIRST by testing MCP connection (no database touch!)
            is_valid = await self.validate_credential(
                service=pending["service"],
                service_id=pending["service_id"],
                credential=credential,
                timeout=validation_timeout,
            )

            if is_valid:
                # NOW store the validated credential
                try:
                    status = await self.overlord.credential_resolver.store_credential(
                        user_id=user_id,
                        service=pending["service"],
                        credentials=credential,
                        credential_name=pending["service"],  # Generic name for now
                    )
                    if status == "duplicate":
                        print(f"Token already stored for {pending['service']}")
                    else:
                        print(f"Stored new credential for {pending['service']}")
                except Exception as store_error:
                    print(f"ERROR storing credential: {store_error}")
                    traceback.print_exc()
                    raise  # Re-raise to be caught by outer exception handler

                # Async update the name (fire and forget, don't wait or block)
                import asyncio

                async def update_name_wrapper():
                    """Wrapper to handle errors in background name update."""
                    try:
                        await self.overlord.credential_resolver.update_credential_name_with_discovery(
                            user_id=user_id,
                            service=pending["service"],
                            mcp_service=self.overlord.mcp_service,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to update credential name for {pending['service']}: {e}",
                            exc_info=True,
                        )

                # Create task with error handling
                task = asyncio.create_task(update_name_wrapper())
                # Add callback to log if task fails unexpectedly
                task.add_done_callback(
                    lambda t: (
                        logger.error(f"Name update task failed: {t.exception()}")
                        if t.exception()
                        else None
                    )
                )

                # Clear pending state and continue with original request
                original_message = pending.get("original_message")
                self._pending.pop(session_id)

                # Generate success message
                success_msg = await self._generate_success_message(
                    pending["service"], pending["service"]
                )

                # Return with signal to continue processing original request
                return {
                    "message": success_msg,
                    "continue_with": original_message,
                    "action": "credential_stored",
                }
            else:
                # Invalid credential - don't store, just ask for retry
                print(f"Invalid credential for {pending['service']} - asking for retry")

                # Don't pop state - keep for retry
                return await self._generate_validation_failure_message(pending["service"])

        except Exception as e:
            # FAILED - keep state for retry, user stays in loop
            print(f"ERROR in handle_credential_response: {e}")
            traceback.print_exc()
            return await self._generate_validation_failure_message(pending["service"])

    async def is_credential_request(self, message: str) -> bool:
        """
        Check if message is requesting to add credentials using LLM.
        Simple binary check for credential addition intent.

        Args:
            message: User's message to analyze

        Returns:
            True if user is requesting to add credentials, False otherwise
        """
        # Use LLM to detect credential request intent
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            return False

        model_name = text_model_config.get("model")
        cache_key = f"credential_request_{model_name}"

        if cache_key in self.overlord._model_cache:
            llm = self.overlord._model_cache[cache_key]
        else:
            # Filter out params we're setting explicitly to avoid duplicate kwargs
            settings = {k: v for k, v in text_model_config.get("settings", {}).items()
                       if k not in ["temperature", "max_tokens"]}
            llm = await self.overlord.create_model(
                model=model_name,
                api_key=text_model_config.get("api_key"),
                temperature=0.0,
                max_tokens=10,
                **settings,
            )
            self.overlord._model_cache[cache_key] = llm

        system_prompt = """Analyze messages to determine if the user is asking to ADD or CONFIGURE new credentials.

Examples of credential requests:
- "I need to add a new GitHub account"
- "Configure new API key"
- "Set up different credentials"
- "Add another account"

Examples of NON-credential requests:
- "Use my GitHub account"
- "List my repositories"
- "What's my balance?"

Respond with only "YES" if requesting to add credentials, "NO" otherwise."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)

            result = response.strip().upper()
            return result == "YES"
        except Exception:
            # Failed to detect credential request via LLM
            pass
            return False

    async def handle_credential_request(
        self,
        message: str,
        user_id: str,
        detection_result: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle credential request based on formation mode configuration.

        Args:
            message: Original user message
            user_id: User identifier
            detection_result: Result from detect_credential_need
            session_id: Optional session identifier

        Returns:
            Dict with response action and content
        """
        service = detection_result["service"]
        service_id = detection_result["service_id"]

        # Get user credentials configuration from formation
        cred_config = (
            self.overlord.formation_config.get("user_credentials", {})
            if hasattr(self.overlord, "formation_config") and self.overlord.formation_config
            else {}
        )
        mode = cred_config.get("mode", "redirect")

        if mode == "redirect":
            # Show redirect message
            redirect_message = cred_config.get(
                "redirect_message",
                "Please configure your API credentials in the external credential manager.",
            )

            return {
                "action": "redirect",
                "message": f"{redirect_message}\n\nService '{service}' requires authentication.",
                "mode": "redirect",
            }

        elif mode == "dynamic":
            # Check if service accepts inline credentials
            accept_inline = detection_result.get("accept_inline", False)
            auth_type = detection_result.get("auth_type", "bearer")

            if accept_inline:
                # Store minimal state with timestamp for timeout handling
                import time

                if session_id:
                    self._pending[session_id] = {
                        "service": service,
                        "service_id": service_id,
                        "auth_type": auth_type,
                        "timestamp": time.time(),
                        "original_message": message,  # Store for replay after success
                    }

                # Prompt for inline credential collection
                prompt_message = await self._generate_credential_prompt(
                    service, service_id, auth_type
                )

                return {
                    "action": "collect",
                    "message": prompt_message,
                    "mode": "dynamic",
                    "service": service,
                    "service_id": service_id,
                    "auth_type": auth_type,
                }
            else:
                # Cannot accept inline, fall back to redirect
                redirect_message = cred_config.get(
                    "redirect_message",
                    "Please configure your API credentials in the external credential manager.",
                )
                reason = self._get_redirect_reason(auth_type)

                return {
                    "action": "redirect",
                    "message": f"{redirect_message}\n\n{reason}\n\nService '{service}' requires authentication.",
                    "mode": "redirect_fallback",
                }

        # Unknown mode, default to redirect
        redirect_message = cred_config.get(
            "redirect_message",
            "Please configure your API credentials in the external credential manager.",
        )

        return {
            "action": "redirect",
            "message": f"{redirect_message}\n\nService '{service}' requires authentication.",
            "mode": "redirect_default",
        }

    async def _generate_credential_prompt(
        self, service: str, service_id: str, auth_type: str
    ) -> str:
        """Generate appropriate prompt for credential collection using persona."""
        # Get LLM configuration
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            # Fallback if no LLM available
            return f"Please provide credentials for {service}"

        # Prepare context based on auth type
        auth_description = {
            "bearer": "personal access token or API token",
            "api_key": "API key",
            "basic": "username and password",
            "oauth": "OAuth token",
        }.get(auth_type, "credentials")

        system_prompt = """Generate a natural, friendly message asking the user to provide their credentials.

Important:
- Be conversational and friendly
- Mention that credentials will be stored securely
- Keep it brief (1-2 sentences)
- Match the user's language if they're not using English
- Don't use technical jargon like 'bearer token' - use friendly terms

Example good responses:
- "I'll need your GitHub personal access token to continue. Could you share it with me?"
- "To access your GitHub repositories, I'll need your access token. Don't worry, I'll store it securely."

Generate only the message, nothing else."""

        try:
            # Get or create LLM instance
            # Create a hashable cache key from the config
            cache_key = ("text", text_model_config.get("provider"), text_model_config.get("model"))
            if cache_key not in self.overlord._model_cache:
                from ...services.llm import LLM

                llm = LLM(
                    provider=text_model_config.get("provider"),
                    model=text_model_config.get("model"),
                    temperature=0.7,
                    max_tokens=100,
                    **text_model_config.get("settings", {}),
                )
                self.overlord._model_cache[cache_key] = llm
            else:
                llm = self.overlord._model_cache[cache_key]

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Service: {service}, Credential type: {auth_description}"},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip()
        except Exception as e:
            print(f"Warning: Failed to generate credential prompt via LLM: {e}")
            # Fallback to simple message
            if auth_type == "bearer":
                return f"I need your {service} personal access token to continue. Could you share it with me?"
            elif auth_type == "api_key":
                return f"I need your {service} API key to continue. It will be stored securely."
            elif auth_type == "basic":
                return f"I need your {service} username and password to continue. Format: username:password"
            return f"I need your {service} credentials to continue."

    async def _is_cancellation(self, message: str) -> bool:
        """Check if user wants to cancel credential entry using LLM."""
        system_prompt = """The user is in the middle of providing credentials.
Determine if they are trying to cancel/abort/skip the credential entry process.

Examples of cancellation (in any language):
- "nevermind"
- "forget it"
- "cancel"
- "I don't want to"
- "skip this"
- "later"
- "stop"
- "no thanks"
- "pas maintenant" (French: not now)
- "cancelar" (Spanish: cancel)
- "やめる" (Japanese: stop)

IMPORTANT: These are NOT cancellations - they are HELP REQUESTS:
- "I don't know how to get a token"
- "How do I get this?"
- "Can you help me?"
- "Where do I find this?"
- "What is this?"

If the user is asking for help or guidance, respond NO (not a cancellation).

Respond with only YES or NO."""

        try:
            # Use properly configured LLM from overlord/formation
            llm = await self._get_configured_llm(cache_suffix="cancellation", max_tokens=10)
            if not llm:
                # No configured LLM available, fallback to simple pattern matching
                cancel_patterns = [
                    "cancel",
                    "stop",
                    "nevermind",
                    "forget",
                    "skip",
                    "abort",
                    "no",
                    "later",
                ]
                message_lower = message.lower()
                return any(pattern in message_lower for pattern in cancel_patterns)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip().upper().startswith("YES")
        except Exception as e:
            logger.debug(f"Failed to check cancellation with LLM: {e}")
            # On LLM failure, assume not cancellation to avoid accidental exits
            return False

    async def _is_help_request(self, message: str) -> bool:
        """Check if user is asking for help/guidance on getting credentials."""
        system_prompt = """The user is in the middle of providing credentials.
Determine if they are asking for HELP or GUIDANCE on how to obtain credentials.

Examples of help requests (in any language):
- "I don't know how to get a token"
- "How do I get this?"
- "Can you help me?"
- "Where do I find this?"
- "What is this?"
- "How do I create one?"
- "I need help"
- "Show me how"
- "¿Cómo obtengo esto?" (Spanish: How do I get this?)
- "Comment obtenir ça?" (French: How to get this?)
- "これをどうやって入手しますか？" (Japanese: How do I get this?)

IMPORTANT: These are NOT help requests - they are PROVIDING credentials:
- "Thanks for the help! Here's my token: xyz123"
- "Here is my key: abc789"
- "My token is: ghp_xxxxx"
- If the message contains what looks like an actual credential/token, respond NO

Respond with only YES or NO."""

        try:
            llm = await self._get_configured_llm(cache_suffix="help", max_tokens=10)
            if not llm:
                # Fallback to simple pattern matching
                message_lower = message.lower()
                # If message contains a token-like string, it's NOT a help request
                if any(
                    pattern in message_lower
                    for pattern in ["here's my", "here is my", "my token is", "token:", "key:"]
                ):
                    return False
                help_patterns = [
                    "don't know",
                    "how do i",
                    "how to",
                    "can you help",
                    "help me",
                    "where do i",
                    "what is",
                    "show me",
                ]
                return any(pattern in message_lower for pattern in help_patterns)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip().upper().startswith("YES")
        except Exception as e:
            logger.debug(f"Failed to check help request with LLM: {e}")
            # On LLM failure, fallback to pattern matching
            message_lower = message.lower()
            # If message contains a token-like string, it's NOT a help request
            if any(
                pattern in message_lower
                for pattern in ["here's my", "here is my", "my token is", "token:", "key:"]
            ):
                return False
            help_patterns = ["don't know", "how do i", "how to", "help"]
            return any(pattern in message_lower for pattern in help_patterns)

    async def _generate_help_response(self, service: str) -> str:
        """Generate helpful guidance for obtaining credentials for a specific service.

        Uses LLM to generate service-specific instructions based on world knowledge.
        This scales to any service and supports any language. Falls back to inline
        template if LLM fails.
        """
        # Try LLM-generated help first
        try:
            # Get configured LLM instance
            llm = await self._get_configured_llm(cache_suffix="credential_help", max_tokens=500)
            if not llm:
                raise RuntimeError("No LLM available for help generation")

            # Detect user language from context
            user_language = self._detect_user_language()

            # System prompt for credential help generation
            system_prompt = f"""You are helping a user obtain API credentials.

Based on your world knowledge, provide clear step-by-step instructions in {user_language} for obtaining an API key or access token.

If you know the service:
- Include the sign-in URL
- Explain where to find API/developer settings
- Detail how to generate the credential
- Mention any important permissions/scopes
- Note any security considerations

If you don't have specific knowledge about the service:
- Provide generic instructions in {user_language}
- Guide them to look for "Settings", "API", or "Developer" sections
- Explain the general process of finding and generating API credentials

Be helpful and specific when you can, or provide useful generic guidance if you can't."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"I need help getting credentials for: {service}"},
            ]
            response_obj = await llm.chat(messages, max_tokens=500)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)

            if response:
                return response.strip()

        except Exception as e:
            # Log failure but continue to inline fallback
            from ...services import observability

            observability.observe(
                event_type=observability.SystemEvents.EXTENSION_FAILED,
                level=observability.EventLevel.DEBUG,
                data={"service": service, "error": str(e)},
                description=f"LLM help generation failed, using inline fallback: {e}",
            )

        # Last resort inline fallback (only if LLM completely unavailable)
        return f"""To get credentials for {service}:

1. Sign in to the {service} website
2. Look for Settings or Account settings
3. Find API, Developer settings, or Integrations section
4. Generate a new API key or access token
5. Copy the credentials

Once you have your credentials, paste them here."""

    def _detect_user_language(self) -> str:
        """Detect user's language from context or default to English."""
        return "English"

    async def _extract_credential_from_text(self, message: str) -> str:
        """Extract credential from natural language using LLM."""
        system_prompt = """The user is providing an API credential/token.
Extract ONLY the actual credential/token/key from their message.
If the message appears to be just the credential itself, return it as-is.

Examples:
- "Here's my token: abc123" → "abc123"
- "The key is xyz789" → "xyz789"
- "ghp_1234567890" → "ghp_1234567890"
- "mi token es abc123" (Spanish) → "abc123"
- "voici mon jeton: xyz" (French) → "xyz"
- "abc123" → "abc123"

Return ONLY the credential itself, no quotes, no explanation."""

        try:
            # Use properly configured LLM from overlord/formation
            llm = await self._get_configured_llm(cache_suffix="extraction", max_tokens=100)
            if not llm:
                # No configured LLM available, fallback to simple extraction
                # Assume the whole message is the credential
                return message.strip().strip('"').strip("'")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
            response_obj = await llm.chat(messages)
            extracted = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            # Clean up any quotes the LLM might have added
            return extracted.strip().strip('"').strip("'")
        except Exception as e:
            logger.debug(f"Failed to extract credential with LLM: {e}")
            # Fallback: assume the whole message is the credential
            return message.strip().strip('"').strip("'")

    async def _generate_validation_failure_message(self, service: str) -> str:
        """Generate validation failure message respecting persona."""
        # Get LLM configuration
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            # Fallback if no LLM available
            return (
                f"That {service} token didn't work. Please double-check the token "
                f"or create a new one in your {service} settings."
            )

        system_prompt = """Generate a helpful, understanding message when a user's credential fails validation.

The message should:
- Gently explain the token didn't work
- Suggest they double-check the token
- Mention they should check their account settings to create a new token if needed
- Be supportive, not frustrating
- Keep it brief (2-3 sentences)
- Do NOT include specific URLs
- Let them know they can provide a different token or move on

Example good responses:
- "Hmm, that token didn't seem to work. Could you double-check it? You can also create a new one in your settings."
- "I couldn't validate that token. Please make sure it's correct, or you can generate a new one in your account settings."

Generate only the message, nothing else."""

        try:
            # Create LLM instance from config
            from ...services.llm import LLM

            llm = LLM(
                provider=text_model_config.get("provider"),
                model=text_model_config.get("model"),
                temperature=0.7,
                max_tokens=100,
                **text_model_config.get("settings", {}),
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The credential for {service} failed validation."},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip()
        except Exception as e:
            print(f"Warning: Failed to generate failure message via LLM: {e}")
            return (
                f"That {service} token didn't work. "
                f"Please double-check the token or create a new one in your {service} settings."
            )

    async def _generate_duplicate_message(self, service: str) -> str:
        """Generate message for duplicate token respecting persona."""
        # Get LLM configuration
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            # Fallback if no LLM available
            return f"That {service} token is already stored in your account. You're all set!"

        system_prompt = """Generate a friendly message when a user provides a credential that's already stored.

The message should:
- Explain the token is already in their account
- Reassure them they can use it
- Be understanding, not frustrating
- Keep it brief (1-2 sentences)

Example good responses:
- "That token is already saved in your account! You're all set to use the service."
- "I already have that token stored for you. Ready to go!"

Return ONLY the message text, no quotes."""

        try:
            # Create LLM for message generation
            model_name = text_model_config.get("model")
            cache_key = f"text_model_{model_name}"

            if cache_key not in self.overlord._model_cache:
                # Filter out params we're setting explicitly to avoid duplicate kwargs
                settings = {k: v for k, v in text_model_config.get("settings", {}).items()
                           if k not in ["temperature", "max_tokens"]}
                llm = await self.overlord.create_model(
                    model=model_name,
                    api_key=text_model_config.get("api_key"),
                    temperature=0.7,
                    max_tokens=100,
                    **settings,
                )
                self.overlord._model_cache[cache_key] = llm
            else:
                llm = self.overlord._model_cache[cache_key]

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The {service} credential is already stored."},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip()
        except Exception as e:
            print(f"Warning: Failed to generate duplicate message via LLM: {e}")
            # Fallback message
            return f"That {service} token is already stored in your account. You're all set!"

    async def _generate_success_message(self, service: str, account_name: str) -> str:
        """Generate success message respecting persona."""
        # Get LLM configuration
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            # Fallback if no LLM available
            return f"Successfully connected to {service} as {account_name}!"

        system_prompt = """Generate a brief, friendly confirmation message for successful credential authentication.

The message should:
- Confirm successful connection
- Mention the account name
- Be conversational and positive
- Keep it to 1 sentence

Example good responses:
- "Great! I've successfully connected to your account."
- "Perfect! You're now connected as the specified account."
- "All set! I can now access your account."

Generate only the message, nothing else."""

        try:
            # Get or create LLM instance
            # Create a hashable cache key from the config
            cache_key = ("text", text_model_config.get("provider"), text_model_config.get("model"))
            if cache_key not in self.overlord._model_cache:
                from ...services.llm import LLM

                llm = LLM(
                    provider=text_model_config.get("provider"),
                    model=text_model_config.get("model"),
                    temperature=0.7,
                    max_tokens=50,
                    **text_model_config.get("settings", {}),
                )
                self.overlord._model_cache[cache_key] = llm
            else:
                llm = self.overlord._model_cache[cache_key]

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Successfully connected to {service} as {account_name}."},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip()
        except Exception as e:
            print(f"Warning: Failed to generate success message via LLM: {e}")
            return f"Successfully connected to {service} as {account_name}!"

    async def _generate_cancellation_message(self) -> str:
        """Generate cancellation message respecting persona."""
        # Get LLM configuration
        text_model_config = self.overlord._capability_models.get("text")
        if not text_model_config:
            return "No problem! Let me know if you'd like to add credentials later."

        system_prompt = """Generate a brief, understanding message when a user cancels providing credentials.

The message should:
- Acknowledge their choice
- Be supportive and not pushy
- Mention they can add credentials later if needed
- Keep it to 1-2 sentences

Example good responses:
- "No problem! Let me know if you'd like to add credentials later."
- "Sure, no worries! You can always add your credentials when you're ready."
- "Understood! Feel free to add credentials anytime you need them."

Generate only the message, nothing else."""

        try:
            # Get or create LLM instance
            # Create a hashable cache key from the config
            cache_key = ("text", text_model_config.get("provider"), text_model_config.get("model"))
            if cache_key not in self.overlord._model_cache:
                from ...services.llm import LLM

                llm = LLM(
                    provider=text_model_config.get("provider"),
                    model=text_model_config.get("model"),
                    temperature=0.7,
                    max_tokens=50,
                    **text_model_config.get("settings", {}),
                )
                self.overlord._model_cache[cache_key] = llm
            else:
                llm = self.overlord._model_cache[cache_key]

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "User cancelled providing credentials."},
            ]
            response_obj = await llm.chat(messages)
            response = response_obj.content if hasattr(response_obj, "content") else str(response_obj)
            return response.strip()
        except Exception as e:
            print(f"Warning: Failed to generate cancellation message via LLM: {e}")
            return "No problem! Let me know if you'd like to add credentials later."

    def _get_redirect_reason(self, auth_type: str) -> str:
        """Get user-friendly reason for redirect."""
        if auth_type in ["oauth", "oauth2", "oauth2_flow"]:
            return "OAuth authentication requires browser-based authorization flow."

        if auth_type == "bearer":
            return (
                "This service requires bearer token authentication through external configuration."
            )

        if auth_type == "unknown":
            return "Authentication type could not be determined."

        return (
            f"{auth_type.capitalize()} authentication requires external configuration for security."
        )

    def validate_credential_data(self, credential_data: Any, service: str) -> bool:
        """
        Validate credential data structure before storing.

        Args:
            credential_data: The credential data to validate
            service: The service name for validation context

        Returns:
            True if valid, False otherwise
        """
        if not credential_data:
            return False

        # Basic validation - ensure it's not empty or whitespace
        if isinstance(credential_data, str):
            return bool(credential_data.strip())

        # For dict credentials, ensure required fields exist
        if isinstance(credential_data, dict):
            return bool(credential_data.get("value") or credential_data.get("token"))

        return False

    async def parse_credential_selection(
        self, clarification_response: str, clarification_request
    ) -> Optional[Dict[str, Any]]:
        """
        Parse user's credential selection from clarification response.

        Args:
            clarification_response: User's response to credential selection
            clarification_request: Original clarification request

        Returns:
            Dict with selected credential info or None if parsing failed
        """
        # This would parse the user's selection and return the appropriate credential
        # Implementation depends on clarification system integration
        # For now, return None as placeholder
        return None
