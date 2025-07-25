#!/usr/bin/env python3
"""
Test suite for enhanced user ID handling implementation.

Tests the flexible user ID conversion functionality that accepts any external
user ID format and maps it to internal integer IDs for compatibility.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.muxi.overlord import Overlord
from src.muxi.memory.short_term import ShortTermMemory


class TestUserIdEnhancement:
    """Test enhanced user ID handling functionality."""

    @pytest.fixture
    def mock_memory(self):
        """Create mock memory systems for testing."""
        buffer_memory = Mock(spec=ShortTermMemory)
        buffer_memory.add = AsyncMock()
        buffer_memory.search = AsyncMock(return_value=[])

        long_term_memory = Mock()
        long_term_memory.db = Mock()
        long_term_memory.db.cursor = Mock()
        long_term_memory.db.fetchone = Mock()
        long_term_memory.db.commit = Mock()

        return buffer_memory, long_term_memory

    @pytest.fixture
    def overlord(self, mock_memory):
        """Create overlord instance with mock memory for testing."""
        buffer_memory, long_term_memory = mock_memory
        return Overlord(
            buffer_memory=buffer_memory,
            long_term_memory=long_term_memory,
            auto_extract_user_info=False  # Disable for testing
        )

    @pytest.mark.asyncio
    async def test_normalize_external_id_various_formats(self, overlord):
        """Test normalization of different external ID formats."""
        # Test string ID
        assert overlord._normalize_external_id("user123") == "user123"

        # Test integer ID
        assert overlord._normalize_external_id(12345) == "12345"

        # Test float ID
        assert overlord._normalize_external_id(123.45) == "123.45"

        # Test UUID string
        uuid_str = "550e8400-e29b-4d4b-a716-446655440000"
        assert overlord._normalize_external_id(uuid_str) == uuid_str

        # Test email
        email = "user@example.com"
        assert overlord._normalize_external_id(email) == email

        # Test None
        assert overlord._normalize_external_id(None) == "anonymous"

        # Test custom object
        class CustomId:
            def __str__(self):
                return "custom_id_123"

        custom_id = CustomId()
        assert overlord._normalize_external_id(custom_id) == "custom_id_123"

    @pytest.mark.asyncio
    async def test_enhance_existing_user_id_conversion_anonymous(self, overlord):
        """Test handling of anonymous users (user_id = 0 or None)."""
        # Test None user_id
        result = await overlord._enhance_existing_user_id_conversion(None)
        assert result == 0

        # Test 0 user_id
        result = await overlord._enhance_existing_user_id_conversion(0)
        assert result == 0

    @pytest.mark.asyncio
    async def test_enhance_existing_user_id_conversion_with_cache(self, overlord):
        """Test caching functionality for user ID conversion."""
        user_id = "test_user_123"

        # Mock the _find_or_create_user method instead of _resolve_flexible_user_id
        # This allows the cache logic to work properly
        with patch.object(overlord, '_find_or_create_user') as mock_find:
            mock_find.return_value = {
                'internal_id': 12345,
                'isolation_key': "user_12345_abcd1234"
            }

            # First call should hit the database
            result1 = await overlord._enhance_existing_user_id_conversion(user_id)
            assert result1 == 12345
            assert mock_find.call_count == 1

            # Second call should use cache (database not called again)
            result2 = await overlord._enhance_existing_user_id_conversion(user_id)
            assert result2 == 12345
            assert mock_find.call_count == 1  # Should not increase

    @pytest.mark.asyncio
    async def test_find_or_create_user_existing_user(self, overlord):
        """Test finding an existing user in the database."""
        # Mock database connection
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (123, "test_user", "hash123")

        overlord.long_term_memory.db.cursor.return_value = mock_cursor

        result = await overlord._find_or_create_user("test_user", "hash123")

        assert result['internal_id'] == 123
        assert "user_123_hash123" in result['isolation_key']

        # Verify database query was called
        mock_cursor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_or_create_user_new_user(self, overlord):
        """Test creating a new user in the database."""
        # Mock database connection for user not found, then create
        mock_cursor = Mock()
        mock_cursor.fetchone.side_effect = [None, (456,)]  # Not found, then new ID

        overlord.long_term_memory.db.cursor.return_value = mock_cursor

        with patch('src.muxi.utils.id_generator.generate_nanoid') as mock_nanoid:
            mock_nanoid.return_value = "test_nano_id"

            result = await overlord._find_or_create_user("new_user", "newhash")

            assert result['internal_id'] == 456
            assert "user_456_newhash" in result['isolation_key']

            # Verify insert query was called
            assert mock_cursor.execute.call_count == 2  # SELECT then INSERT

    @pytest.mark.asyncio
    async def test_find_or_create_user_fallback_on_db_error(self, overlord):
        """Test fallback behavior when database operations fail."""
        # Mock database connection to raise an exception
        overlord.long_term_memory.db.cursor.side_effect = Exception("DB Error")

        result = await overlord._find_or_create_user("test_user", "hash123")

        # Should return synthetic ID
        assert isinstance(result['internal_id'], int)
        assert result['internal_id'] > 0
        assert "user_" in result['isolation_key']
        assert "hash123" in result['isolation_key']

    @pytest.mark.asyncio
    async def test_process_sync_chat_enhanced_conversion(self, overlord):
        """Test enhanced user ID conversion in _process_sync_chat method."""
        # Mock agent and methods
        mock_agent = Mock()
        mock_agent.process_message = AsyncMock(return_value=Mock(content="Test response"))

        overlord.agents["test_agent"] = mock_agent
        overlord.get_agent = Mock(return_value=mock_agent)
        overlord.select_agent_for_message = AsyncMock(return_value="test_agent")

        # Mock the enhanced conversion method
        with patch.object(overlord, '_enhance_existing_user_id_conversion') as mock_enhance:
            mock_enhance.return_value = 12345

            # Test with string user_id
            result = await overlord._process_sync_chat("Hello", None, "user_abc_123")

            # Verify enhanced conversion was called
            mock_enhance.assert_called_once_with("user_abc_123")

            # Verify agent was called with converted ID
            mock_agent.process_message.assert_called_once_with("Hello", user_id=12345)

            # Verify result is returned
            assert result is not None

    @pytest.mark.asyncio
    async def test_process_sync_chat_error_handling(self, overlord):
        """Test error handling when enhanced conversion fails (no fallback)."""
        # Mock agent
        mock_agent = Mock()
        mock_agent.process_message = AsyncMock(return_value=Mock(content="Test response"))

        overlord.agents["test_agent"] = mock_agent
        overlord.get_agent = Mock(return_value=mock_agent)
        overlord.select_agent_for_message = AsyncMock(return_value="test_agent")

        # Mock enhanced conversion to fail
        with patch.object(overlord, '_enhance_existing_user_id_conversion') as mock_enhance:
            mock_enhance.side_effect = Exception("Enhanced conversion failed")

            # Test that exception is raised (no fallback)
            with pytest.raises(Exception, match="Enhanced conversion failed"):
                await overlord._process_sync_chat("Hello", None, "123")

    @pytest.mark.asyncio
    async def test_various_external_id_formats_end_to_end(self, overlord):
        """Test end-to-end handling of various external ID formats."""
        test_cases = [
            ("user123", "string ID"),
            (12345, "integer ID"),
            ("user@example.com", "email ID"),
            ("550e8400-e29b-4d4b-a716-446655440000", "UUID"),
            ("org:dept:user123", "hierarchical ID"),
        ]

        for external_id, description in test_cases:
            # Mock database to return consistent results
            with patch.object(overlord, '_find_or_create_user') as mock_find:
                mock_find.return_value = {
                    'internal_id': 999,
                    'isolation_key': "user_999_test"
                }

                result = await overlord._enhance_existing_user_id_conversion(external_id)

                assert result == 999, f"Failed for {description}: {external_id}"

                # Verify normalization was called
                normalized = overlord._normalize_external_id(external_id)
                assert isinstance(normalized, str), f"Normalization failed for {description}"

    @pytest.mark.asyncio
    async def test_user_id_cache_behavior(self, overlord):
        """Test user ID caching works correctly across multiple calls."""
        # Clear any existing cache
        overlord._user_id_cache.clear()

        # Mock database operations
        with patch.object(overlord, '_find_or_create_user') as mock_find:
            mock_find.return_value = {
                'internal_id': 777,
                'isolation_key': "user_777_cached"
            }

            # First call should hit database
            result1 = await overlord._enhance_existing_user_id_conversion("cached_user")
            assert result1 == 777
            assert mock_find.call_count == 1

            # Second call should use cache
            result2 = await overlord._enhance_existing_user_id_conversion("cached_user")
            assert result2 == 777
            assert mock_find.call_count == 1  # Should not increase

            # Different user should hit database again
            result3 = await overlord._enhance_existing_user_id_conversion("different_user")
            assert result3 == 777
            assert mock_find.call_count == 2  # Should increase


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__])
