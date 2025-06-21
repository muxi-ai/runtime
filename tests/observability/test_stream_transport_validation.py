"""
Unit tests for StreamTransport configuration validation.

Tests that StreamTransport properly validates configuration and provides
clear error messages for common configuration issues.
"""

import pytest
from src.muxi.runtime.services.observability.transports.stream import StreamTransport
from unittest.mock import patch


class TestStreamTransportConfigurationValidation:
    """Test cases for StreamTransport configuration validation."""

    def test_valid_token_zmq_configuration(self):
        """Test that valid token + ZMQ configuration passes validation."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "valid_token_123"}
        }

        # Should not raise any exceptions
        transport = StreamTransport(config)
        assert transport.encryptor is not None

    def test_missing_destination_raises_error(self):
        """Test that missing destination raises clear error."""
        config = {
            "protocol": "zmq",
            "auth": {"type": "token", "token": "test_token"}
        }

        with pytest.raises(ValueError, match="Destination URL is required"):
            StreamTransport(config)

    def test_empty_destination_raises_error(self):
        """Test that empty destination raises clear error."""
        config = {
            "destination": "",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "test_token"}
        }

        with pytest.raises(ValueError, match="Destination URL is required"):
            StreamTransport(config)

    def test_invalid_zmq_destination_raises_error(self):
        """Test that invalid ZMQ destination format raises error."""
        invalid_destinations = [
            "http://monitor.com:5555",
            "ftp://monitor.com:5555",
            "ws://monitor.com:5555",
            "monitor.com:5555",
            "localhost:5555"
        ]

        for destination in invalid_destinations:
            config = {
                "destination": destination,
                "protocol": "zmq",
                "auth": {"type": "token", "token": "test_token"}
            }

            with pytest.raises(ValueError, match="Invalid ZMQ destination"):
                StreamTransport(config)

    def test_valid_zmq_destinations(self):
        """Test that valid ZMQ destinations are accepted."""
        valid_destinations = [
            "tcp://monitor.com:5555",
            "tcps://secure.monitor.com:5555",
            "ipc:///tmp/zmq_socket",
            "ipcs:///tmp/secure_socket"
        ]

        for destination in valid_destinations:
            config = {
                "destination": destination,
                "protocol": "zmq",
                "auth": ({"type": "token", "token": "test_token"}
                         if destination.startswith(("tcp://", "tcps://")) else {})
            }

            # Should not raise exceptions
            transport = StreamTransport(config)
            assert transport.destination == destination

    def test_missing_token_for_token_auth_raises_error(self):
        """Test that missing token for token auth raises clear error."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token"}  # Missing token field
        }

        with pytest.raises(ValueError, match="Token required for encrypted ZMQ transport"):
            StreamTransport(config)

    def test_empty_token_raises_error(self):
        """Test that empty token raises error."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": ""}
        }

        with pytest.raises(ValueError, match="Token required for encrypted ZMQ transport"):
            StreamTransport(config)

    def test_whitespace_only_token_raises_error(self):
        """Test that whitespace-only token raises error."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "   "}
        }

        with pytest.raises(ValueError, match="Token required for encrypted ZMQ transport"):
            StreamTransport(config)

    def test_non_string_token_raises_error(self):
        """Test that non-string token raises error."""
        invalid_tokens = [123, None, [], {}]

        for token in invalid_tokens:
            config = {
                "destination": "tcp://monitor.example.com:5555",
                "protocol": "zmq",
                "auth": {"type": "token", "token": token}
            }

            with pytest.raises(ValueError, match="Token required for encrypted ZMQ transport"):
                StreamTransport(config)

    def test_bearer_auth_validation(self):
        """Test bearer authentication validation."""
        # Valid bearer auth
        config = {
            "destination": "https://api.example.com/events",
            "protocol": "http",
            "auth": {"type": "bearer", "token": "bearer_token_123"}
        }

        transport = StreamTransport(config)
        assert transport.auth_config["type"] == "bearer"

        # Missing token for bearer auth
        config = {
            "destination": "https://api.example.com/events",
            "protocol": "http",
            "auth": {"type": "bearer"}
        }

        with pytest.raises(ValueError, match="Bearer authentication requires 'token' field"):
            StreamTransport(config)

    def test_api_key_auth_validation(self):
        """Test API key authentication validation."""
        # Valid API key auth
        config = {
            "destination": "https://api.example.com/events",
            "protocol": "http",
            "auth": {"type": "api_key", "api_key": "api_key_123"}
        }

        transport = StreamTransport(config)
        assert transport.auth_config["type"] == "api_key"

        # Missing api_key field
        config = {
            "destination": "https://api.example.com/events",
            "protocol": "http",
            "auth": {"type": "api_key"}
        }

        with pytest.raises(ValueError, match="API key authentication requires 'api_key' field"):
            StreamTransport(config)

    def test_sasl_auth_validation(self):
        """Test SASL authentication validation."""
        # Valid SASL auth
        config = {
            "destination": "kafka://broker1:9092,broker2:9092",
            "protocol": "kafka",
            "auth": {"type": "sasl", "username": "user", "password": "pass"}
        }

        transport = StreamTransport(config)
        assert transport.auth_config["type"] == "sasl"

        # Missing username
        config = {
            "destination": "kafka://broker1:9092",
            "protocol": "kafka",
            "auth": {"type": "sasl", "password": "pass"}
        }

        with pytest.raises(ValueError,
                          match="SASL authentication requires 'username' and 'password' fields"):
            StreamTransport(config)

        # Missing password
        config = {
            "destination": "kafka://broker1:9092",
            "protocol": "kafka",
            "auth": {"type": "sasl", "username": "user"}
        }

        with pytest.raises(ValueError,
                          match="SASL authentication requires 'username' and 'password' fields"):
            StreamTransport(config)

    def test_unsupported_auth_type_raises_error(self):
        """Test that unsupported auth types raise error."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "oauth2", "client_id": "test"}
        }

        with pytest.raises(ValueError, match="Unsupported authentication type 'oauth2'"):
            StreamTransport(config)

    def test_validation_with_trail_preset(self):
        """Test that trail preset validation works correctly."""
        # Valid trail config
        config = {
            "transport": "trail",
            "token": "trail_token_123"
        }

        transport = StreamTransport(config)
        assert transport.destination == "tcps://trail.muxi.ai/ingest"
        assert transport.auth_config["type"] == "token"
        assert transport.encryptor is not None

        # Missing token for trail
        config = {
            "transport": "trail"
        }

        with pytest.raises(ValueError, match="Token required for trail transport"):
            StreamTransport(config)

    def test_no_auth_for_non_encrypted_protocols(self):
        """Test that non-encrypted protocols don't require auth."""
        configs = [
            {
                "destination": "http://api.example.com/events",
                "protocol": "http"
            },
            {
                "destination": "ipc:///tmp/local_socket",
                "protocol": "zmq"
            },
            {
                "destination": "kafka://broker:9092",
                "protocol": "kafka"
            }
        ]

        for config in configs:
            # Should not raise exceptions
            transport = StreamTransport(config)
            assert transport.encryptor is None

    def test_encryption_initialization_error_handling(self):
        """Test error handling during encryption initialization."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "test_token"}
        }

        # Mock TokenEncryption to raise an exception
        with patch('src.muxi.runtime.services.observability.transports.stream.TokenEncryption') as mock_encryption:
            mock_encryption.side_effect = Exception("Encryption setup failed")

            with pytest.raises(ValueError, match="Failed to initialize encryption"):
                StreamTransport(config)

    def test_configuration_validation_with_various_formats(self):
        """Test that configuration validation works with different format types."""
        formats = ["jsonl", "msgpack", "protobuf"]

        for format_type in formats:
            config = {
                "destination": "tcp://monitor.example.com:5555",
                "protocol": "zmq",
                "format": format_type,
                "auth": {"type": "token", "token": f"token_for_{format_type}"}
            }

            transport = StreamTransport(config)
            assert transport.format_type == format_type
            assert transport.encryptor is not None

    def test_clear_error_messages(self):
        """Test that error messages are clear and helpful."""
        # Test destination-specific error message
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token"}  # Missing token
        }

        with pytest.raises(ValueError) as exc_info:
            StreamTransport(config)

        error_message = str(exc_info.value)
        assert "tcp://monitor.example.com:5555" in error_message
        assert "auth.token" in error_message
        assert "configuration" in error_message
