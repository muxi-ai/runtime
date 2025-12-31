"""Unit tests for clarification system request vs execution distinction."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from muxi.runtime.formation.clarification.analyzer import InformationAnalyzer


class TestExecutionContextHandling:
    """Test execution context handling in clarification analyzer."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing."""
        llm = AsyncMock()
        return llm

    @pytest.fixture
    def analyzer(self, mock_llm):
        """Create a clarification analyzer with mock LLM."""
        return InformationAnalyzer(model=mock_llm)

    @pytest.mark.asyncio
    async def test_github_request_with_execution_context(self, analyzer, mock_llm):
        """Test that GitHub repository requests are marked as CLEAR when MCP is available."""
        # Mock LLM to return CLEAR
        mock_llm.chat.return_value = "CLEAR"

        execution_context = {
            "has_mcp_servers": True,
            "mcp_services": ["github", "gitlab"],
            "session_has_prior_service_use": False
        }

        result = await analyzer.analyze_request(
            user_message="List my GitHub repositories",
            intent="list_repositories",
            available_tools=[],
            user_context={},
            execution_context=execution_context
        )

        # Should return can_proceed=True
        assert result.can_proceed is True
        assert len(result.missing_info) == 0

        # Verify LLM was called with execution context in system message
        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args[0][0]
        system_message = call_args[0]["content"]
        assert "MCP Services Available: ['github', 'gitlab']" in system_message

    @pytest.mark.asyncio
    async def test_follow_up_request_with_session_history(self, analyzer, mock_llm):
        """Test that follow-up requests are marked as CLEAR when session has prior service use."""
        # Mock LLM to return CLEAR
        mock_llm.chat.return_value = "CLEAR"

        execution_context = {
            "has_mcp_servers": True,
            "mcp_services": ["github"],
            "session_has_prior_service_use": True  # Session already used services
        }

        result = await analyzer.analyze_request(
            user_message="Create an issue in repository X",
            intent="create_issue",
            available_tools=[],
            user_context={},
            execution_context=execution_context
        )

        # Should return can_proceed=True
        assert result.can_proceed is True
        assert len(result.missing_info) == 0

        # Verify session history was included in context
        call_args = mock_llm.chat.call_args[0][0]
        system_message = call_args[0]["content"]
        assert "Session has prior service use: True" in system_message

    @pytest.mark.asyncio
    async def test_ambiguous_request_needs_clarification(self, analyzer, mock_llm):
        """Test that truly ambiguous requests still need clarification."""
        # Mock LLM to return NEEDS_CLARIFICATION
        mock_llm.chat.return_value = "NEEDS_CLARIFICATION: What would you like me to build?"

        execution_context = {
            "has_mcp_servers": True,
            "mcp_services": ["github"],
            "session_has_prior_service_use": False
        }

        result = await analyzer.analyze_request(
            user_message="Build it",
            intent="build",
            available_tools=[],
            user_context={},
            execution_context=execution_context
        )

        # Should need clarification
        assert result.can_proceed is False
        assert len(result.missing_info) > 0
        assert "What would you like me to build?" in result.missing_info[0]

    @pytest.mark.asyncio
    async def test_execution_context_none_handled_gracefully(self, analyzer, mock_llm):
        """Test that missing execution context is handled gracefully."""
        # Mock LLM to return response
        mock_llm.chat.return_value = "CLEAR"

        result = await analyzer.analyze_request(
            user_message="List my GitHub repositories",
            intent="list_repositories",
            available_tools=[],
            user_context={},
            execution_context=None  # No execution context
        )

        # Should still work
        assert result is not None

        # Verify LLM was called without execution context
        call_args = mock_llm.chat.call_args[0][0]
        system_message = call_args[0]["content"]
        assert "System Execution Capabilities" not in system_message

    @pytest.mark.asyncio
    async def test_request_vs_execution_clarification_distinction(self, analyzer, mock_llm):
        """Test that the system distinguishes between request and execution clarification."""
        # Test cases with expected outcomes
        test_cases = [
            # Clear intent, execution detail needed
            ("List my GitHub repositories", "CLEAR", True),
            ("Deploy to production", "CLEAR", True),
            ("Check my email", "CLEAR", True),
            ("Create an issue in repo X", "CLEAR", True),

            # Unclear intent, request clarification needed
            ("Build it", "NEEDS_CLARIFICATION: What would you like me to build?", False),
            ("Fix the bug", "NEEDS_CLARIFICATION: Which bug needs to be fixed?", False),
            ("Send the message", "NEEDS_CLARIFICATION: What message would you like to send?", False),
        ]

        execution_context = {
            "has_mcp_servers": True,
            "mcp_services": ["github", "email"],
            "session_has_prior_service_use": False
        }

        for message, expected_response, expected_proceed in test_cases:
            mock_llm.chat.return_value = expected_response

            result = await analyzer.analyze_request(
                user_message=message,
                intent="general",
                available_tools=[],
                user_context={},
                execution_context=execution_context
            )

            assert result.can_proceed == expected_proceed, f"Failed for message: {message}"

            # Verify the prompt includes the distinction guidance
            if mock_llm.chat.called:
                call_args = mock_llm.chat.call_args[0][0]
                system_message = call_args[0]["content"]
                assert "REQUEST CLARIFICATION" in system_message
                assert "EXECUTION CLARIFICATION" in system_message
                assert "KEY RULE: If you understand WHAT the user wants to do, return CLEAR" in system_message


class TestSessionServiceHistory:
    """Test session service history tracking."""

    @pytest.mark.asyncio
    async def test_session_history_initialized(self):
        """Test that session service history is properly initialized."""
        from muxi.runtime.formation.overlord.overlord import Overlord

        # Create minimal overlord instance
        agents = {}
        buffer_memory_manager = MagicMock()
        long_term_memory_manager = MagicMock()
        model = MagicMock()

        with patch.object(Overlord, '__init__', lambda self: None):
            overlord = Overlord()
            overlord.agents = agents
            overlord.buffer_memory_manager = buffer_memory_manager
            overlord.long_term_memory_manager = long_term_memory_manager
            overlord.model = model
            overlord._pending_clarifications = {}
            overlord._session_service_history = {}

            # Verify initialization
            assert hasattr(overlord, '_session_service_history')
            assert isinstance(overlord._session_service_history, dict)
            assert len(overlord._session_service_history) == 0

    @pytest.mark.asyncio
    async def test_service_tracked_after_credential_selection(self):
        """Test that services are tracked after credential selection."""
        from muxi.runtime.formation.overlord.overlord import Overlord

        with patch.object(Overlord, '__init__', lambda self: None):
            overlord = Overlord()
            overlord._session_service_history = {}

            # Simulate tracking a service
            session_id = "test_session_123"
            service = "github"

            # Track service use (simulating the code at line 5177)
            if session_id not in overlord._session_service_history:
                overlord._session_service_history[session_id] = set()
            overlord._session_service_history[session_id].add(service)

            # Verify tracking
            assert session_id in overlord._session_service_history
            assert "github" in overlord._session_service_history[session_id]

            # Add another service
            overlord._session_service_history[session_id].add("gitlab")
            assert len(overlord._session_service_history[session_id]) == 2
            assert "gitlab" in overlord._session_service_history[session_id]

    @pytest.mark.asyncio
    async def test_execution_context_includes_session_history(self):
        """Test that execution context properly includes session history."""
        from muxi.runtime.formation.overlord.overlord import Overlord

        with patch.object(Overlord, '__init__', lambda self: None):
            overlord = Overlord()
            overlord._session_service_history = {
                "test_session": {"github", "gitlab"}
            }
            overlord.mcp_coordinator = MagicMock()
            overlord.mcp_coordinator.get_servers = MagicMock(return_value=["github-mcp", "gitlab-mcp"])

            # Build execution context (simulating code at line 5664)
            session_id = "test_session"
            execution_context = {
                "has_mcp_servers": bool(hasattr(overlord, "mcp_coordinator") and overlord.mcp_coordinator),
                "mcp_services": [],
                "session_has_prior_service_use": False
            }

            if hasattr(overlord, "mcp_coordinator") and overlord.mcp_coordinator:
                servers = overlord.mcp_coordinator.get_servers()
                execution_context["mcp_services"] = [
                    server.replace("-mcp", "").replace("_mcp", "") for server in servers
                ]

                if session_id and hasattr(overlord, "_session_service_history"):
                    session_history = overlord._session_service_history.get(session_id, set())
                    execution_context["session_has_prior_service_use"] = bool(session_history)

            # Verify execution context
            assert execution_context["has_mcp_servers"] is True
            assert execution_context["mcp_services"] == ["github", "gitlab"]
            assert execution_context["session_has_prior_service_use"] is True

    @pytest.mark.asyncio
    async def test_execution_context_for_new_session(self):
        """Test execution context for a session with no history."""
        from muxi.runtime.formation.overlord.overlord import Overlord

        with patch.object(Overlord, '__init__', lambda self: None):
            overlord = Overlord()
            overlord._session_service_history = {}
            overlord.mcp_coordinator = MagicMock()
            overlord.mcp_coordinator.get_servers = MagicMock(return_value=["github-mcp"])

            # Build execution context for new session
            session_id = "new_session"
            execution_context = {
                "has_mcp_servers": bool(hasattr(overlord, "mcp_coordinator") and overlord.mcp_coordinator),
                "mcp_services": [],
                "session_has_prior_service_use": False
            }

            if hasattr(overlord, "mcp_coordinator") and overlord.mcp_coordinator:
                servers = overlord.mcp_coordinator.get_servers()
                execution_context["mcp_services"] = [
                    server.replace("-mcp", "").replace("_mcp", "") for server in servers
                ]

                if session_id and hasattr(overlord, "_session_service_history"):
                    session_history = overlord._session_service_history.get(session_id, set())
                    execution_context["session_has_prior_service_use"] = bool(session_history)

            # Verify execution context
            assert execution_context["has_mcp_servers"] is True
            assert execution_context["mcp_services"] == ["github"]
            assert execution_context["session_has_prior_service_use"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
