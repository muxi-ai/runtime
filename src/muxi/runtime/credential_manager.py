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

# Import observability components
from .observability import ObservabilityManager, EventType, EventLevel


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

        # Emit initialization event
        try:
            observability_manager = ObservabilityManager.get_instance()
            observability_manager.event_logger.emit_event(
                event_type=EventType.REQUEST_PROCESSING,
                level=EventLevel.INFO,
                data={
                    'component': 'credential_manager',
                    'operation': 'initialization',
                    'db_available': self.db_available,
                    'secrets_manager_available': self.secrets_manager is not None,
                    'connection_string_provided': credential_db_connection_string is not None
                },
                description='CredentialManager initialized with configuration'
            )
        except Exception:
            # Don't fail initialization due to observability issues
            pass

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
        # Emit credential retrieval start event
        try:
            observability_manager = ObservabilityManager.get_instance()
            event_id = observability_manager.event_logger.emit_event(
                event_type=EventType.REQUEST_PROCESSING,
                level=EventLevel.INFO,
                data={
                    'component': 'credential_manager',
                    'operation': 'credential_retrieval',
                    'credential_id': credential_id,
                    'user_id': user_id,
                    'has_credential_id': bool(credential_id),
                    'db_available': self.db_available,
                    'secrets_manager_available': self.secrets_manager is not None
                },
                description=f'Starting credential retrieval for {credential_id}'
            )
        except Exception:
            # Don't fail credential retrieval due to observability issues
            event_id = None

        if not credential_id:
            # Emit validation failure event
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_DENIED_VALIDATION,
                        level=EventLevel.WARNING,
                        data={
                            'component': 'credential_manager',
                            'operation': 'credential_retrieval',
                            'error': 'empty_credential_id',
                            'credential_id': credential_id
                        },
                        description='Credential retrieval failed: empty credential_id',
                        parent_event_id=event_id
                    )
            except Exception:
                pass
            return None

        credential_value = None
        sources_tried = []

        try:
            # First try user-specific credential if user_id is provided
            if user_id is not None and self.db_available:
                sources_tried.append('user_database')
                user_credential = self._get_user_credential(credential_id, user_id)
                if user_credential:
                    credential_value = user_credential

            # Then try system-wide credential from database
            if credential_value is None and self.db_available:
                sources_tried.append('system_database')
                system_credential = self._get_system_credential(credential_id)
                if system_credential:
                    credential_value = system_credential

            # Finally, try encrypted secrets
            if credential_value is None and self.secrets_manager:
                sources_tried.append('encrypted_secrets')
                try:
                    # Convert credential_id to standard secret name format
                    secret_name = credential_id.upper()
                    secret_value = self.secrets_manager.get_secret(secret_name)
                    if secret_value:
                        credential_value = secret_value
                except Exception:
                    # Log error but don't fail - continue with None
                    pass

            # Emit completion event
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_COMPLETED,
                        level=EventLevel.INFO,
                        data={
                            'component': 'credential_manager',
                            'operation': 'credential_retrieval',
                            'credential_id': credential_id,
                            'user_id': user_id,
                            'credential_found': credential_value is not None,
                            'sources_tried': sources_tried,
                            'source_count': len(sources_tried)
                        },
                        description=f'Credential retrieval completed for {credential_id}',
                        parent_event_id=event_id
                    )
            except Exception:
                pass

            return credential_value

        except Exception as e:
            # Emit error event
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_FAILED,
                        level=EventLevel.ERROR,
                        data={
                            'component': 'credential_manager',
                            'operation': 'credential_retrieval',
                            'credential_id': credential_id,
                            'user_id': user_id,
                            'error': str(e),
                            'error_type': type(e).__name__,
                            'sources_tried': sources_tried
                        },
                        description=f'Credential retrieval failed for {credential_id}: {str(e)}',
                        parent_event_id=event_id
                    )
            except Exception:
                pass
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
        # Emit user credential retrieval start event
        try:
            observability_manager = ObservabilityManager.get_instance()
            event_id = observability_manager.event_logger.emit_event(
                event_type=EventType.REQUEST_PROCESSING,
                level=EventLevel.DEBUG,
                data={
                    'component': 'credential_manager',
                    'operation': 'user_credential_retrieval',
                    'credential_id': credential_id,
                    'user_id': user_id,
                    'source': 'user_database'
                },
                description=(f'Retrieving user-specific credential {credential_id} '
                             f'for user {user_id}')
            )
        except Exception:
            observability_manager = None
            event_id = None

        # This is a placeholder that should be replaced with actual database access code
        # In a real implementation, this would query the credentials table
        try:
            # Example of how this might work with a real database
            # query = "SELECT value FROM credentials WHERE credential_id = ? AND user_id = ?"
            # result = database.execute_query(query, (credential_id, user_id))
            # return result[0] if result else None

            # Emit completion event for placeholder implementation
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_COMPLETED,
                        level=EventLevel.DEBUG,
                        data={
                            'component': 'credential_manager',
                            'operation': 'user_credential_retrieval',
                            'credential_id': credential_id,
                            'user_id': user_id,
                            'source': 'user_database',
                            'credential_found': False,
                            'implementation_status': 'placeholder'
                        },
                        description=('User credential retrieval completed '
                                     '(placeholder implementation)'),
                        parent_event_id=event_id
                    )
            except Exception:
                pass

            return None
        except Exception as e:
            # Emit error event
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_FAILED,
                        level=EventLevel.ERROR,
                        data={
                            'component': 'credential_manager',
                            'operation': 'user_credential_retrieval',
                            'credential_id': credential_id,
                            'user_id': user_id,
                            'source': 'user_database',
                            'error': str(e),
                            'error_type': type(e).__name__
                        },
                        description=f'User credential retrieval failed: {str(e)}',
                        parent_event_id=event_id
                    )
            except Exception:
                pass
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
        # Emit system credential retrieval start event
        try:
            observability_manager = ObservabilityManager.get_instance()
            event_id = observability_manager.event_logger.emit_event(
                event_type=EventType.REQUEST_PROCESSING,
                level=EventLevel.DEBUG,
                data={
                    'component': 'credential_manager',
                    'operation': 'system_credential_retrieval',
                    'credential_id': credential_id,
                    'source': 'system_database'
                },
                description=f'Retrieving system-wide credential {credential_id}'
            )
        except Exception:
            observability_manager = None
            event_id = None

        # This is a placeholder that should be replaced with actual database access code
        # In a real implementation, this would query the credentials table
        try:
            # Example of how this might work with a real database
            # query = "SELECT value FROM credentials WHERE credential_id = ? AND user_id IS NULL"
            # result = database.execute_query(query, (credential_id,))
            # return result[0] if result else None

            # Emit completion event for placeholder implementation
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_COMPLETED,
                        level=EventLevel.DEBUG,
                        data={
                            'component': 'credential_manager',
                            'operation': 'system_credential_retrieval',
                            'credential_id': credential_id,
                            'source': 'system_database',
                            'credential_found': False,
                            'implementation_status': 'placeholder'
                        },
                        description=('System credential retrieval completed '
                                     '(placeholder implementation)'),
                        parent_event_id=event_id
                    )
            except Exception:
                pass

            return None
        except Exception as e:
            # Emit error event
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_FAILED,
                        level=EventLevel.ERROR,
                        data={
                            'component': 'credential_manager',
                            'operation': 'system_credential_retrieval',
                            'credential_id': credential_id,
                            'source': 'system_database',
                            'error': str(e),
                            'error_type': type(e).__name__
                        },
                        description=f'System credential retrieval failed: {str(e)}',
                        parent_event_id=event_id
                    )
            except Exception:
                pass
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
        # Emit MCP credential resolution start event
        try:
            observability_manager = ObservabilityManager.get_instance()
            event_id = observability_manager.event_logger.emit_event(
                event_type=EventType.MCP_CONNECTION_ESTABLISHED,
                level=EventLevel.INFO,
                data={
                    'component': 'credential_manager',
                    'operation': 'mcp_credential_resolution',
                    'user_id': user_id,
                    'has_auth_config': 'auth' in mcp_config,
                    'config_keys': list(mcp_config.keys())
                },
                description='Starting MCP credential resolution'
            )
        except Exception:
            observability_manager = None
            event_id = None

        try:
            auth_config = mcp_config.get("auth")
            if not auth_config:
                # Emit completion event for no auth config
                try:
                    if observability_manager:
                        observability_manager.event_logger.emit_event(
                            event_type=EventType.REQUEST_COMPLETED,
                            level=EventLevel.DEBUG,
                            data={
                                'component': 'credential_manager',
                                'operation': 'mcp_credential_resolution',
                                'user_id': user_id,
                                'credentials_resolved': 0,
                                'auth_config_present': False
                            },
                            description=('MCP credential resolution completed: '
                                         'no auth config'),
                            parent_event_id=event_id
                        )
                except Exception:
                    pass
                return mcp_config

            # Get auth configuration
            credentials_config = auth_config
            result_args = mcp_config.get("args", {}).copy()
            credentials_resolved = 0
            credentials_failed = []

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
                        credentials_failed.append(cred_id)
                        # Emit error event for missing required credential
                        try:
                            if observability_manager:
                                observability_manager.event_logger.emit_event(
                                    event_type=EventType.REQUEST_FAILED,
                                    level=EventLevel.ERROR,
                                    data={
                                        'component': 'credential_manager',
                                        'operation': 'mcp_credential_resolution',
                                        'credential_id': cred_id,
                                        'user_id': user_id,
                                        'error': 'required_credential_not_found',
                                        'param_name': param_name,
                                        'required': required
                                    },
                                    description=(f'Required MCP credential not found: '
                                                 f'{cred_id}'),
                                    parent_event_id=event_id
                                )
                        except Exception:
                            pass
                        raise ValueError(f"Required credential not found: {cred_id}")

                    # Add credential to args if found
                    if value is not None:
                        result_args[param_name] = value
                        credentials_resolved += 1

            # Update args in the result config
            result = mcp_config.copy()
            result["args"] = result_args

            # Emit completion event
            try:
                if observability_manager:
                    completion_desc = (f'MCP credential resolution completed: '
                                       f'{credentials_resolved} credentials resolved')
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_COMPLETED,
                        level=EventLevel.INFO,
                        data={
                            'component': 'credential_manager',
                            'operation': 'mcp_credential_resolution',
                            'user_id': user_id,
                            'credentials_resolved': credentials_resolved,
                            'credentials_failed': credentials_failed,
                            'auth_config_present': True,
                            'result_args_count': len(result_args)
                        },
                        description=completion_desc,
                        parent_event_id=event_id
                    )
            except Exception:
                pass

            return result

        except Exception as e:
            # Emit error event
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_FAILED,
                        level=EventLevel.ERROR,
                        data={
                            'component': 'credential_manager',
                            'operation': 'mcp_credential_resolution',
                            'user_id': user_id,
                            'error': str(e),
                            'error_type': type(e).__name__
                        },
                        description=f'MCP credential resolution failed: {str(e)}',
                        parent_event_id=event_id
                    )
            except Exception:
                pass
            raise

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
        # Emit batch MCP credential resolution start event
        try:
            observability_manager = ObservabilityManager.get_instance()
            batch_desc = (f'Starting batch MCP credential resolution for '
                          f'{len(mcp_configs)} configurations')
            event_id = observability_manager.event_logger.emit_event(
                event_type=EventType.MCP_CONNECTION_ESTABLISHED,
                level=EventLevel.INFO,
                data={
                    'component': 'credential_manager',
                    'operation': 'batch_mcp_credential_resolution',
                    'user_id': user_id,
                    'config_count': len(mcp_configs),
                    'batch_size': len(mcp_configs)
                },
                description=batch_desc
            )
        except Exception:
            observability_manager = None
            event_id = None

        try:
            resolved_configs = []
            successful_resolutions = 0
            failed_resolutions = 0

            for i, mcp_config in enumerate(mcp_configs):
                try:
                    resolved_config = self.resolve_mcp_credentials(mcp_config, user_id)
                    resolved_configs.append(resolved_config)
                    successful_resolutions += 1
                except Exception as e:
                    # Log individual failure but continue with batch
                    try:
                        if observability_manager:
                            failure_desc = (f'Individual MCP config resolution failed '
                                            f'at index {i}: {str(e)}')
                            observability_manager.event_logger.emit_event(
                                event_type=EventType.REQUEST_FAILED,
                                level=EventLevel.WARNING,
                                data={
                                    'component': 'credential_manager',
                                    'operation': 'batch_mcp_credential_resolution',
                                    'config_index': i,
                                    'user_id': user_id,
                                    'error': str(e),
                                    'error_type': type(e).__name__
                                },
                                description=failure_desc,
                                parent_event_id=event_id
                            )
                    except Exception:
                        pass
                    failed_resolutions += 1
                    # Re-raise the exception to maintain original behavior
                    raise

            # Emit completion event
            try:
                if observability_manager:
                    completion_desc = (f'Batch MCP credential resolution completed: '
                                       f'{successful_resolutions}/{len(mcp_configs)} '
                                       f'successful')
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_COMPLETED,
                        level=EventLevel.INFO,
                        data={
                            'component': 'credential_manager',
                            'operation': 'batch_mcp_credential_resolution',
                            'user_id': user_id,
                            'config_count': len(mcp_configs),
                            'successful_resolutions': successful_resolutions,
                            'failed_resolutions': failed_resolutions,
                            'total_processed': successful_resolutions + failed_resolutions
                        },
                        description=completion_desc,
                        parent_event_id=event_id
                    )
            except Exception:
                pass

            return resolved_configs

        except Exception as e:
            # Emit error event for batch failure
            try:
                if observability_manager:
                    observability_manager.event_logger.emit_event(
                        event_type=EventType.REQUEST_FAILED,
                        level=EventLevel.ERROR,
                        data={
                            'component': 'credential_manager',
                            'operation': 'batch_mcp_credential_resolution',
                            'user_id': user_id,
                            'config_count': len(mcp_configs),
                            'error': str(e),
                            'error_type': type(e).__name__
                        },
                        description=f'Batch MCP credential resolution failed: {str(e)}',
                        parent_event_id=event_id
                    )
            except Exception:
                pass
            raise
