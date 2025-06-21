"""
Unit tests for TokenEncryption class.

Tests client-side encryption functionality and key derivation.
"""

import time
from unittest.mock import patch
from src.muxi.runtime.services.observability.transports.token_encryption import TokenEncryption


class TestTokenEncryption:
    """Test cases for TokenEncryption class."""

    def test_token_encryption_message(self):
        """Test basic message encryption functionality."""
        token = "test_token_123"
        encryptor = TokenEncryption(token)

        test_event = {"level": "info", "message": "test event", "timestamp": 1234567890}

        result = encryptor.encrypt_message(test_event)

        # Verify structure
        assert isinstance(result, dict)
        assert result["encrypted"] is True
        assert "payload" in result
        assert isinstance(result["payload"], str)

    def test_format_agnostic_encryption(self):
        """Test that encryption works with various data types."""
        token = "test_token_456"
        encryptor = TokenEncryption(token)

        # Test with different event structures
        events = [
            {"simple": "string"},
            {"number": 42, "float": 3.14},
            {"list": [1, 2, 3], "nested": {"key": "value"}},
            {"unicode": "测试", "emoji": "🚀"},
        ]

        for event in events:
            result = encryptor.encrypt_message(event)
            assert result["encrypted"] is True
            assert isinstance(result["payload"], str)

    def test_message_structure(self):
        """Test that encrypted message has correct internal structure."""
        token = "structure_test_token"
        encryptor = TokenEncryption(token)

        test_event = {"test": "data"}

        with patch('time.time', return_value=1234567890.0):
            result = encryptor.encrypt_message(test_event)

        # The encrypted payload should contain the token, timestamp, and event
        # We can't directly verify since it's encrypted, but we can verify structure
        assert result["encrypted"] is True
        assert isinstance(result["payload"], str)
        assert len(result["payload"]) > 0

    def test_key_derivation(self):
        """Test that same token produces same key derivation."""
        token = "consistent_token"

        encryptor1 = TokenEncryption(token)
        encryptor2 = TokenEncryption(token)

        # Same token should produce same key
        assert encryptor1.key == encryptor2.key

        # Different tokens should produce different keys
        encryptor3 = TokenEncryption("different_token")
        assert encryptor1.key != encryptor3.key

    def test_encryption_determinism(self):
        """Test that encryption includes timestamp for uniqueness."""
        token = "determinism_test"
        encryptor = TokenEncryption(token)

        test_event = {"message": "same data"}

        # Small delay between encryptions to ensure different timestamps
        result1 = encryptor.encrypt_message(test_event)
        time.sleep(0.001)
        result2 = encryptor.encrypt_message(test_event)

        # Results should be different due to timestamp
        assert result1["payload"] != result2["payload"]

    def test_empty_event_data(self):
        """Test encryption with empty event data."""
        token = "empty_test_token"
        encryptor = TokenEncryption(token)

        empty_event = {}
        result = encryptor.encrypt_message(empty_event)

        assert result["encrypted"] is True
        assert isinstance(result["payload"], str)
        assert len(result["payload"]) > 0

    def test_token_types(self):
        """Test encryption with different token formats."""
        tokens = [
            "simple_token",
            "token-with-dashes",
            "token_with_underscores",
            "Token123!@#",
            "very_long_token_" + "x" * 100,
        ]

        test_event = {"test": "data"}

        for token in tokens:
            encryptor = TokenEncryption(token)
            result = encryptor.encrypt_message(test_event)
            assert result["encrypted"] is True
            assert isinstance(result["payload"], str)
