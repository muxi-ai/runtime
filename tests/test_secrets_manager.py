"""
Tests for the SecretsManager - Formation-level secrets management.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from runtime.muxi.runtime.secrets import SecretsManager


class TestSecretsManager:
    """Test suite for SecretsManager functionality."""

    @pytest.fixture
    async def temp_formation_dir(self):
        """Create a temporary formation directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    async def secrets_manager(self, temp_formation_dir):
        """Create a SecretsManager instance for testing."""
        manager = SecretsManager(temp_formation_dir)
        await manager.initialize_encryption()
        return manager

    @pytest.mark.asyncio
    async def test_initialization(self, temp_formation_dir):
        """Test secrets manager initialization."""
        manager = SecretsManager(temp_formation_dir)

        # Before initialization
        assert manager._fernet is None

        # After initialization
        await manager.initialize_encryption()
        assert manager._fernet is not None
        assert (temp_formation_dir / ".key").exists()

    def test_secret_name_normalization(self):
        """Test secret name normalization rules."""
        manager = SecretsManager("/tmp/test")

        # Test various input formats
        test_cases = [
            ("openai-api-key", "OPENAI_API_KEY"),
            ("database_url", "DATABASE_URL"),
            ("MySecret123", "MYSECRET123"),
        ]

        for input_name, expected in test_cases:
            result = manager._normalize_secret_name(input_name)
            assert result == expected, f"Failed for input '{input_name}'"

    @pytest.mark.asyncio
    async def test_secret_storage_and_retrieval(self, secrets_manager):
        """Test basic secret storage and retrieval."""
        manager = secrets_manager

        # Store a secret
        await manager.store_secret("api_key", "sk-1234567890abcdef")

        # Retrieve and verify
        retrieved_value = await manager.get_secret("api_key")
        assert retrieved_value == "sk-1234567890abcdef"

    @pytest.mark.asyncio
    async def test_full_string_interpolation(self, secrets_manager):
        """Test full string replacement with secrets."""
        manager = secrets_manager

        # Store test secret
        await manager.store_secret("api_key", "sk-1234567890")

        # Test full replacement
        result = await manager.interpolate_secrets("${{ secrets.API_KEY }}")
        assert result == "sk-1234567890"

    @pytest.mark.asyncio
    async def test_partial_string_interpolation(self, secrets_manager):
        """Test partial string interpolation within larger strings."""
        manager = secrets_manager

        # Store test secret
        await manager.store_secret("db_password", "secret123")

        # Test partial interpolation
        template = "postgres://user:${{ secrets.DB_PASSWORD }}@localhost:5432/db"
        result = await manager.interpolate_secrets(template)
        expected = "postgres://user:secret123@localhost:5432/db"
        assert result == expected

    @pytest.mark.asyncio
    async def test_missing_secret_error(self, secrets_manager):
        """Test error handling for missing secrets."""
        manager = secrets_manager

        # Try to interpolate non-existent secret
        with pytest.raises(ValueError, match="Secret 'NON_EXISTENT' not found"):
            await manager.interpolate_secrets("${{ secrets.NON_EXISTENT }}")


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
