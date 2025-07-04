"""
Credential Clarification Handler

Handles clarification requests for missing user credentials.
"""

from typing import Dict, Any, Optional
from ...datatypes.clarification import ClarificationRequest, ClarificationResponse


class CredentialClarificationHandler:
    """Handles clarification requests for missing user credentials."""

    def generate_credential_request(
        self, service: str, context: Optional[Dict[str, Any]] = None
    ) -> ClarificationRequest:
        """
        Generate a clarification request for missing credentials.

        Args:
            service: The service name (lowercase)
            context: Optional context about why the credential is needed

        Returns:
            ClarificationRequest for the missing credential
        """
        # Format service name for display
        display_name = self._format_service_name(service)

        # Build the message
        message_parts = [f"I need your {display_name} credentials to continue."]

        # Add context if provided
        if context:
            tool_name = context.get("tool_name")
            if tool_name:
                message_parts.append(f"This is required to use the '{tool_name}' tool.")

        # Add generic credential request
        message_parts.append(
            f"Please provide your {display_name} credentials (API key, token, or authentication details)."
        )

        message = " ".join(message_parts)

        # Create the clarification request
        return ClarificationRequest(
            request_type="credential_required",
            questions=[
                {
                    "id": f"credential_{service}",
                    "question": message,
                    "type": "credential",
                    "metadata": {
                        "service": service,
                        "display_name": display_name,
                        "secure": True,  # Indicates this should be handled securely
                    },
                }
            ],
            context=(
                {"reason": "missing_credential", "service": service, **context}
                if context
                else {"reason": "missing_credential", "service": service}
            ),
        )

    def parse_credential_response(
        self, response: ClarificationResponse, service: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a clarification response to extract credentials.

        Args:
            response: The clarification response from the user
            service: The service name we're expecting credentials for

        Returns:
            Dictionary with credential data or None if parsing failed
        """
        if not response.answers:
            return None

        # Look for the credential answer
        for answer in response.answers:
            if answer.get("id") == f"credential_{service}":
                value = answer.get("answer", "").strip()
                if value:
                    field_name = self._determine_field_name(service, value)
                    return {field_name: value}

        # If not found in structured response, check if it's in the raw text
        # This handles cases where users just paste the credential
        if hasattr(response, "raw_response") and response.raw_response:
            text = response.raw_response.strip()
            if text:
                field_name = self._determine_field_name(service, text)
                return {field_name: text}

        return None

    def validate_credential_format(self, service: str, credential: str) -> bool:  # noqa: ARG002
        """
        Basic validation of credential format.

        Args:
            service: The service name
            credential: The credential string to validate

        Returns:
            True if format looks valid, False otherwise
        """
        if not credential or not isinstance(credential, str):
            return False

        # Remove whitespace
        credential = credential.strip()

        # Generic validation - just ensure it's not empty and reasonable length
        # The actual validation should be done by attempting to use the credential
        return len(credential) >= 8

    def _format_service_name(self, service: str) -> str:
        """
        Format service name for display.

        Args:
            service: The service name (lowercase)

        Returns:
            Formatted display name
        """
        # Handle common services with special formatting
        special_cases = {
            "github": "GitHub",
            "gitlab": "GitLab",
            "openai": "OpenAI",
            "mongodb": "MongoDB",
            "postgresql": "PostgreSQL",
            "mysql": "MySQL",
            "redis": "Redis",
            "elasticsearch": "Elasticsearch",
            "aws": "AWS",
            "gcp": "GCP",
            "azure": "Azure",
        }

        if service.lower() in special_cases:
            return special_cases[service.lower()]

        # Default: capitalize each word
        return service.replace("_", " ").replace("-", " ").title()

    def _determine_field_name(self, service: str, credential: str) -> str:  # noqa: ARG002
        """
        Determine the appropriate field name for the credential.

        Args:
            service: The service name
            credential: The credential value

        Returns:
            Field name to use (e.g., 'token', 'api_key', 'key')
        """
        # Simple heuristic based on service name
        service_lower = service.lower()

        # Check service name for hints
        if "token" in service_lower:
            return "token"
        elif "api" in service_lower or "key" in service_lower:
            return "api_key"

        # Check common patterns in service names
        if service_lower in ["github", "gitlab", "slack", "discord", "bitbucket"]:
            return "token"
        elif service_lower in ["openai", "anthropic", "cohere", "pinecone"]:
            return "api_key"

        # Generic fallback - most modern APIs use either token or api_key
        return "token"
