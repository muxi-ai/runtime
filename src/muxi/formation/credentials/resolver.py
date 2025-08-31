"""
Credential Resolution Service for User-Specific Credentials

This service handles runtime resolution of user credentials for MCP servers
and other components that need to access services on behalf of users.
"""

from typing import Optional, Dict, Any, List
from sqlalchemy import Column, Integer, String, DateTime, select, Text
from sqlalchemy.orm import declarative_base
import nanoid

from ...datatypes.json_type import JSONType
from ...datatypes.exceptions import FormationError
from ...utils.datetime_utils import utc_now_naive
from ...services import observability

Base = declarative_base()


class User(Base):
    """SQLAlchemy model for users table that works with both PostgreSQL and SQLite."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    public_id = Column(String(21), nullable=False, unique=True)  # Nano ID for external exposure
    external_user_id = Column(Text, nullable=False)  # The actual external user ID
    formation_id = Column(String, nullable=False, default="default-formation")
    created_at = Column(DateTime, default=lambda: utc_now_naive())
    updated_at = Column(
        DateTime,
        default=lambda: utc_now_naive(),
        onupdate=lambda: utc_now_naive(),
    )

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"<User(id={self.id}, external_user_id={self.external_user_id!r}, formation_id={self.formation_id!r})>"


class Credential(Base):
    """SQLAlchemy model for user credentials that works with both PostgreSQL and SQLite."""

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)  # Foreign key to users.id
    credential_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    service = Column(String, nullable=False)  # Always lowercase
    credentials = Column(JSONType, nullable=False, default={})  # Works with both DBs
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

    def __init__(self, async_session_maker, formation_id: str, llm_model: Optional[str] = None):
        """
        Initialize the credential resolver.

        Args:
            async_session_maker: Async SQLAlchemy session factory
            formation_id: The formation ID (normalized)
            llm_model: Optional LLM model to use for extraction (e.g., from formation.llm.models.text)
        """
        self.async_session_maker = async_session_maker
        self.formation_id = formation_id
        self._cache = {}  # In-memory cache: {user_id: {service: credentials}}
        self.llm_model = llm_model  # Store the LLM model to use

    async def resolve(self, user_id: str, service: str) -> Optional[Dict]:
        """
        Resolve user credentials for a service.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)

        Returns:
            The credential data if found, None otherwise.
            Callers should check for None and handle missing credentials
            appropriately (e.g., by raising MissingCredentialError or
            triggering a clarification flow).
        """
        # Normalize service name to lowercase
        service = service.lower()

        # Check cache first
        if user_id in self._cache and service in self._cache[user_id]:
            return self._cache[user_id][service]

        # Query database using async session with proper JOIN
        async with self.async_session_maker() as session:
            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id == user_id,
                    User.formation_id == self.formation_id,
                    Credential.service == service,
                )
            )

            result = await session.execute(stmt)
            credentials = result.scalars().all()

            if credentials:
                if len(credentials) == 1:
                    # Single credential - return it directly
                    credential_data = credentials[0].credentials
                    user_cache = self._cache.setdefault(user_id, {})
                    user_cache[service] = credential_data
                    return credential_data
                else:
                    # Multiple credentials - return them as a list with names
                    credential_list = [
                        {"name": cred.name, "credentials": cred.credentials} for cred in credentials
                    ]
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

        async with self.async_session_maker() as session:
            try:
                # First, find or create the user
                # Look up the user
                user_stmt = select(User).where(
                    User.external_user_id == user_id,
                    User.formation_id == self.formation_id,
                )
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()

                if not user:
                    # Create the user if it doesn't exist
                    user = User(
                        public_id=nanoid.generate(size=21),
                        external_user_id=user_id,
                        formation_id=self.formation_id,
                    )
                    session.add(user)
                    await session.flush()  # Flush to get the ID

                # Token is new, create it
                # Note: Duplicate checking is handled by EncryptedCredentialResolver
                new_cred = Credential(
                    user_id=user.id,  # Use the integer user ID from users table
                    credential_id=nanoid.generate(),  # Generate unique ID
                    name=credential_name,  # Use discovered/provided name
                    service=service,
                    credentials=credentials,
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

            # Update in database
            async with self.async_session_maker() as session:
                stmt = (
                    select(Credential)
                    .join(User, Credential.user_id == User.id)
                    .where(
                        User.external_user_id == user_id,
                        User.formation_id == self.formation_id,
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

        async with self.async_session_maker() as session:
            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id == user_id,
                    User.formation_id == self.formation_id,
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
        async with self.async_session_maker() as session:
            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id == user_id,
                    User.formation_id == self.formation_id,
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
            discovery_prompt = (
                f"You are helping discover a meaningful name for a {service} credential by calling an identity tool."
                f"\n\nAvailable tools from {server_id}:"
                f"\n{tools_text}"
                "\n\nPlease identify the BEST tool for discovering the authenticated user's identity/account info "
                "(like get_me, whoami, get_authenticated_user, user_info, auth_test, etc.)."
                "\n\nRespond with ONLY the exact tool name (no explanation, no quotes, no extra text). "
                "\n\nIf no identity tool is available, respond with 'NONE'."
            )

            # Get LLM recommendation
            try:
                response = await discovery_llm.chat(
                    messages=[{"role": "user", "content": discovery_prompt}],
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

            extraction_prompt = f"""
Extract the account's identifier (username/login/etc.) from the context below.
Look for username, login, account name, or similar unique identifier.
Respond with ONLY the identifier (no explanation, no quotes, no extra text).
If no suitable identifier found, respond with "NONE".

<context>
{response_text}
</context>
"""

            result = await extraction_llm.chat(
                messages=[{"role": "user", "content": extraction_prompt}],
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
            extraction_prompt = f"""
Extract the most meaningful account identifier from this {service} user data.

Data: {data_str}

Look for username, login, account name, or similar unique identifier.
Prefer usernames over display names, and unique identifiers over generic ones.
Respond with ONLY the identifier (no explanation, no quotes, no extra text).
If no suitable identifier found, respond with "NONE".
"""

            result = await extraction_llm.chat(
                messages=[{"role": "user", "content": extraction_prompt}],
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
