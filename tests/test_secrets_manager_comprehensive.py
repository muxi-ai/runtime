"""
Tests for the SecretsManager - Formation-level secrets management.

Covers:
- Encryption and decryption
- Secret storage and retrieval
- Name normalization
- GitHub Actions-style interpolation
- Whitespace tolerance
- Error handling
"""

import pytest
import asyncio
import tempfile
import shutil
import sys
from pathlib import Path

from runtime.muxi.runtime.secrets import SecretsManager

# Add runtime to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))


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
        assert not manager.secrets_dir.exists()
        assert manager._fernet is None

        # After initialization
        await manager.initialize_encryption()
        assert manager.secrets_dir.exists()
        assert manager._fernet is not None
        assert manager.master_key_path.exists()

    @pytest.mark.asyncio
    async def test_master_key_persistence(self, temp_formation_dir):
        """Test that master key persists between manager instances."""
        # Create first manager and initialize
        manager1 = SecretsManager(temp_formation_dir)
        await manager1.initialize_encryption()

        # Store a secret
        await manager1.store_secret("test_key", "test_value")

        # Create second manager - should reuse existing key
        manager2 = SecretsManager(temp_formation_dir)
        await manager2.initialize_encryption()

        # Should be able to retrieve the secret
        value = await manager2.get_secret("test_key")
        assert value == "test_value"

    def test_secret_name_normalization(self):
        """Test secret name normalization rules."""
        manager = SecretsManager("/tmp/test")

        # Test various input formats
        test_cases = [
            ("openai-api-key", "OPENAI_API_KEY"),
            ("database_url", "DATABASE_URL"),
            ("MySecret123", "MYSECRET123"),
            ("a2a.shared.key", "A2A_SHARED_KEY"),
            ("--test--", "TEST"),
            ("_leading_trailing_", "LEADING_TRAILING"),
            ("multiple___underscores", "MULTIPLE_UNDERSCORES"),
            ("MiXeD-CaSe_Key", "MIXED_CASE_KEY"),
        ]

        for input_name, expected in test_cases:
            result = manager._normalize_secret_name(input_name)
            assert result == expected, f"Failed for input '{input_name}'"

    @pytest.mark.asyncio
    async def test_secret_storage_and_retrieval(self, secrets_manager):
        """Test basic secret storage and retrieval."""
        manager = secrets_manager

        # Store various types of secrets
        test_secrets = {
            "api_key": "sk-1234567890abcdef",
            "database_url": "postgresql://user:pass@localhost:5432/db",
            "number_value": 12345,
            "boolean_value": True,
            "complex_object": {"key": "value", "nested": {"data": "test"}},
        }

        # Store all secrets
        for name, value in test_secrets.items():
            await manager.store_secret(name, value)

        # Retrieve and verify all secrets
        for name, expected_value in test_secrets.items():
            retrieved_value = await manager.get_secret(name)
            assert retrieved_value == expected_value

    @pytest.mark.asyncio
    async def test_case_insensitive_access(self, secrets_manager):
        """Test that secret access is case-insensitive."""
        manager = secrets_manager

        # Store with lowercase
        await manager.store_secret("openai_api_key", "sk-test123")

        # Retrieve with various cases
        test_cases = [
            "OPENAI_API_KEY",
            "openai_api_key",
            "OpenAI_API_Key",
            "openai-api-key",  # Different separator
        ]

        for name_variant in test_cases:
            value = await manager.get_secret(name_variant)
            assert value == "sk-test123", f"Failed for '{name_variant}'"

    @pytest.mark.asyncio
    async def test_secret_overwrite_protection(self, secrets_manager):
        """Test protection against accidental secret overwriting."""
        manager = secrets_manager

        # Store initial secret
        await manager.store_secret("protected_key", "original_value")

        # Attempt to overwrite without permission - should fail
        with pytest.raises(ValueError, match="already exists"):
            await manager.store_secret("protected_key", "new_value")

        # Verify original value unchanged
        value = await manager.get_secret("protected_key")
        assert value == "original_value"

        # Explicit overwrite should work
        await manager.store_secret("protected_key", "new_value", overwrite=True)
        value = await manager.get_secret("protected_key")
        assert value == "new_value"

    @pytest.mark.asyncio
    async def test_secret_deletion(self, secrets_manager):
        """Test secret deletion functionality."""
        manager = secrets_manager

        # Store secrets
        await manager.store_secret("temp_secret", "delete_me")
        await manager.store_secret("keep_secret", "keep_me")

        # Verify both exist
        assert await manager.secret_exists("temp_secret")
        assert await manager.secret_exists("keep_secret")

        # Delete one
        result = await manager.delete_secret("temp_secret")
        assert result is True

        # Verify deletion
        assert not await manager.secret_exists("temp_secret")
        assert await manager.secret_exists("keep_secret")

        # Deleting non-existent secret
        result = await manager.delete_secret("non_existent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_secrets(self, secrets_manager):
        """Test listing all secrets."""
        manager = secrets_manager

        # Empty initially
        secrets = await manager.list_secrets()
        assert len(secrets) == 0

        # Add some secrets
        test_secrets = ["API_KEY", "DATABASE_URL", "SECRET_TOKEN"]
        for secret in test_secrets:
            await manager.store_secret(secret, f"value_{secret}")

        # List should contain all secrets (normalized names)
        secrets = await manager.list_secrets()
        assert len(secrets) == 3
        assert set(secrets) == set(test_secrets)

    @pytest.mark.asyncio
    async def test_full_string_interpolation(self, secrets_manager):
        """Test full string replacement with secrets."""
        manager = secrets_manager

        # Store test secrets
        await manager.store_secret("api_key", "sk-1234567890")

        # Test full replacement with different whitespace patterns
        test_cases = [
            "${{ secrets.API_KEY }}",
            "${{secrets.API_KEY}}",  # No spaces
            "${{ secrets.API_KEY}}",  # Trailing space only
            "${{secrets.API_KEY }}",  # Leading space only
        ]

        for template in test_cases:
            result = await manager.interpolate_secrets(template)
            assert result == "sk-1234567890", f"Failed for template '{template}'"

    @pytest.mark.asyncio
    async def test_partial_string_interpolation(self, secrets_manager):
        """Test partial string interpolation within larger strings."""
        manager = secrets_manager

        # Store test secrets
        await manager.store_secret("db_password", "secret123")
        await manager.store_secret("api_token", "token456")

        # Test partial interpolation
        test_cases = [
            {
                "input": "postgres://user:${{ secrets.DB_PASSWORD }}@localhost:5432/db",
                "expected": "postgres://user:secret123@localhost:5432/db"
            },
            {
                "input": "Bearer ${{ secrets.API_TOKEN }}",
                "expected": "Bearer token456"
            },
            {
                "input": "Key: ${{ secrets.API_TOKEN }}, Password: ${{ secrets.DB_PASSWORD }}",
                "expected": "Key: token456, Password: secret123"
            },
        ]

        for case in test_cases:
            result = await manager.interpolate_secrets(case["input"])
            assert result == case["expected"]

    @pytest.mark.asyncio
    async def test_nested_data_interpolation(self, secrets_manager):
        """Test interpolation in nested data structures."""
        manager = secrets_manager

        # Store test secrets
        await manager.store_secret("openai_key", "sk-openai123")
        await manager.store_secret("database_url", "postgresql://localhost/db")

        # Test nested dictionary
        config = {
            "llm": {
                "provider": "openai",
                "api_key": "${{ secrets.OPENAI_KEY }}"
            },
            "database": {
                "url": "${{ secrets.DATABASE_URL }}",
                "timeout": 30
            },
            "static_value": "no_interpolation"
        }

        result = await manager.interpolate_secrets(config)

        expected = {
            "llm": {
                "provider": "openai",
                "api_key": "sk-openai123"
            },
            "database": {
                "url": "postgresql://localhost/db",
                "timeout": 30
            },
            "static_value": "no_interpolation"
        }

        assert result == expected

    @pytest.mark.asyncio
    async def test_list_interpolation(self, secrets_manager):
        """Test interpolation in lists."""
        manager = secrets_manager

        await manager.store_secret("key1", "value1")
        await manager.store_secret("key2", "value2")

        config = [
            "${{ secrets.KEY1 }}",
            "static_value",
            {"nested": "${{ secrets.KEY2 }}"},
            42
        ]

        result = await manager.interpolate_secrets(config)

        expected = [
            "value1",
            "static_value",
            {"nested": "value2"},
            42
        ]

        assert result == expected

    @pytest.mark.asyncio
    async def test_missing_secret_error(self, secrets_manager):
        """Test error handling for missing secrets."""
        manager = secrets_manager

        # Try to interpolate non-existent secret
        with pytest.raises(ValueError, match="Secret 'NON_EXISTENT' not found"):
            await manager.interpolate_secrets("${{ secrets.NON_EXISTENT }}")

    @pytest.mark.asyncio
    async def test_import_export_secrets(self, secrets_manager):
        """Test bulk import and export functionality."""
        manager = secrets_manager

        # Test secrets to import
        secrets_to_import = {
            "api_key": "sk-test123",
            "database-url": "postgresql://localhost/db",
            "number_value": 42,
            "boolean_value": True
        }

        # Import secrets
        await manager.import_secrets(secrets_to_import)

        # Export and verify
        exported = await manager.export_secrets()

        # Check that all secrets were imported with normalized names
        assert "API_KEY" in exported
        assert "DATABASE_URL" in exported
        assert "NUMBER_VALUE" in exported
        assert "BOOLEAN_VALUE" in exported

        # Verify values
        assert exported["API_KEY"] == "sk-test123"
        assert exported["DATABASE_URL"] == "postgresql://localhost/db"
        assert exported["NUMBER_VALUE"] == 42
        assert exported["BOOLEAN_VALUE"] is True

    @pytest.mark.asyncio
    async def test_clear_all_secrets(self, secrets_manager):
        """Test clearing all secrets."""
        manager = secrets_manager

        # Add some secrets
        await manager.store_secret("key1", "value1")
        await manager.store_secret("key2", "value2")

        # Verify they exist
        assert len(await manager.list_secrets()) == 2

        # Clear all
        await manager.clear_all_secrets()

        # Verify empty
        assert len(await manager.list_secrets()) == 0
        assert await manager.get_secret("key1") is None

    @pytest.mark.asyncio
    async def test_encryption_file_permissions(self, temp_formation_dir):
        """Test that encryption files have secure permissions."""
        manager = SecretsManager(temp_formation_dir)
        await manager.initialize_encryption()

        # Check master key permissions
        key_stat = manager.master_key_path.stat()
        # 0o600 = owner read/write only
        assert oct(key_stat.st_mode)[-3:] == "600"

        # Store a secret and check encrypted file permissions
        await manager.store_secret("test", "value")
        secrets_stat = manager.secrets_file_path.stat()
        assert oct(secrets_stat.st_mode)[-3:] == "600"

    @pytest.mark.asyncio
    async def test_concurrent_access(self, secrets_manager):
        """Test concurrent access to secrets (basic thread safety)."""
        manager = secrets_manager

        # Define concurrent operations
        async def store_operation(name: str, value: str):
            await manager.store_secret(f"concurrent_{name}", value)

        async def read_operation(name: str):
            return await manager.get_secret(f"concurrent_{name}")

        # Run concurrent operations
        store_tasks = [
            store_operation("1", "value1"),
            store_operation("2", "value2"),
            store_operation("3", "value3"),
        ]

        await asyncio.gather(*store_tasks)

        # Verify all were stored
        read_tasks = [
            read_operation("1"),
            read_operation("2"),
            read_operation("3"),
        ]

        results = await asyncio.gather(*read_tasks)
        assert results == ["value1", "value2", "value3"]

    @pytest.mark.asyncio
    async def test_regex_pattern_edge_cases(self, secrets_manager):
        """Test edge cases for the secrets interpolation regex."""
        manager = secrets_manager

        await manager.store_secret("test_key", "secret_value")

        # Test cases that should NOT match
        non_matching_cases = [
            "{{ secrets.TEST_KEY }}",  # Missing $
            "${ secrets.TEST_KEY }",   # Wrong braces
            "${{ secret.TEST_KEY }}",  # Wrong prefix
            "${{ secrets.test-key }}",  # Invalid characters in secret name
            "${{ secrets. }}",          # Empty secret name
        ]

        for case in non_matching_cases:
            result = await manager.interpolate_secrets(case)
            assert result == case, f"Should not interpolate: '{case}'"

        # Test cases that SHOULD match
        matching_cases = [
            "${{ secrets.TEST_KEY }}",
            "${{secrets.TEST_KEY}}",
            "${{ secrets.TEST_KEY}}",
            "${{secrets.TEST_KEY }}",
        ]

        for case in matching_cases:
            result = await manager.interpolate_secrets(case)
            assert result == "secret_value", f"Should interpolate: '{case}'"


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
