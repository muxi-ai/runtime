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
                **text_model_config.get("settings", {})
            )
            self.overlord._model_cache[cache_key] = llm

        # Get available services that use user credentials
        available_services = list(self.overlord._mcp_servers_with_user_credentials.values())
        if not available_services:
            return None

        services_str = ", ".join([s["service"] for s in available_services])

        prompt = f"""Analyze the user's message to determine if it involves credential-enabled services.

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

2. SERVICE_USE - User wants to use a service (but may lack credentials):
   - "List my GitHub repositories"
   - "Get my account balance"
   - "Show my pull requests"
   - "Check my issues"

3. NONE - Neither credential management nor service use:
   - General questions, help requests, other topics

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
            if '{' in response and '}' in response:
                json_start = response.index('{')
                json_end = response.rindex('}') + 1
                json_str = response[json_start:json_end]
                detection = json.loads(json_str)
            else:
                return None

            if detection["type"] == "NONE":
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
                    "confidence": detection.get("confidence", 0.0)
                }

            # For SERVICE_USE - ALWAYS return None
            # Let the normal flow (MCP service) handle credential selection
            # The MCP service will detect if there are multiple credentials
            # and raise AmbiguousCredentialError if needed
            if detection["type"] == "SERVICE_USE":
                return None

        except Exception:
            # Failed to detect credential need via LLM
            pass
            return None

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
                **text_model_config.get("settings", {})
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
        session_id: Optional[str] = None
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
                "Please configure your API credentials in the external credential manager."
            )

            return {
                "action": "redirect",
                "message": f"{redirect_message}\n\nService '{service}' requires authentication.",
                "mode": "redirect"
            }

        elif mode == "dynamic":
            # Check if service accepts inline credentials
            accept_inline = detection_result.get("accept_inline", False)
            auth_type = detection_result.get("auth_type", "bearer")

            if accept_inline:
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
                    "auth_type": auth_type
                }
            else:
                # Cannot accept inline, fall back to redirect
                redirect_message = cred_config.get(
                    "redirect_message",
                    "Please configure your API credentials in the external credential manager."
                )
                reason = self._get_redirect_reason(auth_type)

                return {
                    "action": "redirect",
                    "message": f"{redirect_message}\n\n{reason}\n\nService '{service}' requires authentication.",
                    "mode": "redirect_fallback"
                }

        # Unknown mode, default to redirect
        redirect_message = cred_config.get(
            "redirect_message",
            "Please configure your API credentials in the external credential manager."
        )

        return {
            "action": "redirect",
            "message": f"{redirect_message}\n\nService '{service}' requires authentication.",
            "mode": "redirect_default"
        }

    async def _generate_credential_prompt(
        self, service: str, service_id: str, auth_type: str
    ) -> str:
        """Generate appropriate prompt for credential collection."""
        base_prompt = f"Please provide the {auth_type} for '{service}':"

        if auth_type == "basic":
            return (
                "⚠️ Security Warning: Basic authentication transmits credentials in a reversible format.\n"
                "Only provide these credentials if you trust this environment.\n\n"
                f"{base_prompt}\n"
                "Format: username:password"
            )

        elif auth_type == "api_key":
            return f"{base_prompt}\n\nNote: Your API key will be securely stored for this session."

        elif auth_type == "bearer":
            return (
                f"{base_prompt}\n\n"
                "Please provide your personal access token or bearer token."
            )

        # Generic prompt for other types
        return base_prompt

    def _get_redirect_reason(self, auth_type: str) -> str:
        """Get user-friendly reason for redirect."""
        if auth_type in ["oauth", "oauth2", "oauth2_flow"]:
            return "OAuth authentication requires browser-based authorization flow."

        if auth_type == "bearer":
            return "This service requires bearer token authentication through external configuration."

        if auth_type == "unknown":
            return "Authentication type could not be determined."

        return f"{auth_type.capitalize()} authentication requires external configuration for security."

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
