# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Credential Manager - Secure Credential Access
# Description:  Manages credentials for MCP servers and framework components
# Role:         Provides secure credential resolution with database and secrets support
# Usage:        Used by components needing secure credential access
# Author:       Muxi Framework Team
#
# The Credential Manager provides a centralized way to access credentials from
# multiple sources with a defined priority order. It supports both system-wide
# and user-specific credentials, with database storage, encrypted secrets, and
# secure credential resolution.
#
# Credential resolution order:
# 1. User-specific credential from database (if user_id provided)
# 2. System-wide credential from database
# 3. Encrypted secrets using SecretsManager
#
# This ensures secure handling of sensitive information while providing
# flexible credential management for different use cases.
# =============================================================================

from typing import Any, Dict, List, Optional


class CredentialManager:
    """
    Manage credentials for MCP servers and framework components.

    The CredentialManager provides a centralized way to access credentials from
    multiple sources with a defined priority order. It supports both system-wide
    and user-specific credentials, with database storage and encrypted secrets
    support instead of environment variables.
    """

    def __init__(
        self,
        credential_db_connection_string: Optional[str] = None,
        secrets_manager: Optional[Any] = None
    ):
        """
        Initialize the credential manager.

        Creates a credential manager that can access credentials from database
        and encrypted secrets. Encrypted secrets are preferred over environment
        variables for security.

        Args:
            credential_db_connection_string: Database connection string for credential storage.
                If None, only encrypted secrets will be used for credential retrieval.
            secrets_manager: SecretsManager instance for encrypted credential access.
                If None, credential resolution will only use database storage.
        """
        self.connection_string = credential_db_connection_string
        self.db_available = credential_db_connection_string is not None
        self.secrets_manager = secrets_manager

    def get_credential(self, credential_id: str, user_id: Optional[int] = None) -> Optional[str]:
        """
        Get a credential by ID, optionally for a specific user.

        This method tries to retrieve credentials in the following order:
        1. User-specific credential from database (if user_id provided)
        2. System-wide credential from database
        3. Encrypted secrets using SecretsManager

        Args:
            credential_id: ID of the credential to retrieve. Used as key in database
                and for encrypted secrets lookup.
            user_id: Optional user ID for user-specific credentials. When provided,
                the system will first look for credentials specific to this user.

        Returns:
            Optional[str]: The credential value if found, or None if not found in any source.
        """
        if not credential_id:
            return None

        # First try user-specific credential if user_id is provided
        if user_id is not None and self.db_available:
            user_credential = self._get_user_credential(credential_id, user_id)
            if user_credential:
                return user_credential

        # Then try system-wide credential from database
        if self.db_available:
            system_credential = self._get_system_credential(credential_id)
            if system_credential:
                return system_credential

        # Finally, try encrypted secrets
        if self.secrets_manager:
            try:
                # Convert credential_id to standard secret name format
                secret_name = credential_id.upper()
                return self.secrets_manager.get_secret(secret_name)
            except Exception:
                # Log error but don't fail - return None
                return None

        return None

    def _get_user_credential(self, credential_id: str, user_id: int) -> Optional[str]:
        """
        Get a user-specific credential from the database.

        This internal method retrieves a credential that is specific to a particular user.
        Note: This is currently a placeholder that should be replaced with actual
        database access code in a production implementation.

        Args:
            credential_id: ID of the credential to look up in the database.
            user_id: User ID to find credentials for.

        Returns:
            Optional[str]: The credential value if found, or None if not found or on error.
        """
        # This is a placeholder that should be replaced with actual database access code
        # In a real implementation, this would query the credentials table
        try:
            # Example of how this might work with a real database
            # query = "SELECT value FROM credentials WHERE credential_id = ? AND user_id = ?"
            # result = database.execute_query(query, (credential_id, user_id))
            # return result[0] if result else None
            return None
        except Exception:
            return None

    def _get_system_credential(self, credential_id: str) -> Optional[str]:
        """
        Get a system-wide credential from the database.

        This internal method retrieves a credential that is available to all users.
        Note: This is currently a placeholder that should be replaced with actual
        database access code in a production implementation.

        Args:
            credential_id: ID of the credential to look up in the database.

        Returns:
            Optional[str]: The credential value if found, or None if not found or on error.
        """
        # This is a placeholder that should be replaced with actual database access code
        # In a real implementation, this would query the credentials table
        try:
            # Example of how this might work with a real database
            # query = "SELECT value FROM credentials WHERE credential_id = ? AND user_id IS NULL"
            # result = database.execute_query(query, (credential_id,))
            # return result[0] if result else None
            return None
        except Exception:
            return None

    def resolve_mcp_credentials(
        self, mcp_config: Dict[str, Any], user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Resolve credentials for an MCP server configuration.

        This method processes an MCP server configuration and resolves any credential
        references it contains. It handles both required and optional credentials,
        and can map credential IDs to different parameter names if needed.

        Args:
            mcp_config: MCP server configuration dictionary, potentially containing
                a "credentials" key with credential specifications.
            user_id: Optional user ID for user-specific credentials.

        Returns:
            Dict[str, Any]: The MCP server configuration with resolved credentials
                added to the "args" section.

        Raises:
            ValueError: If a required credential is not found in any available source.
        """
        if "credentials" not in mcp_config:
            return mcp_config

        # Get credentials configuration
        credentials_config = mcp_config["credentials"]
        result_args = mcp_config.get("args", {}).copy()

        # Handle single credential object
        if isinstance(credentials_config, dict):
            credentials_config = [credentials_config]

        # Handle list of credentials
        if isinstance(credentials_config, list):
            for cred_config in credentials_config:
                # Get credential details
                cred_id = cred_config.get("id")
                param_name = cred_config.get("param_name", cred_id)
                required = cred_config.get("required", False)

                # Get credential value
                value = self.get_credential(cred_id, user_id)

                # Handle required credential not found
                if required and value is None:
                    raise ValueError(f"Required credential not found: {cred_id}")

                # Add credential to args if found
                if value is not None:
                    result_args[param_name] = value

        # Update args in the result config
        result = mcp_config.copy()
        result["args"] = result_args

        return result

    def resolve_all_mcp_credentials(
        self, mcp_configs: List[Dict[str, Any]], user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Resolve credentials for multiple MCP server configurations.

        This is a convenience method to resolve credentials for a list of MCP server
        configurations in a single call.

        Args:
            mcp_configs: List of MCP server configuration dictionaries to process.
            user_id: Optional user ID for user-specific credentials.

        Returns:
            List[Dict[str, Any]]: The MCP server configurations with all available
                credentials resolved and added to their respective "args" sections.
        """
        return [self.resolve_mcp_credentials(mcp_config, user_id) for mcp_config in mcp_configs]
