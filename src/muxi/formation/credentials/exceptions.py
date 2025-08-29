"""
Credential-related exceptions for the formation system.
"""

from typing import Optional, Dict, Any, List
from ...datatypes.exceptions import FormationError


class MissingCredentialError(FormationError):
    """Raised when a required user credential is not found."""

    def __init__(self, service: str, user_id: str):
        self.service = service
        self.user_id = user_id
        super().__init__(
            f"Missing credential for service '{service}' for user '{user_id}'",
            {
                "service": service,
                "user_id": user_id,
                "error_type": "missing_credential",
            }
        )


class AmbiguousCredentialError(FormationError):
    """Raised when multiple credentials exist but selection is ambiguous."""

    def __init__(
        self,
        service: str,
        user_id: str,
        available_credentials: List[str],
        ordered_credentials: Optional[List[int]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.service = service
        self.user_id = user_id
        self.available_credentials = available_credentials
        self.ordered_credentials = ordered_credentials or []
        creds_str = ", ".join(available_credentials)
        message = (
            f"Multiple credentials available for service '{service}' "
            f"for user '{user_id}': {creds_str}. Please specify which one to use."
        )
        super().__init__(message, details)
