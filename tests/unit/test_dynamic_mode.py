"""
Tests for dynamic mode credential handling.

This module tests the dynamic mode functionality which intelligently accepts
simple credentials inline while redirecting complex authentication flows.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from muxi.formation.overlord.clarification import UnifiedClarificationSystem, ClarificationResult


class TestDynamicMode:
    """Test suite for dynamic mode credential handling."""

    @pytest.fixture
    def mock_overlord(self):
        """Create a mock overlord with dynamic mode configuration."""
        overlord = MagicMock()
        overlord.buffer_memory = None
        overlord.clarification_config = None
        overlord.extraction_model = None
        overlord.formation_config = {
            "user_credentials": {
                "mode": "dynamic",
                "redirect_message": "Please configure credentials externally."
            }
        }

        # Mock MCP registry for service metadata
        overlord.mcp_registry = MagicMock()
        overlord.mcp_coordinator = MagicMock()

        return overlord

    @pytest.fixture
    def clarification_system(self, mock_overlord):
        """Create a UnifiedClarificationSystem instance."""
        return UnifiedClarificationSystem(mock_overlord)

    @pytest.mark.asyncio
    async def test_dynamic_mode_accepts_api_key_inline(self, clarification_system, mock_overlord):
        """Test that dynamic mode accepts API keys inline."""
        # Mock service with API key auth
        mock_overlord.mcp_registry.get.return_value = MagicMock(
            auth={'type': 'api_key', 'accept_inline': False}
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="openai",
            user_id="user123",
            request_id="req456"
        )

        assert result.action == "clarify"
        assert result.mode == "dynamic"
        assert "Please provide the api_key for 'openai'" in result.question
        assert "securely stored" in result.question

    @pytest.mark.asyncio
    async def test_dynamic_mode_accepts_basic_auth_with_warning(self, clarification_system, mock_overlord):
        """Test that dynamic mode accepts basic auth with security warning."""
        # Mock service with basic auth
        mock_overlord.mcp_registry.get.return_value = MagicMock(
            auth={'type': 'basic', 'accept_inline': False}
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="jenkins",
            user_id="user234",
            request_id="req567"
        )

        assert result.action == "clarify"
        assert result.mode == "dynamic"
        assert "⚠️ Security Warning" in result.question
        assert "Basic authentication transmits credentials" in result.question
        assert "username:password" in result.question

    @pytest.mark.asyncio
    async def test_dynamic_mode_accepts_bearer_with_accept_inline_true(self, clarification_system, mock_overlord):
        """Test that dynamic mode accepts bearer tokens when accept_inline is true."""
        # Mock service with bearer auth and accept_inline=true
        mock_overlord.mcp_registry.get.return_value = MagicMock(
            auth={'type': 'bearer', 'accept_inline': True}
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="github",
            user_id="user345",
            request_id="req678"
        )

        assert result.action == "clarify"
        assert result.mode == "dynamic"
        assert "personal access token or bearer token" in result.question

    @pytest.mark.asyncio
    async def test_dynamic_mode_redirects_bearer_without_accept_inline(self, clarification_system, mock_overlord):
        """Test that dynamic mode redirects bearer tokens when accept_inline is false."""
        # Mock service with bearer auth and accept_inline=false
        mock_overlord.mcp_registry.get.return_value = MagicMock(
            auth={'type': 'bearer', 'accept_inline': False}
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="azure",
            user_id="user456",
            request_id="req789"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "Please configure credentials externally" in result.question
        assert "bearer token authentication through external configuration" in result.question

    @pytest.mark.asyncio
    async def test_dynamic_mode_always_redirects_oauth(self, clarification_system, mock_overlord):
        """Test that dynamic mode always redirects OAuth flows."""
        # Test various OAuth types
        oauth_types = ["oauth", "oauth2", "oauth2_flow"]

        for auth_type in oauth_types:
            mock_overlord.mcp_registry.get.return_value = MagicMock(
                auth={'type': auth_type, 'accept_inline': True}  # Even with accept_inline=true
            )

            result = await clarification_system.handle_mcp_credential_request(
                service_id="google",
                user_id="user567",
                request_id=f"req_{auth_type}"
            )

            assert result.action == "message"
            assert result.mode == "redirect"
            assert "OAuth authentication requires browser-based authorization" in result.question

    @pytest.mark.asyncio
    async def test_dynamic_mode_redirects_unknown_auth_type(self, clarification_system, mock_overlord):
        """Test that dynamic mode redirects unknown authentication types."""
        # Mock service with unknown auth type
        mock_overlord.mcp_registry.get.return_value = MagicMock(
            auth={'type': 'custom_auth', 'accept_inline': False}
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="custom",
            user_id="user678",
            request_id="req890"
        )

        assert result.action == "message"
        assert result.mode == "redirect"
        assert "external configuration for security" in result.question

    @pytest.mark.asyncio
    async def test_can_accept_inline_logic(self, clarification_system):
        """Test the can_accept_inline method logic."""
        # API keys are always accepted
        assert clarification_system.can_accept_inline("api_key", False) is True
        assert clarification_system.can_accept_inline("api_key", True) is True

        # Basic auth is always accepted
        assert clarification_system.can_accept_inline("basic", False) is True
        assert clarification_system.can_accept_inline("basic", True) is True

        # Bearer tokens depend on accept_inline
        assert clarification_system.can_accept_inline("bearer", False) is False
        assert clarification_system.can_accept_inline("bearer", True) is True

        # OAuth is never accepted
        assert clarification_system.can_accept_inline("oauth", False) is False
        assert clarification_system.can_accept_inline("oauth", True) is False
        assert clarification_system.can_accept_inline("oauth2", False) is False
        assert clarification_system.can_accept_inline("oauth2", True) is False

        # Unknown types are rejected
        assert clarification_system.can_accept_inline("unknown", False) is False
        assert clarification_system.can_accept_inline("custom", True) is False

    @pytest.mark.asyncio
    async def test_request_inline_credential_prompts(self, clarification_system):
        """Test that request_inline_credential generates appropriate prompts."""
        # API key prompt
        prompt = await clarification_system.request_inline_credential("openai", "api_key", "req123")
        assert "Please provide the api_key for 'openai'" in prompt
        assert "securely stored" in prompt

        # Basic auth prompt with warning
        prompt = await clarification_system.request_inline_credential("jenkins", "basic", "req234")
        assert "⚠️ Security Warning" in prompt
        assert "username:password" in prompt

        # Bearer token prompt
        prompt = await clarification_system.request_inline_credential("github", "bearer", "req345")
        assert "personal access token" in prompt

        # Generic prompt
        prompt = await clarification_system.request_inline_credential("custom", "custom_auth", "req456")
        assert "Please provide the custom_auth for 'custom'" in prompt

    @pytest.mark.asyncio
    async def test_get_redirect_reason(self, clarification_system):
        """Test that _get_redirect_reason provides appropriate explanations."""
        # OAuth explanation
        reason = clarification_system._get_redirect_reason("oauth")
        assert "browser-based authorization flow" in reason

        reason = clarification_system._get_redirect_reason("oauth2")
        assert "browser-based authorization flow" in reason

        # Bearer without accept_inline
        reason = clarification_system._get_redirect_reason("bearer")
        assert "bearer token authentication through external configuration" in reason

        # Unknown auth type
        reason = clarification_system._get_redirect_reason("unknown")
        assert "Authentication type could not be determined" in reason

        # Generic auth type
        reason = clarification_system._get_redirect_reason("custom")
        assert "Custom authentication requires external configuration" in reason

    @pytest.mark.asyncio
    async def test_dynamic_mode_creates_clarification_state(self, clarification_system, mock_overlord):
        """Test that dynamic mode creates proper clarification state for inline collection."""
        # Mock buffer memory
        mock_buffer = AsyncMock()
        clarification_system.buffer_memory = mock_buffer

        # Track state modifications
        state_dict = {}

        async def mock_create_state(request_id, message, mode):
            # Initialize state
            state_dict['created'] = True
            state_dict['request_id'] = request_id
            state_dict['message'] = message
            state_dict['mode'] = mode

        async def mock_get_state(request_id):
            # Return a dict to be modified
            return {"initial": True}

        async def mock_store_state(request_id, state):
            # Store the modified state
            state_dict['stored'] = state

        clarification_system._create_state = mock_create_state
        clarification_system._get_state = mock_get_state
        clarification_system._store_state = mock_store_state

        # Mock service with API key auth
        mock_overlord.mcp_registry.get.return_value = MagicMock(
            auth={'type': 'api_key', 'accept_inline': False}
        )

        result = await clarification_system.handle_mcp_credential_request(
            service_id="openai",
            user_id="user789",
            request_id="req901"
        )

        # Verify clarification state was created
        assert state_dict.get('created') is True
        assert state_dict.get('request_id') == "req901"
        assert "api_key" in state_dict.get('message', '')
        assert state_dict.get('mode') == "credential"

        # Verify state was stored with service info
        stored_state = state_dict.get('stored', {})
        assert stored_state.get('service_id') == "openai"
        assert stored_state.get('auth_type') == "api_key"
        assert stored_state.get('max_depth') == 1

        assert result.action == "clarify"
        assert result.mode == "dynamic"

    @pytest.mark.asyncio
    async def test_dynamic_mode_fallback_to_mcp_coordinator(self, clarification_system, mock_overlord):
        """Test that dynamic mode falls back to MCP coordinator when registry not available."""
        # Remove MCP registry
        mock_overlord.mcp_registry.get.return_value = None

        # Configure MCP coordinator with service config
        mock_overlord.mcp_coordinator.config = MagicMock()
        mock_overlord.mcp_coordinator.config.services = {
            'github': {
                'auth': {
                    'type': 'bearer',
                    'accept_inline': True
                }
            }
        }

        result = await clarification_system.handle_mcp_credential_request(
            service_id="github",
            user_id="user012",
            request_id="req234"
        )

        # Should accept bearer token inline because accept_inline is true
        assert result.action == "clarify"
        assert result.mode == "dynamic"

    @pytest.mark.asyncio
    async def test_dynamic_mode_with_no_service_metadata(self, clarification_system, mock_overlord):
        """Test dynamic mode behavior when no service metadata is available."""
        # No MCP registry
        mock_overlord.mcp_registry.get.return_value = None

        # No MCP coordinator config
        mock_overlord.mcp_coordinator = None

        result = await clarification_system.handle_mcp_credential_request(
            service_id="mystery",
            user_id="user345",
            request_id="req567"
        )

        # Should redirect when auth type is unknown
        assert result.action == "message"
        assert result.mode == "redirect"
        assert "Authentication type could not be determined" in result.question
