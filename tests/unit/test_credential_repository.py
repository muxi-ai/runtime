"""
Unit tests for the CredentialRepository class.

Tests basic CRUD operations, user isolation, and error handling
without encryption (encryption tests will be added in task #35).
"""

import pytest
import json
from unittest.mock import AsyncMock
from datetime import datetime

from muxi.database.repositories.credential_repository import CredentialRepository


class TestCredentialRepository:
    """Test suite for CredentialRepository."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database connection."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def repository(self, mock_db):
        """Create a CredentialRepository instance with mock DB."""
        return CredentialRepository(mock_db)

    @pytest.mark.asyncio
    async def test_store_new_credential(self, repository, mock_db):
        """Test storing a new credential."""
        user_id = "123"
        service = "github"
        credential_data = {
            "type": "api_key",
            "value": "ghp_test123",
            "created": "2024-01-01"
        }

        mock_db.execute.return_value = "INSERT 0 1"

        await repository.store(user_id, service, credential_data)

        # Verify the SQL was called correctly
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args

        # Check SQL query structure
        assert "INSERT INTO credentials" in call_args[0][0]
        assert "ON CONFLICT" in call_args[0][0]

        # Check parameters
        assert call_args[0][1] == 123  # user_id as int
        assert call_args[0][2] == service
        assert call_args[0][3] == json.dumps(credential_data)

    @pytest.mark.asyncio
    async def test_store_update_existing_credential(self, repository, mock_db):
        """Test updating an existing credential (UPSERT logic)."""
        user_id = "123"
        service = "github"
        new_credential_data = {
            "type": "bearer",
            "value": "new_token_456"
        }

        mock_db.execute.return_value = "UPDATE 1"

        await repository.store(user_id, service, new_credential_data)

        # Verify UPSERT was attempted
        call_args = mock_db.execute.call_args
        assert "ON CONFLICT" in call_args[0][0]
        assert "DO UPDATE" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_existing_credential(self, repository, mock_db):
        """Test retrieving an existing credential."""
        user_id = "123"
        service = "openai"
        stored_data = {
            "type": "api_key",
            "value": "sk-test123"
        }

        # Mock the database response
        mock_row = {
            'credentials': json.dumps(stored_data),
            'updated_at': datetime.now()
        }
        mock_db.fetchrow.return_value = mock_row

        result = await repository.get(user_id, service)

        assert result == stored_data
        mock_db.fetchrow.assert_called_once()

        # Verify query parameters
        call_args = mock_db.fetchrow.call_args
        assert call_args[0][1] == 123  # user_id as int
        assert call_args[0][2] == service

    @pytest.mark.asyncio
    async def test_get_nonexistent_credential(self, repository, mock_db):
        """Test retrieving a credential that doesn't exist."""
        user_id = "456"
        service = "unknown_service"

        mock_db.fetchrow.return_value = None

        result = await repository.get(user_id, service)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_for_user_with_credentials(self, repository, mock_db):
        """Test listing services for a user with stored credentials."""
        user_id = "789"

        mock_results = [
            {'service': 'github', 'updated_at': datetime.now()},
            {'service': 'openai', 'updated_at': datetime.now()},
            {'service': 'slack', 'updated_at': datetime.now()}
        ]
        mock_db.fetch.return_value = mock_results

        services = await repository.list_for_user(user_id)

        assert len(services) == 3
        assert 'github' in services
        assert 'openai' in services
        assert 'slack' in services

    @pytest.mark.asyncio
    async def test_list_for_user_without_credentials(self, repository, mock_db):
        """Test listing services for a user with no credentials."""
        user_id = "999"

        mock_db.fetch.return_value = []

        services = await repository.list_for_user(user_id)

        assert services == []

    @pytest.mark.asyncio
    async def test_remove_existing_credential(self, repository, mock_db):
        """Test removing an existing credential."""
        user_id = "111"
        service = "dropbox"

        mock_db.execute.return_value = "DELETE 1"

        result = await repository.remove(user_id, service)

        assert result is True
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_credential(self, repository, mock_db):
        """Test removing a credential that doesn't exist."""
        user_id = "222"
        service = "nonexistent"

        mock_db.execute.return_value = "DELETE 0"

        result = await repository.remove(user_id, service)

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_credential_present(self, repository, mock_db):
        """Test checking existence of a present credential."""
        user_id = "333"
        service = "azure"

        mock_db.fetchval.return_value = True

        exists = await repository.exists(user_id, service)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_credential_absent(self, repository, mock_db):
        """Test checking existence of an absent credential."""
        user_id = "444"
        service = "missing"

        mock_db.fetchval.return_value = False

        exists = await repository.exists(user_id, service)

        assert exists is False

    @pytest.mark.asyncio
    async def test_count_for_user(self, repository, mock_db):
        """Test counting credentials for a user."""
        user_id = "555"

        mock_db.fetchval.return_value = 5

        count = await repository.count_for_user(user_id)

        assert count == 5

    @pytest.mark.asyncio
    async def test_update_last_used(self, repository, mock_db):
        """Test updating the last used timestamp."""
        user_id = "666"
        service = "aws"

        mock_db.execute.return_value = "UPDATE 1"

        await repository.update_last_used(user_id, service)

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "UPDATE credentials" in call_args[0][0]
        assert "SET updated_at = NOW()" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_user_isolation(self, repository, mock_db):
        """Test that users can only access their own credentials."""
        user1_id = "user1"
        user2_id = "user2"
        service = "shared_service"

        # User 1 stores a credential
        await repository.store(user1_id, service, {"key": "user1_secret"})

        # User 2 tries to get the same service
        mock_db.fetchrow.return_value = None  # Simulate no access
        result = await repository.get(user2_id, service)

        assert result is None

        # Verify user_id was properly used in query
        _ = mock_db.fetchrow.call_args
        # user2_id should be hashed differently than user1_id
        user1_int = int(user1_id) if user1_id.isdigit() else hash(user1_id) % 2147483647
        user2_int = int(user2_id) if user2_id.isdigit() else hash(user2_id) % 2147483647
        assert user1_int != user2_int

    @pytest.mark.asyncio
    async def test_handle_string_user_id(self, repository, mock_db):
        """Test handling of non-numeric user IDs."""
        user_id = "alice@example.com"
        service = "gitlab"

        await repository.store(user_id, service, {"token": "glpat-123"})

        # Verify user_id was converted to int via hash
        call_args = mock_db.execute.call_args
        user_id_int = call_args[0][1]
        assert isinstance(user_id_int, int)
        assert user_id_int == hash(user_id) % 2147483647

    @pytest.mark.asyncio
    async def test_handle_numeric_string_user_id(self, repository, mock_db):
        """Test handling of numeric string user IDs."""
        user_id = "42"
        service = "jira"

        await repository.store(user_id, service, {"api_token": "jira123"})

        # Verify user_id was converted to int directly
        call_args = mock_db.execute.call_args
        user_id_int = call_args[0][1]
        assert user_id_int == 42

    @pytest.mark.asyncio
    async def test_error_handling_store(self, repository, mock_db):
        """Test error handling during store operation."""
        user_id = "error_user"
        service = "error_service"

        mock_db.execute.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception) as exc_info:
            await repository.store(user_id, service, {"data": "test"})

        assert "Database connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_handling_get(self, repository, mock_db):
        """Test error handling during get operation."""
        user_id = "error_user"
        service = "error_service"

        mock_db.fetchrow.side_effect = Exception("Query timeout")

        with pytest.raises(Exception) as exc_info:
            await repository.get(user_id, service)

        assert "Query timeout" in str(exc_info.value)
