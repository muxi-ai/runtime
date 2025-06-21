"""
Unit tests for zmq_decrypt reference implementation.

Tests full encrypt/decrypt cycle and server-side functionality.
"""

import pytest
from unittest.mock import patch
from src.muxi.runtime.services.observability.transports.token_encryption import TokenEncryption
from src.muxi.runtime.utils.zmq_decrypt import (
    decrypt_zmq_message,
    AuthenticationError,
    DecryptionError
)


class TestZMQDecryptReference:
    """Test cases for ZMQ decryption reference implementation."""

    def test_full_encrypt_decrypt_cycle(self):
        """Test complete encryption and decryption cycle."""
        token = "test_cycle_token"
        encryptor = TokenEncryption(token)

        original_event = {
            "level": "info",
            "message": "test message",
            "source": "test_agent",
            "metadata": {"key": "value"}
        }

        # Encrypt the message
        encrypted_result = encryptor.encrypt_message(original_event)

        # Decrypt the message
        decrypted_event = decrypt_zmq_message(encrypted_result, token)

        # Should recover original event data
        assert decrypted_event == original_event

    def test_invalid_token_rejection(self):
        """Test that invalid tokens are rejected during decryption."""
        encrypt_token = "correct_token"
        decrypt_token = "wrong_token"

        encryptor = TokenEncryption(encrypt_token)
        test_event = {"message": "secret data"}

        encrypted_result = encryptor.encrypt_message(test_event)

        # Should raise AuthenticationError with wrong token
        with pytest.raises(AuthenticationError, match="Invalid token"):
            decrypt_zmq_message(encrypted_result, decrypt_token)

    def test_message_integrity(self):
        """Test detection of tampered messages."""
        token = "integrity_token"
        encryptor = TokenEncryption(token)

        test_event = {"sensitive": "data"}
        encrypted_result = encryptor.encrypt_message(test_event)

        # Tamper with the encrypted payload
        tampered_result = encrypted_result.copy()
        tampered_result["payload"] = tampered_result["payload"][:-5] + "XXXXX"

        # Should raise AuthenticationError (Fernet treats tampering as auth failure)
        with pytest.raises(AuthenticationError, match="Invalid token"):
            decrypt_zmq_message(tampered_result, token)

    def test_plaintext_message_handling(self):
        """Test handling of plaintext messages during migration."""
        plaintext_message = {
            "level": "info",
            "message": "plaintext event",
            "encrypted": False  # or missing
        }

        # Should return the message as-is
        result = decrypt_zmq_message(plaintext_message, "any_token")
        assert result == plaintext_message

        # Test with missing encrypted field
        message_no_encrypted = {"level": "info", "message": "no encrypted field"}
        result = decrypt_zmq_message(message_no_encrypted, "any_token")
        assert result == message_no_encrypted

    def test_various_event_types(self):
        """Test encryption/decryption with various event data types."""
        token = "variety_token"
        encryptor = TokenEncryption(token)

        test_events = [
            {},  # Empty event
            {"simple": "string"},
            {"number": 42, "float": 3.14, "bool": True},
            {"list": [1, 2, 3], "nested": {"deep": {"data": "value"}}},
            {"unicode": "测试数据", "emoji": "🔒🚀"},
            {"none_value": None, "empty_string": ""},
        ]

        for original_event in test_events:
            encrypted_result = encryptor.encrypt_message(original_event)
            decrypted_event = decrypt_zmq_message(encrypted_result, token)
            assert decrypted_event == original_event

    def test_timestamp_preservation(self):
        """Test that timestamp is included but not part of returned event."""
        token = "timestamp_token"
        encryptor = TokenEncryption(token)

        test_event = {"data": "timestamped"}

        with patch('time.time', return_value=1234567890.5):
            encrypted_result = encryptor.encrypt_message(test_event)

        decrypted_event = decrypt_zmq_message(encrypted_result, token)

        # Returned event should not include auth_token or timestamp
        assert "auth_token" not in decrypted_event
        assert "timestamp" not in decrypted_event
        assert decrypted_event == test_event

    def test_malformed_encrypted_data(self):
        """Test handling of malformed encrypted data."""
        token = "malformed_token"

        # Test base64 decode failures - should be DecryptionError
        base64_failures = [
            {"encrypted": True, "payload": "invalid_base64!!!"},
            {"encrypted": True},  # Missing payload
        ]

        for malformed_msg in base64_failures:
            with pytest.raises(DecryptionError):
                decrypt_zmq_message(malformed_msg, token)

        # Test valid base64 but invalid Fernet token - should be AuthenticationError
        fernet_failures = [
            {"encrypted": True, "payload": ""},  # Empty payload (valid base64 but invalid Fernet)
            {"encrypted": True, "payload": "dGVzdA=="},  # Valid base64 but invalid encryption
        ]

        for malformed_msg in fernet_failures:
            with pytest.raises(AuthenticationError):
                decrypt_zmq_message(malformed_msg, token)

    def test_token_consistency(self):
        """Test that encryption/decryption token must match exactly."""
        original_token = "exact_match_token"
        encryptor = TokenEncryption(original_token)

        test_event = {"secure": "data"}
        encrypted_result = encryptor.encrypt_message(test_event)

        # Exact match should work
        decrypted = decrypt_zmq_message(encrypted_result, original_token)
        assert decrypted == test_event

        # Case sensitivity
        with pytest.raises(AuthenticationError):
            decrypt_zmq_message(encrypted_result, original_token.upper())

        # Extra spaces
        with pytest.raises(AuthenticationError):
            decrypt_zmq_message(encrypted_result, f" {original_token} ")
