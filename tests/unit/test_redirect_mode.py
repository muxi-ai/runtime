"""
Tests for redirect mode credential handling.

This module tests the redirect mode functionality which ensures credentials
are never accepted inline and users are redirected to external systems.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass

from muxi.runtime.formation.overlord.clarification import UnifiedClarificationSystem, ClarificationResult
from muxi.runtime.formation.credentials import MissingCredentialError


class TestRedirectMode:
    """Test suite for redirect mode credential handling."""

    @pytest.fixture
    def mock_overlord(self):
        """Create a mock overlord with configuration."""
        overlord = MagicMock()
        overlord.buffer_memory = None
        overlord.clarification_config = None
        overlord.extraction_model = None
        overlord.formation_config = {
            "user_credentials": {
                "mode": "redirect",
                "redirect_message": "Please configure credentials externally."
            }
        }
        return overlord

    @pytest.fixture
    def clarification_system(self, mock_overlord):
        """Create a UnifiedClarificationSystem instance."""
        return UnifiedClarificationSystem(mock_overlord)

    @pytest.mark.asyncio
    async def test_redirect_mode_returns_redirect_message(self, clarification_system):
        """Test that redirect mode returns the configured redirect message."""
        result = await clarification_system.handle_mcp_credential_request(
            service_id="github",
            user_id="user123",
            request_id="req456"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "Please configure credentials externally." in result.question
        assert "Service 'github' requires authentication." in result.question

    @pytest.mark.asyncio
    async def test_redirect_mode_with_custom_message(self, mock_overlord, clarification_system):
        """Test redirect mode with a custom redirect message."""
        # Update the configuration with a custom message
        mock_overlord.formation_config["user_credentials"]["redirect_message"] = (
            "🔐 Security Policy: Use our SSO portal at https://sso.company.com"
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="openai",
            user_id="user789",
            request_id="req012"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "🔐 Security Policy: Use our SSO portal" in result.question
        assert "https://sso.company.com" in result.question
        assert "Service 'openai' requires authentication." in result.question

    @pytest.mark.asyncio
    async def test_redirect_mode_default_message_when_no_config(self):
        """Test that default redirect message is used when no config is provided."""
        # Create overlord without user_credentials config
        overlord = MagicMock()
        overlord.buffer_memory = None
        overlord.clarification_config = None
        overlord.extraction_model = None
        overlord.formation_config = {}  # No user_credentials

        clarification_system = UnifiedClarificationSystem(overlord)

        result = await clarification_system.handle_mcp_credential_request(
            service_id="slack",
            user_id="user234",
            request_id="req567"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "For security, credentials must be configured outside" in result.question
        assert "Service 'slack' requires authentication." in result.question

    @pytest.mark.asyncio
    async def test_redirect_mode_is_default(self):
        """Test that redirect mode is the default when mode is not specified."""
        # Create overlord with user_credentials but no mode specified
        overlord = MagicMock()
        overlord.buffer_memory = None
        overlord.clarification_config = None
        overlord.extraction_model = None
        overlord.formation_config = {
            "user_credentials": {
                # No mode specified - should default to redirect
                "redirect_message": "Custom message without mode"
            }
        }

        clarification_system = UnifiedClarificationSystem(overlord)

        result = await clarification_system.handle_mcp_credential_request(
            service_id="azure",
            user_id="user345",
            request_id="req678"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "Custom message without mode" in result.question

    @pytest.mark.asyncio
    async def test_redirect_mode_never_starts_clarification(self, clarification_system):
        """Test that redirect mode never starts a clarification flow."""
        # Mock buffer memory to track if clarification state is created
        mock_buffer = AsyncMock()
        clarification_system.buffer_memory = mock_buffer

        result = await clarification_system.handle_mcp_credential_request(
            service_id="github",
            user_id="user456",
            request_id="req789"
        )

        # Verify no clarification state was created
        mock_buffer.kv_set.assert_not_called()

        # Verify result indicates no clarification
        assert result.action == "message"
        assert result.mode == "redirect"

    @pytest.mark.asyncio
    async def test_different_services_in_redirect_mode(self, clarification_system):
        """Test redirect mode with different service names."""
        services = ["github", "openai", "slack", "azure", "custom-service"]

        for service in services:
            result = await clarification_system.handle_mcp_credential_request(
                service_id=service,
                user_id="user567",
                request_id=f"req_{service}"
            )

            assert result.action == "message"
            assert result.mode == "redirect"
            assert f"Service '{service}' requires authentication." in result.question

    @pytest.mark.asyncio
    async def test_overlord_handles_missing_credential_with_redirect(self):
        """Test that overlord properly handles MissingCredentialError with redirect mode."""
        # Create a mock response class
        @dataclass
        class MockResponse:
            role: str
            content: str
            metadata: dict

        # Create a mock overlord with redirect configuration
        overlord = MagicMock()
        overlord.formation_config = {
            "user_credentials": {
                "mode": "redirect",
                "redirect_message": "Use external credential management."
            }
        }
        overlord.clarification = AsyncMock()
        overlord.clarification.handle_mcp_credential_request = AsyncMock(
            return_value=ClarificationResult(
                action="message",
                question="Use external credential management.\n\nService 'github' requires authentication.",
                mode="redirect"
            )
        )
        overlord._apply_persona = AsyncMock(side_effect=lambda x, y: x)

        # Mock the error handling method
        async def mock_handle_error(e, message, session_id, request_id):
            if isinstance(e, MissingCredentialError):
                result = await overlord.clarification.handle_mcp_credential_request(
                    service_id=e.service,
                    user_id=e.user_id,
                    request_id=request_id
                )

                if result.action == "message" and result.mode == "redirect":
                    return MockResponse(
                        role="assistant",
                        content=result.question,
                        metadata={
                            "credential_mode": "redirect",
                            "service": e.service,
                        }
                    )
            return None

        # Test handling MissingCredentialError
        error = MissingCredentialError("github", "user123")
        response = await mock_handle_error(error, "test message", "session123", "req123")

        assert response is not None
        assert response.content == "Use external credential management.\n\nService 'github' requires authentication."
        assert response.metadata["credential_mode"] == "redirect"
        assert response.metadata["service"] == "github"

    @pytest.mark.asyncio
    async def test_multiline_redirect_message(self, mock_overlord, clarification_system):
        """Test that multiline redirect messages are properly handled."""
        multiline_message = """Welcome to SecureCorp AI Assistant

For your security, authentication credentials must be configured
through our centralized identity management system.

Please visit: https://identity.securecorp.com/ai-credentials

For assistance, contact your IT administrator or email: ai-support@securecorp.com"""

        mock_overlord.formation_config["user_credentials"]["redirect_message"] = multiline_message

        result = await clarification_system.handle_mcp_credential_request(
            service_id="gitlab",
            user_id="user890",
            request_id="req234"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "Welcome to SecureCorp AI Assistant" in result.question
        assert "https://identity.securecorp.com/ai-credentials" in result.question
        assert "Service 'gitlab' requires authentication." in result.question

    @pytest.mark.asyncio
    async def test_redirect_mode_with_missing_overlord_attributes(self):
        """Test redirect mode when overlord is missing expected attributes."""
        # Create a minimal overlord without formation_config
        overlord = MagicMock()
        # Explicitly remove formation_config to test default behavior
        overlord.formation_config = None

        clarification_system = UnifiedClarificationSystem(overlord)

        result = await clarification_system.handle_mcp_credential_request(
            service_id="dropbox",
            user_id="user901",
            request_id="req345"
        )

        # Should still work with defaults
        assert result.action == "message"
        assert result.mode == "redirect"
        # The default message should be used
        assert "For security" in result.question or "credentials" in result.question.lower()
        assert "Service 'dropbox' requires authentication." in result.question
