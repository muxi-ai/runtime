"""
Credential Resolution Service for User-Specific Credentials

This service handles runtime resolution of user credentials for MCP servers
and other components that need to access services on behalf of users.
"""

from typing import Optional, Dict, Any, List, Union
from sqlalchemy import Column, Integer, String, DateTime, select, Text
import nanoid
from cachetools import TTLCache

from ...datatypes.exceptions import FormationError
from ...utils.datetime_utils import utc_now_naive
from ...services import observability
from ...services.db import Base
from ...utils.user_resolution import resolve_user_identifier


class Credential(Base):
    """SQLAlchemy model for user credentials that works with both PostgreSQL and SQLite."""

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)  # Foreign key to users.id
    credential_id = Column(String(21), nullable=False, unique=True)  # CHAR(21) in PostgreSQL
    name = Column(String(255), nullable=False)
    service = Column(String(255), nullable=False)  # Always lowercase
    credentials = Column(Text, nullable=False)  # Stores encrypted JSON as text
    created_at = Column(DateTime, default=lambda: utc_now_naive())
    updated_at = Column(
        DateTime,
        default=lambda: utc_now_naive(),
        onupdate=lambda: utc_now_naive(),
    )

    # Add indexes in the database migration

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"<Credential(user_id={self.user_id!r}, service={self.service!r})>"


class CredentialResolver:
    """
    Service for resolving user-specific credentials at runtime.

    This service provides caching and database access for user credentials,
    supporting both PostgreSQL (JSONB) and SQLite (TEXT) storage through
    the JSONType abstraction.
    """

    def __init__(
        self,
        async_session_maker,
        formation_id: str,
        llm_model: Optional[str] = None,
        db_manager=None,
        cache_ttl: int = 3600,  # 1 hour default
        cache_maxsize: int = 10000,  # 10k users max
    ):
        """
        Initialize the credential resolver.

        Args:
            async_session_maker: Async SQLAlchemy session factory
            formation_id: The formation ID (normalized)
            llm_model: Optional LLM model to use for extraction (e.g., from formation.llm.models.text)
            db_manager: Database manager instance for user resolution
            cache_ttl: Time-to-live for cached credentials in seconds (default: 1 hour)
            cache_maxsize: Maximum number of users in cache (default: 10,000)
        """
        self.async_session_maker = async_session_maker
        self.formation_id = formation_id
        # Bounded TTL cache to prevent unbounded growth
        # Credentials are re-fetched from DB after TTL expires
        self._cache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)
        self.llm_model = llm_model  # Store the LLM model to use
        self.db_manager = db_manager  # Store for user identifier resolution

    async def _resolve_user_id(self, identifier: str) -> int:
        """Resolve external user identifier to internal user ID."""
        internal_user_id, muxi_user_id = await resolve_user_identifier(
            identifier=identifier,
            formation_id=self.formation_id,
            db_manager=self.db_manager,
            kv_cache=None,  # KV cache not yet implemented
        )
        return internal_user_id

    async def resolve(self, user_id: str, service: str) -> Optional[Union[Dict, List[Dict]]]:
        """
        Resolve user credentials for a service.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)

        Returns:
            Dict for a single credential, List[Dict] for multiple credentials,
            or None if not found. When multiple credentials exist, each dict
            contains 'name' and 'credentials' keys. Callers should check for None
            and handle missing credentials appropriately (e.g., by raising
            MissingCredentialError or triggering a clarification flow).
        """
        # Normalize service name to lowercase
        service = service.lower()

        # Check cache first
        if user_id in self._cache and service in self._cache[user_id]:
            return self._cache[user_id][service]

        # Resolve user identifier to internal user ID
        internal_user_id = await self._resolve_user_id(user_id)

        # Query database using internal_user_id
        async with self.async_session_maker() as session:
            stmt = (
                select(Credential)
                .where(
                    Credential.user_id == internal_user_id,
                    Credential.service == service,
                )
            )

            result = await session.execute(stmt)
            credentials = result.scalars().all()

            if credentials:
                import json

                if len(credentials) == 1:
                    # Single credential - return it directly
                    # Deserialize JSON string to dict
                    credential_data = credentials[0].credentials
                    if isinstance(credential_data, str):
                        try:
                            credential_data = json.loads(credential_data)
                        except (json.JSONDecodeError, TypeError) as e:
                            # Log parsing error with context, then fail fast
                            observability.observe(
                                event_type=observability.SystemEvents.EXTENSION_FAILED,
                                level=observability.EventLevel.ERROR,
                                data={
                                    "user_id": user_id,
                                    "service": service,
                                    "credential_name": credentials[0].name,
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                },
                                description=f"Failed to parse credential JSON for {credentials[0].name}: {str(e)}"
                            )
                            raise FormationError(
                                f"Malformed credential JSON for service '{service}' "
                                f"(credential: {credentials[0].name}): {str(e)}"
                            ) from e

                    user_cache = self._cache.setdefault(user_id, {})
                    user_cache[service] = credential_data
                    return credential_data
                else:
                    # Multiple credentials - return them as a list with names
                    credential_list = []
                    for cred in credentials:
                        cred_data = cred.credentials
                        if isinstance(cred_data, str):
                            try:
                                cred_data = json.loads(cred_data)
                            except (json.JSONDecodeError, TypeError) as e:
                                # Log parsing error with context, skip malformed credential
                                observability.observe(
                                    event_type=observability.SystemEvents.EXTENSION_FAILED,
                                    level=observability.EventLevel.ERROR,
                                    data={
                                        "user_id": user_id,
                                        "service": service,
                                        "credential_name": cred.name,
                                        "error": str(e),
                                        "error_type": type(e).__name__,
                                    },
                                    description=f"Failed to parse credential JSON for {cred.name}: {str(e)}"
                                )
                                # Skip this malformed credential, don't include it in the list
                                continue
                        credential_list.append({"name": cred.name, "credentials": cred_data})
                    return credential_list

            return None

    async def store_credential(
        self,
        user_id: str,
        service: str,
        credentials: Dict[str, Any],
        credential_name: Optional[str] = None,
        mcp_service: Optional[Any] = None,
    ) -> str:
        """
        Store user credentials in the database.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)
            credentials: The credential data to store
            credential_name: Optional name for the credential. If None, will attempt smart naming
            mcp_service: Optional MCP service for identity discovery
        """
        # Normalize service to lowercase for consistent storage
        service = service.lower()

        # Determine credential name - use smart naming if not provided
        if credential_name is None:
            # For initial storage, use service name to avoid chicken-egg problem
            # Smart naming requires credentials to be available for the identity tool
            credential_name = service

        # Resolve user identifier to internal user ID
        internal_user_id = await self._resolve_user_id(user_id)

        async with self.async_session_maker() as session:
            try:
                # Token is new, create it
                # Note: Duplicate checking is handled by EncryptedCredentialResolver
                # Serialize credentials to JSON string if it's a dict
                import json
                credentials_str = json.dumps(credentials) if isinstance(credentials, dict) else credentials

                new_cred = Credential(
                    user_id=internal_user_id,  # Use the resolved internal user ID
                    credential_id=nanoid.generate(),  # Generate unique ID
                    name=credential_name,  # Use discovered/provided name
                    service=service,
                    credentials=credentials_str,
                )
                session.add(new_cred)

                await session.commit()

                # Clear cache for this user/service
                if user_id in self._cache:
                    self._cache[user_id].pop(service, None)

                return "created"

            except Exception as e:
                await session.rollback()
                raise FormationError(
                    f"Failed to store credential for service '{service}': {str(e)}"
                ) from e

    async def update_credential_name_with_discovery(
        self,
        user_id: str,
        service: str,
        mcp_service: Optional[Any] = None,
    ) -> Optional[str]:
        """
        Update credential name using identity discovery after credential is stored.

        This should be called AFTER credentials are stored and MCP service is
        initialized with those credentials.

        Args:
            user_id: The user ID
            service: The service name
            mcp_service: MCP service initialized with user credentials

        Returns:
            The updated credential name if successful, None otherwise
        """
        if not mcp_service:
            return None

        # Get the stored credentials
        stored_creds = await self.resolve(user_id, service)
        if not stored_creds:
            return None

        # Discover the name using the initialized MCP service
        smart_name = await self._discover_credential_name(
            service, stored_creds, mcp_service, user_id
        )

        if smart_name and smart_name != service:
            # Log the credential name update
            observability.observe(
                event_type=observability.SystemEvents.SECRET_OPERATION_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "user_id": user_id,
                    "service": service,
                    "old_name": service,
                    "new_name": smart_name,
                    "operation_type": "credential_name_update",
                },
                description=f"Updated credential name from '{service}' to '{smart_name}'",
            )

            # Resolve user identifier to internal user ID
            internal_user_id = await self._resolve_user_id(user_id)

            # Update in database
            async with self.async_session_maker() as session:
                stmt = (
                    select(Credential)
                    .where(
                        Credential.user_id == internal_user_id,
                        Credential.service == service,
                    )
                )
                result = await session.execute(stmt)
                credential = result.scalar_one_or_none()

                if credential:
                    credential.name = smart_name
                    await session.commit()

                    # Clear cache
                    if user_id in self._cache:
                        self._cache[user_id].pop(service, None)

                    return smart_name

        return None

    def clear_cache(self, user_id: str = None) -> None:
        """
        Clear cached credentials.

        Args:
            user_id: If provided, clear only this user's cache. Otherwise clear all.
        """
        if user_id:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()

    async def delete_credential(self, user_id: str, service: str) -> bool:
        """
        Delete a user credential from the database.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)

        Returns:
            True if deleted, False if not found
        """
        # Normalize service to lowercase
        service = service.lower()

        # Resolve user identifier to internal user ID
        internal_user_id = await self._resolve_user_id(user_id)

        async with self.async_session_maker() as session:
            stmt = (
                select(Credential)
                .where(
                    Credential.user_id == internal_user_id,
                    Credential.service == service,
                )
            )
            result = await session.execute(stmt)
            credential = result.scalar_one_or_none()

            if credential:
                await session.delete(credential)
                await session.commit()

                # Clear cache
                if user_id in self._cache:
                    self._cache[user_id].pop(service, None)

                return True

            return False

    async def list_credentials(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all credentials for a user.

        Args:
            user_id: The user ID

        Returns:
            Dictionary mapping service names to lists of credential objects
        """
        # Resolve user identifier to internal user ID
        internal_user_id = await self._resolve_user_id(user_id)

        async with self.async_session_maker() as session:
            stmt = (
                select(Credential)
                .where(
                    Credential.user_id == internal_user_id,
                )
            )
            result = await session.execute(stmt)
            credentials = result.scalars().all()

            # Group credentials by service, preserving all credentials for each service
            service_credentials = {}
            for cred in credentials:
                if cred.service not in service_credentials:
                    service_credentials[cred.service] = []

                # Include credential metadata along with the actual credentials
                service_credentials[cred.service].append(
                    {
                        "id": cred.id,
                        "credential_id": cred.credential_id,
                        "name": cred.name,
                        "credentials": cred.credentials,
                        "created_at": cred.created_at.isoformat() if cred.created_at else None,
                        "updated_at": cred.updated_at.isoformat() if cred.updated_at else None,
                    }
                )

            return service_credentials

    async def _discover_credential_name(
        self,
        service: str,
        credentials: Dict[str, Any],
        mcp_service: Optional[Any],
        user_id: str,
    ) -> str:
        """
        Discover a meaningful name for the credential using LLM-guided identity tools.

        Uses the same approach as agent.py - asks LLM to identify and call appropriate
        identity discovery tools (like get_me, whoami, get_authenticated_user, etc.)

        Args:
            service: The service name (e.g., 'github')
            credentials: The credential data
            mcp_service: MCP service for tool invocation
            user_id: User ID for context

        Returns:
            A meaningful name for the credential or fallback to service name
        """
        # If no MCP service provided, fall back to service name
        if not mcp_service:
            return service

        try:
            # Get the MCP server ID for this service
            server_id = f"{service}-mcp"  # Convention: service-mcp

            # Check if this server exists and has tools
            if server_id not in mcp_service.tool_registry:
                return service

            available_tools = mcp_service.tool_registry[server_id]
            if not available_tools:
                return service

            # Use LLM to intelligently discover and call identity tools
            from ...services.llm import LLM

            # Create a lightweight LLM instance for tool discovery
            # Use the formation's configured model or fall back to a default
            try:
                discovery_llm = LLM(model=self.llm_model)
            except Exception:
                # If LLM creation fails (no API key, etc.), fall back to heuristic approach
                return await self._discover_credential_name_heuristic(
                    service, mcp_service, server_id, user_id
                )

            # Build tool list for LLM
            tool_list = []
            for tool_name, tool_info in available_tools.items():
                description = tool_info.get("description", "")
                tool_list.append(f"- {tool_name}: {description}")

            tools_text = "\n".join(tool_list)

            # Ask LLM to identify the best identity discovery tool
            system_prompt = (
                f"You are helping discover a meaningful name for a {service} credential by calling an identity tool."
                "\n\nPlease identify the BEST tool for discovering the authenticated user's identity/account info "
                "(like get_me, whoami, get_authenticated_user, user_info, auth_test, etc.)."
                "\n\nRespond with ONLY the exact tool name (no explanation, no quotes, no extra text). "
                "\n\nIf no identity tool is available, respond with 'NONE'."
            )

            # Get LLM recommendation
            try:
                response = await discovery_llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Available tools from {server_id}:\n{tools_text}"},
                    ],
                    max_tokens=20,
                    temperature=0,
                )
                recommended_tool = response.strip()
            except Exception:
                # Fall back to heuristic approach
                return await self._discover_credential_name_heuristic(
                    service, mcp_service, server_id, user_id
                )

            # Validate the recommended tool exists
            if recommended_tool == "NONE" or recommended_tool not in available_tools:
                return service

            # Call the recommended identity tool
            result = await mcp_service.invoke_tool(
                server_id=server_id,
                tool_name=recommended_tool,
                parameters={},
                user_id=user_id,
                credential_resolver=self,
            )

            # Extract meaningful name from response
            if result.get("status") == "success":
                name = await self._extract_name_from_identity_response(
                    service, result.get("result", {})
                )
                if name and name != service:
                    return name

        except Exception:
            # If anything fails, fall back to service name
            pass

        return service

    async def _discover_credential_name_heuristic(
        self,
        service: str,
        mcp_service: Any,
        server_id: str,
        user_id: str,
    ) -> str:
        """
        Fallback heuristic approach when LLM is not available.

        Uses common identity tool name patterns to find suitable tools.
        """
        available_tools = mcp_service.tool_registry[server_id]

        # Common identity tool name patterns (ordered by preference)
        identity_patterns = [
            "get_me",
            "whoami",
            "get_authenticated_user",
            "get_current_user",
            "me",
            "user_info",
            "get_user",
            "current_user",
            "auth_test",
            "get_profile",
            "profile",
            "identity",
            "account_info",
        ]

        # Try each pattern to find a matching tool
        for pattern in identity_patterns:
            if pattern in available_tools:
                try:
                    # Call the identity tool
                    result = await mcp_service.invoke_tool(
                        server_id=server_id,
                        tool_name=pattern,
                        parameters={},
                        user_id=user_id,
                        credential_resolver=self,
                    )

                    # Extract meaningful name from response
                    if result.get("status") == "success":
                        name = await self._extract_name_from_identity_response(
                            service, result.get("result", {})
                        )
                        if name and name != service:
                            return name

                except Exception:
                    # Continue to next pattern if this tool fails
                    continue

        # If no identity tools work, fall back to service name
        return service

    async def _extract_name_from_identity_response(
        self, service: str, response: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract a meaningful name from identity tool response using LLM when available.

        Args:
            service: The service name
            response: Response from identity tool

        Returns:
            Extracted name or None
        """
        if not response:
            return None

        # Handle structured response format from MCP tools
        response_text = ""
        if isinstance(response, dict):
            # Look for text content in MCP response structure
            content = response.get("content", [])
            if isinstance(content, list) and content:
                # Get first content item
                first_content = content[0]
                if isinstance(first_content, dict) and first_content.get("type") == "text":
                    response_text = first_content.get("text", "")

        if not response_text:
            # Direct field access fallback
            return await self._extract_name_from_fields(service, response)

        # Try LLM-based extraction first, then fallback to parsing
        try:
            from ...services.llm import LLM

            extraction_llm = LLM(model=self.llm_model)

            system_prompt = """Extract the account's identifier (username/login/etc.) from the provided context.
Look for username, login, account name, or similar unique identifier.
Respond with ONLY the identifier (no explanation, no quotes, no extra text).
If no suitable identifier found, respond with "NONE"."""

            result = await extraction_llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": response_text},
                ],
                max_tokens=50,
                temperature=0,
            )

            extracted_name = result.strip()
            if extracted_name != "NONE" and extracted_name:
                return extracted_name

        except Exception:
            # Fall back to traditional parsing if LLM fails
            pass

        # Fallback to traditional parsing methods
        return await self._parse_identity_text(service, response_text)

    async def _parse_identity_text(self, service: str, text: str) -> Optional[str]:
        """
        Parse identity information from text response.

        Args:
            service: The service name
            text: Text response from identity tool

        Returns:
            Extracted name or None
        """
        if not text:
            return None

        # Service-specific parsing
        if service == "github":
            # Look for GitHub identity patterns
            import json

            try:
                # Try to parse as JSON first
                data = json.loads(text)
                return await self._extract_name_from_fields(service, data)
            except (json.JSONDecodeError, ValueError):
                # Parse text patterns
                patterns = [
                    r'"login":\s*"([^"]+)"',
                    r'"name":\s*"([^"]+)"',
                    r"Username:\s*([^\s\n]+)",
                    r"Login:\s*([^\s\n]+)",
                ]

                for pattern in patterns:
                    import re

                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        name = match.group(1).strip()
                        if name and name != "null":
                            return name

        return None

    async def _extract_name_from_fields(self, service: str, data: Dict[str, Any]) -> Optional[str]:
        """
        Extract name from structured data fields using LLM when available.

        Args:
            service: The service name
            data: Structured data from identity response

        Returns:
            Extracted name or None
        """
        if not isinstance(data, dict):
            return None

        # Try LLM-based extraction first for better results
        try:
            from ...services.llm import LLM

            extraction_llm = LLM(model=self.llm_model)

            data_str = str(data)
            system_prompt = f"""Extract the most meaningful account identifier from {service} user data.
Look for username, login, account name, or similar unique identifier.
Prefer usernames over display names, and unique identifiers over generic ones.
Respond with ONLY the identifier (no explanation, no quotes, no extra text).
If no suitable identifier found, respond with "NONE"."""

            result = await extraction_llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": data_str},
                ],
                max_tokens=50,
                temperature=0,
            )

            extracted_name = result.strip()
            if extracted_name != "NONE" and extracted_name:
                return extracted_name

        except Exception:
            # Fall back to traditional field extraction
            pass

        # Traditional field-based extraction fallback
        # Service-specific field mappings
        if service == "github":
            # GitHub API response fields in order of preference
            name_fields = [
                "login",  # GitHub username (most unique)
                "name",  # Display name
                "email",  # Email as fallback
            ]
        else:
            # Generic fallback fields
            name_fields = [
                "username",
                "login",
                "user",
                "name",
                "display_name",
                "displayName",
                "email",
            ]

        # Try each field in order
        for field in name_fields:
            value = data.get(field)
            if value and isinstance(value, str) and value.strip():
                cleaned = value.strip()
                # Avoid generic/placeholder values
                if cleaned.lower() not in ["null", "none", "", "unknown", "user"]:
                    return cleaned

        return None
