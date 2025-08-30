"""
Integration tests for credential handling modes (redirect and dynamic).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from muxi.formation.overlord.clarification import UnifiedClarificationSystem


@pytest.fixture
def mock_overlord():
    """Create a mock overlord with necessary attributes."""
    overlord = MagicMock()
    overlord.formation_config = {
        "user_credentials": {
            "mode": "redirect",
            "redirect_message": "Please configure credentials outside this chat."
        }
    }
    overlord.llm = None
    overlord.buffer_memory = AsyncMock()
    overlord.mcp_registry = {}
    overlord.mcp_coordinator = MagicMock()
    overlord.mcp_coordinator.servers = {}
    overlord.credential_repository = AsyncMock()
    return overlord


@pytest.fixture
def redirect_system(mock_overlord):
    """Create clarification system in redirect mode."""
    mock_overlord.formation_config["user_credentials"]["mode"] = "redirect"
    return UnifiedClarificationSystem(mock_overlord)


@pytest.fixture
def dynamic_system(mock_overlord):
    """Create clarification system in dynamic mode."""
    mock_overlord.formation_config["user_credentials"]["mode"] = "dynamic"
    system = UnifiedClarificationSystem(mock_overlord)
    system.llm = AsyncMock()  # Add LLM for dynamic mode
    return system


class TestRedirectMode:
    """Test redirect mode behavior."""

    @pytest.mark.asyncio
    async def test_redirect_mode_blocks_all_inline(self, redirect_system):
        """Test that redirect mode blocks all credential requests."""
        auth_types = ["api_key", "basic", "bearer", "oauth", "oauth2", "unknown"]

        for auth_type in auth_types:
            # Mock the auth type detection
            redirect_system._get_service_auth_type = AsyncMock(return_value=auth_type)

            result = await redirect_system.handle_mcp_credential_request(
                service_id="test_service",
                user_id="user123",
                request_id="req456"
            )

            # All auth types should be redirected in redirect mode
            assert result.action == "redirect"
            assert "configure credentials outside" in result.message.lower()
            assert "inline" not in result.message.lower()

    @pytest.mark.asyncio
    async def test_redirect_mode_custom_message(self, mock_overlord):
        """Test redirect mode uses custom message."""
        custom_message = "Use our secure portal for credentials"
        mock_overlord.formation_config["user_credentials"]["redirect_message"] = custom_message

        system = UnifiedClarificationSystem(mock_overlord)
        system._get_service_auth_type = AsyncMock(return_value="api_key")

        result = await system.handle_mcp_credential_request(
            service_id="github",
            user_id="user123",
            request_id="req789"
        )

        assert custom_message in result.message
        assert result.action == "redirect"

    @pytest.mark.asyncio
    async def test_redirect_mode_ignores_accept_inline(self, redirect_system):
        """Test redirect mode ignores accept_inline hints."""
        # Even with accept_inline=True, should redirect
        redirect_system._get_service_auth_type = AsyncMock(return_value="bearer")
        redirect_system._get_service_accept_inline = AsyncMock(return_value=True)

        result = await redirect_system.handle_mcp_credential_request(
            service_id="service_with_hint",
            user_id="user123",
            request_id="req001"
        )

        assert result.action == "redirect"
        assert "configure credentials outside" in result.message.lower()


class TestDynamicMode:
    """Test dynamic mode behavior."""

    @pytest.mark.asyncio
    async def test_dynamic_mode_api_key_accepted(self, dynamic_system):
        """Test API keys are accepted inline in dynamic mode."""
        dynamic_system._get_service_auth_type = AsyncMock(return_value="api_key")
        dynamic_system._create_state = AsyncMock()
        dynamic_system._get_state = AsyncMock(return_value={
            "service_id": "github",
            "auth_type": "api_key",
            "user_id": "user123",
            "max_depth": 1
        })
        dynamic_system._store_state = AsyncMock()

        result = await dynamic_system.handle_mcp_credential_request(
            service_id="github",
            user_id="user123",
            request_id="req123"
        )

        assert result.action == "clarify"
        assert "API key" in result.question or "api key" in result.question.lower()
        assert "securely stored" in result.question.lower()

    @pytest.mark.asyncio
    async def test_dynamic_mode_basic_auth_with_warning(self, dynamic_system):
        """Test basic auth is accepted with security warning."""
        dynamic_system._get_service_auth_type = AsyncMock(return_value="basic")
        dynamic_system._create_state = AsyncMock()
        dynamic_system._get_state = AsyncMock(return_value={
            "service_id": "api_service",
            "auth_type": "basic",
            "user_id": "user123",
            "max_depth": 1
        })
        dynamic_system._store_state = AsyncMock()

        result = await dynamic_system.handle_mcp_credential_request(
            service_id="api_service",
            user_id="user123",
            request_id="req124"
        )

        assert result.action == "clarify"
        # Should have security warning for basic auth
        assert "⚠️" in result.question or "warning" in result.question.lower()
        assert "username" in result.question.lower() or "password" in result.question.lower()

    @pytest.mark.asyncio
    async def test_dynamic_mode_oauth_always_redirects(self, dynamic_system):
        """Test OAuth always redirects even in dynamic mode."""
        for oauth_type in ["oauth", "oauth2", "oauth2_flow"]:
            dynamic_system._get_service_auth_type = AsyncMock(return_value=oauth_type)
            dynamic_system._get_service_accept_inline = AsyncMock(return_value=True)

            result = await dynamic_system.handle_mcp_credential_request(
                service_id="oauth_service",
                user_id="user123",
                request_id="req125"
            )

            assert result.action == "redirect"
            assert "browser" in result.message.lower() or "oauth" in result.message.lower()

    @pytest.mark.asyncio
    async def test_dynamic_mode_bearer_requires_hint(self, dynamic_system):
        """Test bearer tokens require accept_inline hint."""
        dynamic_system._get_service_auth_type = AsyncMock(return_value="bearer")

        # Without accept_inline hint - should redirect
        dynamic_system._get_service_accept_inline = AsyncMock(return_value=False)
        result = await dynamic_system.handle_mcp_credential_request(
            service_id="bearer_service",
            user_id="user123",
            request_id="req126"
        )
        assert result.action == "redirect"

        # With accept_inline hint - should accept
        dynamic_system._get_service_accept_inline = AsyncMock(return_value=True)
        dynamic_system._create_state = AsyncMock()
        dynamic_system._get_state = AsyncMock(return_value={
            "service_id": "bearer_service",
            "auth_type": "bearer",
            "user_id": "user123",
            "max_depth": 1
        })
        dynamic_system._store_state = AsyncMock()

        result = await dynamic_system.handle_mcp_credential_request(
            service_id="bearer_service",
            user_id="user123",
            request_id="req127"
        )
        assert result.action == "clarify"
        assert "bearer token" in result.question.lower() or "token" in result.question.lower()

    @pytest.mark.asyncio
    async def test_dynamic_mode_unknown_auth_redirects(self, dynamic_system):
        """Test unknown auth types redirect for safety."""
        dynamic_system._get_service_auth_type = AsyncMock(return_value="unknown")

        result = await dynamic_system.handle_mcp_credential_request(
            service_id="unknown_service",
            user_id="user123",
            request_id="req128"
        )

        assert result.action == "redirect"
        assert "could not be determined" in result.message.lower() or "unknown" in result.message.lower()


class TestModeConfiguration:
    """Test mode configuration from formation."""

    @pytest.mark.asyncio
    async def test_default_mode_is_redirect(self, mock_overlord):
        """Test default mode is redirect when not specified."""
        mock_overlord.formation_config = {}  # No user_credentials config
        system = UnifiedClarificationSystem(mock_overlord)
        system._get_service_auth_type = AsyncMock(return_value="api_key")

        result = await system.handle_mcp_credential_request(
            service_id="test",
            user_id="user123",
            request_id="req129"
        )

        # Should default to redirect for security
        assert result.action == "redirect"

    @pytest.mark.asyncio
    async def test_invalid_mode_defaults_to_redirect(self, mock_overlord):
        """Test invalid mode defaults to redirect."""
        mock_overlord.formation_config = {
            "user_credentials": {"mode": "invalid_mode"}
        }
        system = UnifiedClarificationSystem(mock_overlord)
        system._get_service_auth_type = AsyncMock(return_value="api_key")

        result = await system.handle_mcp_credential_request(
            service_id="test",
            user_id="user123",
            request_id="req130"
        )

        # Invalid mode should default to redirect
        assert result.action == "redirect"

    def test_mode_validation_in_formation(self, mock_overlord):
        """Test mode validation accepts only valid values."""
        valid_modes = ["redirect", "dynamic"]

        for mode in valid_modes:
            mock_overlord.formation_config = {
                "user_credentials": {"mode": mode}
            }
            system = UnifiedClarificationSystem(mock_overlord)
            # Should initialize without errors
            assert system is not None

    @pytest.mark.asyncio
    async def test_mode_switching_at_runtime(self, mock_overlord):
        """Test mode can be checked at runtime."""
        system = UnifiedClarificationSystem(mock_overlord)
        system._get_service_auth_type = AsyncMock(return_value="api_key")

        # Start with redirect
        mock_overlord.formation_config["user_credentials"]["mode"] = "redirect"
        result = await system.handle_mcp_credential_request(
            service_id="test",
            user_id="user123",
            request_id="req131"
        )
        assert result.action == "redirect"

        # Switch to dynamic (in practice, would require reload)
        mock_overlord.formation_config["user_credentials"]["mode"] = "dynamic"
        system._create_state = AsyncMock()
        system._get_state = AsyncMock(return_value={
            "service_id": "test",
            "auth_type": "api_key",
            "user_id": "user123",
            "max_depth": 1
        })
        system._store_state = AsyncMock()

        result = await system.handle_mcp_credential_request(
            service_id="test",
            user_id="user123",
            request_id="req132"
        )
        assert result.action == "clarify"
