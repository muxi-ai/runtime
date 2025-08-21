"""
Credential repository for secure storage and retrieval of user credentials.

This module implements the basic storage layer for user credentials, using
the existing credentials table in the database. Encryption is handled separately
in task #35 to maintain clean separation of concerns.
"""

from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class CredentialRepository:
    """
    Repository for managing user credentials in the database.

    This implementation provides basic CRUD operations for credential storage
    without encryption. The encryption layer will be added in task #35.

    The repository ensures user isolation - each user can only access their
    own credentials.
    """

    def __init__(self, db_connection):
        """
        Initialize the credential repository.

        Args:
            db_connection: Database connection object (asyncpg or similar)
        """
        self.db = db_connection
        logger.info("CredentialRepository initialized")

    async def store(self, user_id: str, service: str, credential_data: dict) -> None:
        """
        Store or update a credential for a user and service.

        Uses UPSERT logic - updates if exists, inserts if new.

        Args:
            user_id: User identifier (normalized to string)
            service: Service name (e.g., 'github', 'openai')
            credential_data: Credential data dictionary (stored as JSONB)

        Note:
            Currently stores credentials in plaintext. Encryption will be
            added in task #35.
        """
        try:
            # Convert user_id to appropriate format for database
            # The table expects int4 for user_id, but we handle string conversion
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            await self.db.execute(
                """
                INSERT INTO credentials (user_id, service, credentials, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, service) DO UPDATE SET
                    credentials = EXCLUDED.credentials,
                    updated_at = NOW()
                """,
                user_id_int,
                service,
                json.dumps(credential_data),  # Store as JSON string for JSONB column
            )
            logger.info(f"Stored credential for user={user_id}, service={service}")

        except Exception as e:
            logger.error(f"Failed to store credential: {e}")
            raise

    async def get(self, user_id: str, service: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a credential for a user and service.

        Args:
            user_id: User identifier
            service: Service name

        Returns:
            Credential data dictionary if found, None otherwise
        """
        try:
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            result = await self.db.fetchrow(
                """
                SELECT credentials, updated_at
                FROM credentials
                WHERE user_id = $1 AND service = $2
                """,
                user_id_int,
                service,
            )

            if result:
                # Parse JSONB data
                credentials = result["credentials"]
                if isinstance(credentials, str):
                    credentials = json.loads(credentials)

                logger.info(f"Retrieved credential for user={user_id}, service={service}")
                return credentials

            logger.debug(f"No credential found for user={user_id}, service={service}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve credential: {e}")
            raise

    async def list_for_user(self, user_id: str) -> List[str]:
        """
        List all service names that have stored credentials for a user.

        Args:
            user_id: User identifier

        Returns:
            List of service names (never returns actual credentials)
        """
        try:
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            results = await self.db.fetch(
                """
                SELECT service, updated_at
                FROM credentials
                WHERE user_id = $1
                ORDER BY service
                """,
                user_id_int,
            )

            services = [row["service"] for row in results]
            logger.info(f"Listed {len(services)} services for user={user_id}")
            return services

        except Exception as e:
            logger.error(f"Failed to list credentials: {e}")
            raise

    async def remove(self, user_id: str, service: str) -> bool:
        """
        Remove a credential for a user and service.

        Args:
            user_id: User identifier
            service: Service name

        Returns:
            True if credential was removed, False if it didn't exist
        """
        try:
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            result = await self.db.execute(
                """
                DELETE FROM credentials
                WHERE user_id = $1 AND service = $2
                """,
                user_id_int,
                service,
            )

            # Check if any rows were affected
            deleted = result.split()[-1] != "0" if isinstance(result, str) else False

            if deleted:
                logger.info(f"Removed credential for user={user_id}, service={service}")
            else:
                logger.debug(f"No credential to remove for user={user_id}, service={service}")

            return deleted

        except Exception as e:
            logger.error(f"Failed to remove credential: {e}")
            raise

    async def update_last_used(self, user_id: str, service: str) -> None:
        """
        Update the last used timestamp for a credential.

        Useful for tracking credential usage and implementing TTL policies.

        Args:
            user_id: User identifier
            service: Service name
        """
        try:
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            await self.db.execute(
                """
                UPDATE credentials
                SET updated_at = NOW()
                WHERE user_id = $1 AND service = $2
                """,
                user_id_int,
                service,
            )

            logger.debug(f"Updated last used for user={user_id}, service={service}")

        except Exception as e:
            logger.error(f"Failed to update last used timestamp: {e}")
            raise

    async def exists(self, user_id: str, service: str) -> bool:
        """
        Check if a credential exists for a user and service.

        Args:
            user_id: User identifier
            service: Service name

        Returns:
            True if credential exists, False otherwise
        """
        try:
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            result = await self.db.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM credentials
                    WHERE user_id = $1 AND service = $2
                )
                """,
                user_id_int,
                service,
            )

            return bool(result)

        except Exception as e:
            logger.error(f"Failed to check credential existence: {e}")
            raise

    async def count_for_user(self, user_id: str) -> int:
        """
        Count the number of stored credentials for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of stored credentials
        """
        try:
            user_id_int = int(user_id) if user_id.isdigit() else hash(user_id) % 2147483647

            count = await self.db.fetchval(
                """
                SELECT COUNT(*)
                FROM credentials
                WHERE user_id = $1
                """,
                user_id_int,
            )

            return int(count) if count else 0

        except Exception as e:
            logger.error(f"Failed to count credentials: {e}")
            raise
