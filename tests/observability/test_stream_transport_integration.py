"""
Unit tests for StreamTransport encryption integration.

Tests that StreamTransport correctly integrates with TokenEncryption
for encrypted ZMQ streams.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.muxi.services.observability.transports.stream import StreamTransport
from src.muxi.services.observability.transports.token_encryption import TokenEncryption


class TestStreamTransportEncryptionIntegration:
    """Test cases for StreamTransport encryption integration."""

    def test_encryption_detection_token_tcp(self):
        """Test that encryption is enabled for token + tcp:// combination."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "test_token_123"}
        }

        transport = StreamTransport(config)

        assert transport._needs_encryption() is True
        assert transport.encryptor is not None
        assert isinstance(transport.encryptor, TokenEncryption)

    def test_encryption_detection_token_tcps(self):
        """Test that encryption is enabled for token + tcps:// combination."""
        config = {
            "destination": "tcps://secure.monitor.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "secure_token"}
        }

        transport = StreamTransport(config)

        assert transport._needs_encryption() is True
        assert transport.encryptor is not None

    def test_no_encryption_without_token(self):
        """Test that encryption is not enabled without token auth."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "bearer", "token": "bearer_token"}
        }

        transport = StreamTransport(config)

        assert transport._needs_encryption() is False
        assert transport.encryptor is None

    def test_no_encryption_for_http(self):
        """Test that encryption is not enabled for HTTP transport."""
        config = {
            "destination": "https://api.example.com/events",
            "protocol": "http",
            "auth": {"type": "token", "token": "test_token"}
        }

        transport = StreamTransport(config)

        assert transport._needs_encryption() is False
        assert transport.encryptor is None

    def test_no_encryption_for_ipc(self):
        """Test that encryption is not enabled for ipc:// (local) connections."""
        config = {
            "destination": "ipc:///tmp/zmq_socket",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "test_token"}
        }

        transport = StreamTransport(config)

        assert transport._needs_encryption() is False
        assert transport.encryptor is None

    def test_missing_token_raises_error(self):
        """Test that missing token for encryption raises ValueError."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token"}  # Missing token value
        }

        with pytest.raises(ValueError, match="Token required for encrypted ZMQ transport"):
            StreamTransport(config)

    def test_trail_preset_uses_token_auth(self):
        """Test that trail transport preset uses token auth type."""
        config = {
            "transport": "trail",
            "token": "trail_token_123"
        }

        transport = StreamTransport(config)

        assert transport.destination == "tcps://trail.muxi.ai/ingest"
        assert transport.protocol == "zmq"
        assert transport.format_type == "msgpack"
        assert transport.auth_config["type"] == "token"
        assert transport.auth_config["token"] == "trail_token_123"
        assert transport.encryptor is not None

    @pytest.mark.asyncio
    async def test_send_zmq_with_encryption(self):
        """Test that ZMQ sending encrypts messages before formatting."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "format": "jsonl",
            "auth": {"type": "token", "token": "test_encryption_token"}
        }

        transport = StreamTransport(config)

        # Mock the formatter and socket
        mock_formatter = MagicMock()
        mock_formatter.format_event.return_value = '{"encrypted":true,"payload":"..."}'
        transport.formatter = mock_formatter

        mock_socket = AsyncMock()
        transport.zmq_socket = mock_socket

        # Test event
        test_event = {"level": "info", "message": "test message"}

        # Send the event
        await transport._send_zmq([test_event])

        # Verify encryption was called
        assert mock_formatter.format_event.called
        formatted_data = mock_formatter.format_event.call_args[0][0]

        # The formatted data should be encrypted structure, not the original event
        assert formatted_data != test_event
        assert "encrypted" in formatted_data
        assert "payload" in formatted_data
        assert formatted_data["encrypted"] is True

        # Verify socket send was called
        mock_socket.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_zmq_without_encryption(self):
        """Test that ZMQ sending works without encryption."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "format": "jsonl"
            # No auth config - no encryption
        }

        transport = StreamTransport(config)

        # Mock the formatter and socket
        mock_formatter = MagicMock()
        mock_formatter.format_event.return_value = '{"level":"info","message":"test message"}'
        transport.formatter = mock_formatter

        mock_socket = AsyncMock()
        transport.zmq_socket = mock_socket

        # Test event
        test_event = {"level": "info", "message": "test message"}

        # Send the event
        await transport._send_zmq([test_event])

        # Verify no encryption - original event passed to formatter
        formatted_data = mock_formatter.format_event.call_args[0][0]
        assert formatted_data == test_event

        # Verify socket send was called
        mock_socket.send.assert_called_once()

    def test_encryption_with_different_formats(self):
        """Test that encryption works with different format types."""
        formats = ["jsonl", "msgpack", "protobuf"]

        for format_type in formats:
            config = {
                "destination": "tcp://monitor.example.com:5555",
                "protocol": "zmq",
                "format": format_type,
                "auth": {"type": "token", "token": f"token_for_{format_type}"}
            }

            transport = StreamTransport(config)

            assert transport.encryptor is not None
            assert transport.format_type == format_type

            # Test encryption functionality
            test_event = {"format": format_type, "data": "test"}
            encrypted_result = transport.encryptor.encrypt_message(test_event)

            assert encrypted_result["encrypted"] is True
            assert "payload" in encrypted_result

    @pytest.mark.asyncio
    async def test_initialize_zmq_with_encryption(self):
        """Test ZMQ initialization with encryption configuration."""
        config = {
            "destination": "tcps://secure.monitor.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "init_test_token"}
        }

        transport = StreamTransport(config)

        with patch('zmq.asyncio.Context') as mock_context_class:
            mock_context = MagicMock()
            mock_context_class.return_value = mock_context

            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket

            result = await transport._initialize_zmq()

            assert result is True
            assert transport.status.name == "HEALTHY"

            # Verify socket configuration
            mock_context.socket.assert_called_once()
            mock_socket.connect.assert_called_with("tcp://secure.monitor.com:5555")

    def test_error_handling_in_encryption(self):
        """Test error handling when encryption fails."""
        config = {
            "destination": "tcp://monitor.example.com:5555",
            "protocol": "zmq",
            "auth": {"type": "token", "token": "error_test_token"}
        }

        transport = StreamTransport(config)

        # Mock encryptor to raise exception
        with patch.object(transport.encryptor, 'encrypt_message', side_effect=Exception("Encryption failed")):
            mock_formatter = MagicMock()
            transport.formatter = mock_formatter
            mock_socket = AsyncMock()
            transport.zmq_socket = mock_socket

            # Test that send_zmq handles encryption errors gracefully
            import asyncio
            result = asyncio.run(transport._send_zmq([{"test": "data"}]))

            assert result is False
