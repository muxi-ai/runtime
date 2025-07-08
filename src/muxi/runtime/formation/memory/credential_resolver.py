"""
Credential Resolution Service for User-Specific Credentials

This service handles runtime resolution of user credentials for MCP servers
and other components that need to access services on behalf of users.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, select, Text
from sqlalchemy.orm import declarative_base
import nanoid
import hashlib

from ...datatypes.json_type import JSONType
from ...datatypes.exceptions import FormationError

Base = declarative_base()


class MissingCredentialError(FormationError):
    """Raised when a required user credential is not found."""

    def __init__(self, service: str, user_id: str):
        self.service = service
        self.user_id = user_id
        super().__init__(
            f"Missing credential for service '{service}' for user '{user_id}'",
            {"service": service, "user_id": user_id, "error_type": "missing_credential"},
        )


class User(Base):
    """SQLAlchemy model for users table that works with both PostgreSQL and SQLite."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(21), nullable=False)  # Legacy column, kept for compatibility
    external_user_id = Column(Text, nullable=False)  # The actual external user ID
    external_user_id_hash = Column(String(64), nullable=False)  # SHA256 hash of external_user_id
    formation_id = Column(String, nullable=False, default="default-formation")
    formation_id_hash = Column(String, nullable=False)

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    formation_id = Column(String, nullable=False, default="default-formation")
    formation_id_hash = Column(String, nullable=False)

    # Add indexes in the database migration

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"<Credential(user_id={self.user_id!r}, service={self.service!r}, formation_id={self.formation_id!r})>"


class CredentialResolver:
    """
    Service for resolving user-specific credentials at runtime.

    This service provides caching and database access for user credentials,
    supporting both PostgreSQL (JSONB) and SQLite (TEXT) storage through
    the JSONType abstraction.
    """

    def __init__(self, async_session_maker, formation_id: str, formation_id_hash: str):
        """
        Initialize the credential resolver.

        Args:
            async_session_maker: Async SQLAlchemy session factory
            formation_id: The formation ID (human-readable)
            formation_id_hash: The hashed formation ID for database queries
        """
        self.async_session_maker = async_session_maker
        self.formation_id = formation_id
        self.formation_id_hash = formation_id_hash
        self._cache = {}  # In-memory cache: {user_id: {service: credentials}}

    def _compute_user_id_hash(self, external_user_id: str) -> str:
        """
        Compute SHA256 hash of external user ID for database lookups.

        Args:
            external_user_id: The external user ID string

        Returns:
            SHA256 hash of the user ID
        """
        # Ensure external_user_id is a string
        if not isinstance(external_user_id, str):
            external_user_id = str(external_user_id)
        return hashlib.sha256(external_user_id.encode("utf-8")).hexdigest()

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
            # Compute user ID hash for lookup
            user_id_hash = self._compute_user_id_hash(user_id)

            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id_hash == user_id_hash,
                    User.formation_id_hash == self.formation_id_hash,
                    Credential.service == service,
                    Credential.formation_id_hash == self.formation_id_hash,
                )
                .limit(1)
            )

            result = await session.execute(stmt)
            credential = result.scalar_one_or_none()

            if credential:
                # Cache the result
                user_cache = self._cache.setdefault(user_id, {})
                user_cache[service] = credential.credentials
                return credential.credentials

            return None

    async def store_credential(
        self, user_id: str, service: str, credentials: Dict[str, Any]
    ) -> None:
        """
        Store user credentials in the database.

        Args:
            user_id: The user ID
            service: The service name (will be normalized to lowercase)
            credentials: The credential data to store
        """
        # Normalize service to lowercase for consistent storage
        service = service.lower()

        async with self.async_session_maker() as session:
            try:
                # First, find or create the user
                user_id_hash = self._compute_user_id_hash(user_id)

                # Look up the user
                user_stmt = select(User).where(
                    User.external_user_id_hash == user_id_hash,
                    User.formation_id_hash == self.formation_id_hash,
                )
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()

                if not user:
                    # Create the user if it doesn't exist
                    user = User(
                        user_id=nanoid.generate(),  # Legacy field
                        external_user_id=user_id,
                        external_user_id_hash=user_id_hash,
                        formation_id=self.formation_id,
                        formation_id_hash=self.formation_id_hash,
                    )
                    session.add(user)
                    await session.flush()  # Flush to get the ID

                # Check if credential already exists for this user
                cred_stmt = select(Credential).where(
                    Credential.user_id == user.id,
                    Credential.service == service,
                    Credential.formation_id_hash == self.formation_id_hash,
                )
                result = await session.execute(cred_stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing credential
                    existing.credentials = credentials
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new credential
                    new_cred = Credential(
                        user_id=user.id,  # Use the integer user ID from users table
                        credential_id=nanoid.generate(),  # Generate unique ID
                        name=service,  # Can be customized later
                        service=service,
                        credentials=credentials,
                        formation_id=self.formation_id,
                        formation_id_hash=self.formation_id_hash,
                    )
                    session.add(new_cred)

                await session.commit()

                # Clear cache for this user/service
                if user_id in self._cache:
                    self._cache[user_id].pop(service, None)

            except Exception as e:
                await session.rollback()
                raise FormationError(
                    f"Failed to store credential for service '{service}': {str(e)}"
                ) from e

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
            # Compute user ID hash for lookup
            user_id_hash = self._compute_user_id_hash(user_id)

            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id_hash == user_id_hash,
                    User.formation_id_hash == self.formation_id_hash,
                    Credential.service == service,
                    Credential.formation_id_hash == self.formation_id_hash,
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

    async def list_credentials(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """
        List all credentials for a user.

        Args:
            user_id: The user ID

        Returns:
            Dictionary mapping service names to credentials
        """
        async with self.async_session_maker() as session:
            # Compute user ID hash for lookup
            user_id_hash = self._compute_user_id_hash(user_id)

            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id_hash == user_id_hash,
                    User.formation_id_hash == self.formation_id_hash,
                    Credential.formation_id_hash == self.formation_id_hash,
                )
            )
            result = await session.execute(stmt)
            credentials = result.scalars().all()

            return {cred.service: cred.credentials for cred in credentials}
