"""
Unit tests for overlord persona application functionality.

Tests the persona loading, formatting, and application across different response types.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Add the runtime directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from muxi.runtime.formation.overlord.overlord import Overlord  # noqa: E402
from muxi.runtime.datatypes.response import MuxiResponse  # noqa: E402


@pytest.fixture
async def overlord_with_persona():
    """Create an overlord instance with persona configured."""
    # Mock formation config
    formation_config = {
        "llm": {"models": [{"text": "openai/gpt-4o-mini", "api_key": "test-key"}]},
        "overlord": {"persona": "You are a helpful test assistant named TestBot."},
    }

    # Create overlord instance
    overlord = Overlord(
        formation_config=formation_config, configured_services={}, formation_id="test-formation"
    )

    # Mock the capability models
    overlord._capability_models = {"text": {"model": "openai/gpt-4o-mini", "api_key": "test-key"}}

    # Initialize model cache
    overlord._model_cache = {}

    # Load persona
    overlord._load_default_persona()

    return overlord


@pytest.fixture
async def overlord_with_default_persona():
    """Create an overlord instance that loads default persona from file."""
    formation_config = {
        "llm": {"models": [{"text": "openai/gpt-4o-mini", "api_key": "test-key"}]},
        "overlord": {},  # No custom persona
    }

    overlord = Overlord(
        formation_config=formation_config, configured_services={}, formation_id="test-formation"
    )

    overlord._capability_models = {"text": {"model": "openai/gpt-4o-mini", "api_key": "test-key"}}

    overlord._model_cache = {}
    overlord._load_default_persona()

    return overlord


class TestPersonaLoading:
    """Test persona loading functionality."""

    @pytest.mark.asyncio
    async def test_load_custom_persona_from_config(self, overlord_with_persona):
        """Test that custom persona is loaded from formation config."""
        assert overlord_with_persona._default_persona is not None
        assert "TestBot" in overlord_with_persona._default_persona
        assert (
            "IMPORTANT: Always reply in the same language" in overlord_with_persona._default_persona
        )

    @pytest.mark.asyncio
    async def test_load_default_persona_from_file(self, overlord_with_default_persona):
        """Test that default persona is loaded from system_persona.md."""
        assert overlord_with_default_persona._default_persona is not None
        # Check for MUXI content from the file
        assert (
            "MUXI" in overlord_with_default_persona._default_persona
            or "friendly and helpful assistant" in overlord_with_default_persona._default_persona
        )
        assert (
            "IMPORTANT: Always reply in the same language"
            in overlord_with_default_persona._default_persona
        )

    @pytest.mark.asyncio
    async def test_fallback_persona_on_error(self):
        """Test that fallback persona is used when file doesn't exist."""
        formation_config = {
            "llm": {"models": [{"text": "openai/gpt-4o-mini", "api_key": "test-key"}]},
            "overlord": {},
        }

        with patch("os.path.exists", return_value=False):
            overlord = Overlord(
                formation_config=formation_config,
                configured_services={},
                formation_id="test-formation",
            )
            overlord._load_default_persona()

            assert "friendly and helpful assistant" in overlord._default_persona
            assert "IMPORTANT: Always reply in the same language" in overlord._default_persona


class TestPersonaApplication:
    """Test persona application to responses."""

    @pytest.mark.asyncio
    async def test_apply_persona_formats_response(self, overlord_with_persona):
        """Test that _apply_persona formats raw responses."""
        # Mock the LLM response
        mock_llm = AsyncMock()
        mock_result = MagicMock()
        mock_result.generations = [[MagicMock(text="This is a friendly formatted response!")]]
        mock_llm.agenerate.return_value = mock_result

        # Mock create_model to return our mock LLM
        with patch.object(overlord_with_persona, "create_model", return_value=mock_llm):
            formatted = await overlord_with_persona._apply_persona(
                raw_response='{"status": "success", "data": "test"}',
                user_message="Help me with a task",
            )

            assert formatted == "This is a friendly formatted response!"
            mock_llm.agenerate.assert_called_once()

            # Check that the prompt includes persona and user message
            call_args = mock_llm.agenerate.call_args[0][0]
            assert "TestBot" in call_args[0]
            assert "Help me with a task" in call_args[0]
            assert '{"status": "success", "data": "test"}' in call_args[0]

    @pytest.mark.asyncio
    async def test_apply_persona_returns_raw_on_error(self, overlord_with_persona):
        """Test that raw response is returned if formatting fails."""
        # Mock create_model to raise an error
        with patch.object(
            overlord_with_persona, "create_model", side_effect=Exception("LLM Error")
        ):
            raw = '{"error": "something went wrong"}'
            formatted = await overlord_with_persona._apply_persona(
                raw_response=raw, user_message="Test message"
            )

            # Should return raw response on error
            assert formatted == raw

    @pytest.mark.asyncio
    async def test_apply_persona_with_no_text_model(self):
        """Test that raw response is returned when no text model is configured."""
        formation_config = {"llm": {"models": []}, "overlord": {}}  # No models configured

        overlord = Overlord(
            formation_config=formation_config, configured_services={}, formation_id="test-formation"
        )
        overlord._capability_models = {}  # No capability models
        overlord._model_cache = {}
        overlord._load_default_persona()

        raw = "Raw response text"
        formatted = await overlord._apply_persona(raw, "User message")

        # Should return raw when no text model available
        assert formatted == raw


class TestPersonaIntegration:
    """Test persona application in actual response flow."""

    @pytest.mark.asyncio
    async def test_sync_response_gets_persona(self, overlord_with_persona):
        """Test that sync chat responses get persona applied."""
        # Create a mock response
        response = MuxiResponse(
            role="assistant", content='{"task": "completed", "result": "success"}'
        )

        # Mock the agent processing
        mock_agent = AsyncMock()
        mock_agent.process_message.return_value = response

        # Mock agent retrieval
        with patch.object(overlord_with_persona, "_get_agent", return_value=mock_agent):
            # Mock persona application
            with patch.object(
                overlord_with_persona, "_apply_persona", return_value="Task completed successfully!"
            ) as mock_apply:

                # Mock other required methods
                with patch.object(
                    overlord_with_persona, "_check_agent_clarification_request", return_value=None
                ):
                    with patch.object(
                        overlord_with_persona, "_should_skip_clarification", return_value=True
                    ):
                        with patch.object(
                            overlord_with_persona, "add_message_to_memory", return_value=None
                        ):

                            result = await overlord_with_persona._process_sync_chat(
                                message="Complete this task",
                                agent_name="test-agent",
                                user_id="test-user",
                            )

                            # Verify persona was applied
                            assert result.content == "Task completed successfully!"
                            mock_apply.assert_called_once_with(
                                '{"task": "completed", "result": "success"}', "Complete this task"
                            )

    @pytest.mark.asyncio
    async def test_error_response_gets_persona(self, overlord_with_persona):
        """Test that error responses get persona applied."""
        from muxi.runtime.formation.credentials import MissingCredentialError

        # Mock the error scenario
        mock_agent = AsyncMock()
        mock_agent.process_message.side_effect = MissingCredentialError(
            service="github", user_id="test-user"
        )

        with patch.object(overlord_with_persona, "_get_agent", return_value=mock_agent):
            with patch.object(
                overlord_with_persona,
                "_apply_persona",
                return_value="I need your GitHub credentials to continue.",
            ) as mock_apply:
                with patch.object(
                    overlord_with_persona, "_should_skip_clarification", return_value=True
                ):
                    with patch.object(
                        overlord_with_persona, "add_message_to_memory", return_value=None
                    ):

                        result = await overlord_with_persona._process_sync_chat(
                            message="Push to GitHub", agent_name="test-agent", user_id="test-user"
                        )

                        # Verify persona was applied to error
                        assert result.content == "I need your GitHub credentials to continue."
                        mock_apply.assert_called_once()

                        # Check that the error message was passed to persona
                        call_args = mock_apply.call_args[0]
                        assert "GitHub" in call_args[0]
                        assert "credentials" in call_args[0].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
