"""
Credential handling logic for the formation system.
Moved from overlord.py to proper separation of concerns.
"""

from typing import Dict, Optional, Any


class CredentialHandler:
    """
    Handles credential detection, validation, and processing.
    Separated from overlord for better architecture.
    """

    def __init__(self, overlord):
        """Initialize with reference to overlord for accessing services."""
        self.overlord = overlord
        self._pending = {}  # session_id -> {service, service_id, auth_type, timestamp}

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
            llm = await self.overlord.create_model(
                model=model_name,
                api_key=text_model_config.get("api_key"),
                temperature=0.0,
                max_tokens=100,
                **text_model_config.get("settings", {}),
            )
            self.overlord._model_cache[cache_key] = llm

        # Get available services that use user credentials
        available_services = list(self.overlord._mcp_servers_with_user_credentials.values())
        if not available_services:
            return None

        services_str = ", ".join([s["service"] for s in available_services])

        prompt = f"""Analyze the user's message to determine if it requires credentials for external services.

Available credential services: {services_str}

User message: {message}

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
            response = await llm.generate_text(prompt)

            # Parse JSON response
            # Extract JSON from response if it contains other text
            import json

            if "{" in response and "}" in response:
                json_start = response.index("{")
                json_end = response.rindex("}") + 1
                json_str = response[json_start:json_end]
                detection = json.loads(json_str)
            else:
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

        except Exception:
            # Failed to detect credential need via LLM
            pass
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

        print(f"Validating credential for {service}: {credential[:20]}...")

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
        from muxi.services.mcp.handler import MCPHandler
        import asyncio

        handler = MCPHandler(model=None, tool_registry=self.overlord.mcp_service.tool_registry)

        try:
            success = await asyncio.wait_for(
                handler.connect_server(
                    name=f"{service_id}_validation",
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
                # Try to disconnect
                try:
                    await asyncio.wait_for(
                        handler.disconnect_server(f"{service_id}_validation"), timeout=1.0
                    )
                except Exception:
                    pass
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

    async def handle_credential_response(self, message: str, session_id: str, user_id: str):
        """Handle response to credential prompt - with retry loop."""
        if session_id not in self._pending:
            return None

        # Check for cancellation first
        if await self._is_cancellation(message):
            self._pending.pop(session_id)  # Clear state
            return await self._generate_cancellation_message()

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
                user_id=user_id,
                service=pending["service"],
                credentials=credential
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
                    print(f"DEBUG: Storing credential for user_id={user_id}, service={pending['service']}")
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
                    import traceback
                    traceback.print_exc()
                    raise  # Re-raise to be caught by outer exception handler

                # Async update the name (fire and forget, don't wait or block)
                import asyncio

                asyncio.create_task(
                    self.overlord.credential_resolver.update_credential_name_with_discovery(
                        user_id=user_id,
                        service=pending["service"],
                        mcp_service=self.overlord.mcp_service,
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
            import traceback
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
            llm = await self.overlord.create_model(
                model=model_name,
                api_key=text_model_config.get("api_key"),
                temperature=0.0,
                max_tokens=10,
                **text_model_config.get("settings", {}),
            )
            self.overlord._model_cache[cache_key] = llm

        prompt = f"""Analyze this message to determine if the user is asking to ADD or CONFIGURE new credentials.

User message: {message}

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
            response = await llm.generate_text(prompt)

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

        prompt = f"""
Generate a natural, friendly message asking the user to provide their {auth_description} for {service}.

Important:
- Be conversational and friendly
- Mention that credentials will be stored securely
- Keep it brief (1-2 sentences)
- Match the user's language if they're not using English
- Don't use technical jargon like 'bearer token' - use friendly terms

Example good responses:
- "I'll need your GitHub personal access token to continue. Could you share it with me?"
- "To access your GitHub repositories, I'll need your access token. Don't worry, I'll store it securely."

Generate the message now:"""

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

            response = await llm.generate_text(prompt)
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
        prompt = f"""The user is in the middle of providing credentials.
        They just said: "{message}"

        Are they trying to cancel/abort/skip the credential entry process?

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

        Respond with only YES or NO."""

        try:
            from ...services.llm import LLM

            llm = LLM()
            response = await llm.generate_text(prompt, max_tokens=10)
            return response.strip().upper().startswith("YES")
        except Exception:
            # On LLM failure, assume not cancellation to avoid accidental exits
            return False

    async def _extract_credential_from_text(self, message: str) -> str:
        """Extract credential from natural language using LLM."""
        prompt = f"""The user is providing an API credential/token.
        They said: "{message}"

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
            from ...services.llm import LLM

            llm = LLM()
            extracted = await llm.generate_text(prompt, max_tokens=100)
            # Clean up any quotes the LLM might have added
            return extracted.strip().strip('"').strip("'")
        except Exception:
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

        prompt = f"""The user just provided a {service} credential but it failed validation.

Generate a helpful, understanding message that:
- Gently explains the token didn't work
- Suggests they double-check the token
- Mentions they should check their {service} account settings to create a new token if needed
- Is supportive, not frustrating
- Keeps it brief (2-3 sentences)
- Do NOT include specific URLs
- Let them know they can provide a different token or move on

Example good responses:
- "Hmm, that token didn't seem to work. Could you double-check it? You can also create a new one in your {service} settings."
- "I couldn't validate that token. Please make sure it's correct, or you can generate a new one in your {service} account settings."

Generate the message now:"""

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
            response = await llm.generate_text(prompt)
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

        prompt = f"""The user just provided a {service} credential but it's already stored (duplicate).

Generate a friendly message that:
- Explains the token is already in their account
- Reassures them they can use it
- Is understanding, not frustrating
- Keeps it brief (1-2 sentences)

Example good responses:
- "That token is already saved in your account! You're all set to use {service}."
- "I already have that {service} token stored for you. Ready to go!"

Return ONLY the message text, no quotes."""

        try:
            # Create LLM for message generation
            model_name = text_model_config.get("name")
            cache_key = f"text_model_{model_name}"

            if cache_key not in self.overlord._model_cache:
                llm = await self.overlord.create_model(
                    model=model_name,
                    api_key=text_model_config.get("api_key"),
                    temperature=0.7,
                    max_tokens=100,
                    **text_model_config.get("settings", {}),
                )
                self.overlord._model_cache[cache_key] = llm
            else:
                llm = self.overlord._model_cache[cache_key]

            response = await llm.generate_text(prompt)
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

        prompt = f"""The user just provided their credentials and successfully authenticated with {service}.
Their account name is: {account_name}

Generate a brief, friendly confirmation message that:
- Confirms successful connection
- Mentions the account name
- Is conversational and positive
- Keeps it to 1 sentence

Example good responses:
- "Great! I've successfully connected to GitHub as {account_name}."
- "Perfect! You're now connected to GitHub as {account_name}."
- "All set! I can now access your GitHub account ({account_name})."

Generate the message now:"""

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

            response = await llm.generate_text(prompt)
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

        prompt = """The user just cancelled providing their API credentials.

Generate a brief, understanding message that:
- Acknowledges their choice
- Is supportive and not pushy
- Mentions they can add credentials later if needed
- Keeps it to 1-2 sentences

Example good responses:
- "No problem! Let me know if you'd like to add credentials later."
- "Sure, no worries! You can always add your credentials when you're ready."
- "Understood! Feel free to add credentials anytime you need them."

Generate the message now:"""

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

            response = await llm.generate_text(prompt)
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
