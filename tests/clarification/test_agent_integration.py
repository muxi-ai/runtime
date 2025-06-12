"""
Unit tests for Agent integration with the clarification system.

Tests the integration of clarification functionality into the Agent class
without breaking existing Agent functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.muxi.runtime.agent import Agent
from src.muxi.runtime.mcp.message import MCPMessage


class TestAgentClarificationIntegration:
    """Test Agent integration with clarification system"""

    @pytest.fixture
    def mock_model(self):
        """Create mock LLM model"""
        model = MagicMock()
        model.chat = AsyncMock(return_value="Mock response")
        return model

    @pytest.fixture
    def mock_overlord(self):
        """Create mock overlord"""
        overlord = MagicMock()
        overlord.add_message_to_memory = AsyncMock()
        overlord.handle_user_information_extraction = AsyncMock()
        overlord.get_user_context_memory = AsyncMock(return_value={})
        return overlord

    @pytest.fixture
    def agent(self, mock_model, mock_overlord):
        """Create Agent instance for testing"""
        return Agent(
            model=mock_model,
            overlord=mock_overlord,
            agent_id="test-agent",
            system_message="Test agent"
        )

    def test_agent_initialization_includes_clarification(self, agent):
        """Test that Agent properly initializes clarification components"""
        assert hasattr(agent, '_clarification_analyzer')
        assert hasattr(agent, '_clarification_manager')
        assert hasattr(agent, '_clarification_generator')
        assert hasattr(agent, '_clarification_enricher')
        assert hasattr(agent, '_clarification_parser')

    @pytest.mark.asyncio
    async def test_process_message_preserves_existing_functionality(self, agent, mock_model):
        """Test that existing message processing functionality is preserved"""
        # Test normal message processing without clarification
        user_message = "Hello, how are you?"

        # Mock the clarification checks to return None (no clarification needed)
        agent._check_for_clarification_needs = AsyncMock(return_value=None)
        agent._handle_potential_clarification_response = AsyncMock(return_value=None)

        response = await agent.process_message(user_message, user_id=1)

        # Verify response structure
        assert isinstance(response, MCPMessage)
        assert response.role == "assistant"
        assert response.content == "Mock response"

        # Verify model was called
        mock_model.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_clarification_response_handling(self, agent):
        """Test handling of clarification responses"""
        user_message = "My risk tolerance is moderate"
        user_id = 1

        # Mock clarification response processing
        agent._handle_potential_clarification_response = AsyncMock(
            return_value="Thank you for clarifying. Based on your moderate risk tolerance..."
        )

        response = await agent.process_message(user_message, user_id=user_id)

        # Verify clarification response was handled
        assert isinstance(response, MCPMessage)
        assert "risk tolerance" in response.content

        # Verify clarification handler was called
        agent._handle_potential_clarification_response.assert_called_once_with(
            user_message, user_id
        )

    @pytest.mark.asyncio
    async def test_clarification_question_generation(self, agent):
        """Test generation of clarification questions"""
        user_message = "I want to invest my money"
        user_id = 1

        # Mock clarification checks
        agent._handle_potential_clarification_response = AsyncMock(return_value=None)
        agent._check_for_clarification_needs = AsyncMock(
            return_value="I'd be happy to help you with investing. What's your risk tolerance?"
        )

        response = await agent.process_message(user_message, user_id=user_id)

        # Verify clarification question was returned
        assert isinstance(response, MCPMessage)
        assert "risk tolerance" in response.content

        # Verify clarification analyzer was called
        agent._check_for_clarification_needs.assert_called_once_with(
            user_message, user_id
        )

    @pytest.mark.asyncio
    async def test_anonymous_user_skips_clarification(self, agent, mock_model):
        """Test that anonymous users (user_id=0) skip clarification"""
        user_message = "I want to invest"
        user_id = 0  # Anonymous user

        response = await agent.process_message(user_message, user_id=user_id)

        # Verify response was processed normally without clarification
        assert isinstance(response, MCPMessage)
        assert response.content == "Mock response"

        # Verify model was called (normal processing path)
        mock_model.chat.assert_called_once()

    def test_intent_extraction(self, agent):
        """Test intent extraction from user messages"""
        # Test investment intent
        assert agent._extract_intent_from_message("I want to invest money") == "investment_advice"

        # Test explanation intent
        assert (
            agent._extract_intent_from_message("Can you explain blockchain?")
            == "technical_explanation"
        )

        # Test booking intent
        assert agent._extract_intent_from_message("Book a restaurant") == "booking_request"

        # Test search intent
        assert agent._extract_intent_from_message("Find me a hotel") == "search_request"

        # Test general intent
        assert agent._extract_intent_from_message("Hello there") == "general_assistance"

    @pytest.mark.asyncio
    async def test_clarification_system_failure_graceful_degradation(self, agent, mock_model):
        """Test that Agent gracefully handles clarification system failures"""
        user_message = "Help me invest"
        user_id = 1

        # Mock clarification system failure
        agent._check_for_clarification_needs = AsyncMock(
            side_effect=Exception("Clarification error")
        )
        agent._handle_potential_clarification_response = AsyncMock(return_value=None)

        response = await agent.process_message(user_message, user_id=user_id)

        # Verify Agent falls back to normal processing
        assert isinstance(response, MCPMessage)
        assert response.content == "Mock response"

        # Verify model was still called
        mock_model.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_agent_methods_unaffected(self, agent, mock_overlord):
        """Test that existing Agent methods are not affected by clarification additions"""
        # Test run method
        result = await agent.run("Test input", use_memory=False)
        assert isinstance(result, str)

        # Test get_relevant_memories method
        mock_overlord.search_memory = AsyncMock(return_value=[])
        memories = await agent.get_relevant_memories("test query")
        assert isinstance(memories, list)

        # Test discover_agents method
        mock_overlord.get_available_agents_for_a2a = MagicMock(return_value={})
        agents = agent.discover_agents()
        assert isinstance(agents, dict)

    @pytest.mark.asyncio
    async def test_invoke_tool_unchanged(self, agent):
        """Test that invoke_tool method works unchanged"""
        # Mock MCP service
        mock_mcp_service = MagicMock()
        mock_mcp_service.invoke_tool = AsyncMock(return_value={"result": "success"})
        agent._mcp_service = mock_mcp_service

        result = await agent.invoke_tool("test_tool", {"param": "value"})

        assert result == {"result": "success"}
        mock_mcp_service.invoke_tool.assert_called_once_with(
            tool_name="test_tool",
            parameters={"param": "value"},
            server_id=None,
            request_timeout=agent.request_timeout
        )
