"""
Credential Clarification Handler

Handles clarification requests for missing user credentials.
"""

from typing import Dict, Any, Optional
from ...datatypes.clarification import (
    ClarificationRequest,
    ClarificationResponse,
    RequestType,
    ClarificationQuestion,
    QuestionStyle,
)
from ..memory.credential_resolver import AmbiguousCredentialError


class CredentialClarificationHandler:
    """Handles clarification requests for missing user credentials."""

    def generate_credential_request(
        self,
        service: str,
        user_id: str,
        agent_id: str = "system",
        context: Optional[Dict[str, Any]] = None,
    ) -> ClarificationRequest:
        """
        Generate a clarification request for missing credentials.

        Args:
            service: The service name (lowercase)
            user_id: The user ID requesting the credential
            agent_id: The agent ID (defaults to "system")
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

        # Create the clarification question
        clarification_question = ClarificationQuestion(
            question_id=f"credential_{service}",
            question_text=message,
            parameter_name="credential",
            parameter_type="credential",
            parameter_description=f"{display_name} credential",
            required=True,
            validation_rules={"min_length": 8},
            context_hints=[f"This credential is needed for {display_name} integration"],
            style=QuestionStyle.CONVERSATIONAL,
        )

        # Create the clarification request
        return ClarificationRequest(
            user_id=user_id,
            agent_id=agent_id,
            request_type=RequestType.TOOL_CALL,
            tool_name=context.get("tool_name") if context else None,
            intent=f"Request {service} credentials",
            missing_info=[f"{service}_credential"],
            clarification_plan=[clarification_question],
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
                    field_name = self._determine_field_name(service)
                    return {field_name: value}

        # If not found in structured response, check if it's in the raw text
        # This handles cases where users just paste the credential
        if hasattr(response, "raw_response") and response.raw_response:
            text = response.raw_response.strip()
            if text:
                field_name = self._determine_field_name(service)
                return {field_name: text}

        return None

    def validate_credential_format(self, service: str, credential: str) -> bool:
        """
        Basic validation of credential format.

        Args:
            service: The service name (reserved for future service-specific validation)
            credential: The credential string to validate

        Returns:
            True if format looks valid, False otherwise

        Note:
            The service parameter is kept for future enhancements where we might
            implement service-specific validation rules (e.g., GitHub tokens start
            with 'ghp_', OpenAI keys start with 'sk-', etc.)
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

    def generate_ambiguous_credential_request(
        self,
        error: AmbiguousCredentialError,
        agent_id: str = "system",
        context: Optional[Dict[str, Any]] = None,
    ) -> ClarificationRequest:
        """
        Generate a clarification request for ambiguous credential selection.

        Args:
            error: The AmbiguousCredentialError containing available credentials and ordering
            agent_id: The agent ID (defaults to "system")
            context: Optional context about why the credential is needed

        Returns:
            ClarificationRequest for credential selection
        """
        # Format service name for display
        display_name = self._format_service_name(error.service)

        # Get ordered credential names using LLM ordering
        available_creds = error.available_credentials
        ordered_indices = error.ordered_credentials

        # Create ordered list of credential names
        if ordered_indices:
            # Use LLM ordering - convert 1-based indices to 0-based
            ordered_names = []
            for idx in ordered_indices:
                if 1 <= idx <= len(available_creds):
                    ordered_names.append(available_creds[idx - 1]["name"])
        else:
            # Fallback to original order
            ordered_names = [cred["name"] for cred in available_creds]

        # Build the message
        message_parts = [
            f"I found multiple {display_name} accounts for you.",
            "Which account would you like to use?",
        ]

        # Add the credential options in smart order
        options_text = "\n".join(
            [f"{i+1}. {name}" for i, name in enumerate(ordered_names)]
        )
        message_parts.append(f"\nAvailable accounts:\n{options_text}")

        message = " ".join(message_parts)

        # Create the clarification question
        clarification_question = ClarificationQuestion(
            question_id=f"select_credential_{error.service}",
            question_text=message,
            parameter_name="credential_selection",
            parameter_type="choice",
            parameter_description=f"Selected {display_name} credential",
            required=True,
            validation_rules={
                "type": "choice",
                "options": [{"value": name, "label": name} for name in ordered_names],
            },
            context_hints=[f"Choose which {display_name} account to use"],
            style=QuestionStyle.CONVERSATIONAL,
        )

        # Create the clarification request
        return ClarificationRequest(
            user_id=error.user_id,
            agent_id=agent_id,
            request_type=RequestType.TOOL_CALL,
            tool_name=context.get("tool_name") if context else None,
            intent=f"Select {error.service} credential from multiple options",
            missing_info=[f"{error.service}_credential_selection"],
            clarification_plan=[clarification_question],
            context=(
                {
                    "reason": "ambiguous_credential",
                    "service": error.service,
                    "available_credentials": [cred["name"] for cred in available_creds],
                    "ordered_credentials": ordered_names,
                    **context,
                }
                if context
                else {
                    "reason": "ambiguous_credential",
                    "service": error.service,
                    "available_credentials": [cred["name"] for cred in available_creds],
                    "ordered_credentials": ordered_names,
                }
            ),
        )

    def _determine_field_name(self, service: str) -> str:
        """
        Determine the appropriate field name for the credential.

        Args:
            service: The service name

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
