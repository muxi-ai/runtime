"""
Unit tests for the Overlord class.

These tests verify that the Overlord implementation works correctly.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.muxi.runtime.formation.overlord import Overlord
from src.muxi.runtime.datatypes.response import MuxiResponse


class TestOverlord:
    """Tests for the Overlord class."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        mock = MagicMock()
        mock.name = "mock_agent"
        mock.process_message = AsyncMock(return_value=MuxiResponse(
            role="assistant",
            content="Agent response"
        ))
        return mock

    @pytest.fixture
    def mock_buffer_memory(self):
        """Create a mock buffer memory for testing."""
        # Creating a custom class to define methods for the mock
        class MockShortTermMemory:
            def add(self, message, metadata):
                return True

            def search(self, *args, **kwargs):
                return [(0.9, {"text": "Memory content"})]

            def clear(self, *args, **kwargs):
                return None

        # Create and return the mock
        mock = MagicMock(spec=MockShortTermMemory())
        mock.add.return_value = True
        mock.search.return_value = [(0.9, {"text": "Memory content"})]
        mock.clear.return_value = None
        return mock

    @pytest.fixture
    def mock_long_term_memory(self):
        """Create a mock long term memory for testing."""
        # Creating a custom class to define methods for the mock
        class MockLongTermMemory:
            default_collection = "default"

            async def add(self, content, metadata, embedding=None):
                return "memory_id_123"

            async def search(self, query=None, query_embedding=None, k=5, filter_metadata=None):
                return [(0.8, {
                    "text": "Long term memory content",
                    "metadata": {"source": "knowledge_base"}
                })]

            def clear(self, *args, **kwargs):
                return None

            def create_collection(self, *args, **kwargs):
                return None

        # Create and return the mock
        mock = MagicMock(spec=MockLongTermMemory())
        mock.add = AsyncMock(return_value="memory_id_123")
        mock.search = AsyncMock(return_value=[
            (0.8, {
                "text": "Long term memory content",
                "metadata": {"source": "knowledge_base"}
            })
        ])
        mock.clear.return_value = None
        mock.create_collection.return_value = None
        mock.default_collection = "default"
        return mock

    @pytest.fixture
    def overlord(self):
        """Create an Overlord instance for testing."""
        overlord = Overlord()
        # Note: Agent registration is now handled by Formation class
        return overlord

    @pytest.fixture
    def memory_overlord(self, mock_buffer_memory, mock_long_term_memory):
        """Create an Overlord instance with memory for testing."""
        return Overlord(
            buffer_memory=mock_buffer_memory,
            long_term_memory=mock_long_term_memory
        )

    def test_initialization(self):
        """Test that an overlord can be initialized correctly."""
        overlord = Overlord()

        assert overlord.agents == {}
        assert overlord.buffer_memory is None
        assert overlord.long_term_memory is None

    def test_initialization_with_memory(self, mock_buffer_memory, mock_long_term_memory):
        """Test that an overlord can be initialized with memory."""
        overlord = Overlord(
            buffer_memory=mock_buffer_memory,
            long_term_memory=mock_long_term_memory
        )

        assert overlord.buffer_memory == mock_buffer_memory
        assert overlord.long_term_memory == mock_long_term_memory

    @pytest.mark.skip("Agent registration now handled by Formation class - test needs to be refactored")
    def test_register_agent(self, overlord, mock_agent):
        """Test that an agent can be registered."""
        # Note: Agent registration moved to Formation class
        pass

    @pytest.mark.skip("Agent registration now handled by Formation class - test needs to be refactored")
    def test_register_multiple_agents(self, overlord):
        """Test that multiple agents can be registered."""
        # Note: Agent registration moved to Formation class
        pass

    @pytest.mark.asyncio
    async def test_process_message(self, overlord, mock_agent):
        """Test that a message can be processed by a specified agent."""
        # Add the mock agent to overlord for testing
        overlord.agents["mock_agent"] = mock_agent

        # Create a message
        message = MuxiResponse(role="user", content="Hello, world!")

        # Process the message
        response = await overlord.process_message("mock_agent", message)

        # Verify the response
        assert response.role == "assistant"
        assert response.content == "Agent response"

        # Verify the agent was called correctly
        mock_agent.process_message.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_process_message_nonexistent_agent(self, overlord):
        """Test that processing a message for a nonexistent agent raises an error."""
        # Create a message
        message = MuxiResponse(role="user", content="Hello, world!")

        # Processing the message for a nonexistent agent should raise a ValueError
        with pytest.raises(ValueError):
            await overlord.process_message("nonexistent_agent", message)

    @pytest.mark.asyncio
    async def test_collaborative_processing(self):
        """Test that messages can be processed collaboratively between agents."""
        # Create an overlord
        overlord = Overlord()

        # Create specialized mock agents
        research_agent = MagicMock()
        research_agent.name = "research"
        research_agent.process_message = AsyncMock(
            return_value=MuxiResponse(
                role="assistant",
                content="Research information: ..."
            )
        )

        writing_agent = MagicMock()
        writing_agent.name = "writer"
        writing_agent.process_message = AsyncMock(
            return_value=MuxiResponse(
                role="assistant",
                content="Final article: ..."
            )
        )

        # Note: In new API, agents would be managed through Formation
        # For this test, we'll simulate the old behavior
        overlord.agents = {
            "research": research_agent,
            "writer": writing_agent
        }

        # Create messages
        research_query = MuxiResponse(
            role="user",
            content="Find information about AI"
        )
        writing_query = MuxiResponse(
            role="user",
            content="Write an article about AI"
        )

        # Process the messages in sequence
        research_response = await overlord.process_message(
            "research",
            research_query
        )
        writing_response = await overlord.process_message(
            "writer",
            writing_query
        )

        # Verify the responses
        assert research_response.role == "assistant"
        assert "Research information" in research_response.content

        assert writing_response.role == "assistant"
        assert "Final article" in writing_response.content

        # Verify the agents were called correctly
        research_agent.process_message.assert_called_once_with(research_query)
        writing_agent.process_message.assert_called_once_with(writing_query)

    @pytest.mark.asyncio
    async def test_remove_agent(self):
        """Test that an agent can be removed using Formation."""
        from src.muxi.runtime.formation.formation import Formation

        # Create formation and start the overlord
        formation = Formation()
        formation.start_overlord()

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"

        # Add agent through Formation
        agent_id = formation.add_agent(mock_agent, agent_id="test_agent")

        # Test removing the agent (this is now an async operation)
        success = await formation.remove_agent_async(agent_id)

        # Verify the agent was removed successfully
        assert success is True

    def test_get_agent(self, overlord, mock_agent):
        """Test that an agent can be retrieved."""
        # Add the mock agent to overlord for testing
        overlord.agents["mock_agent"] = mock_agent

        # Get the agent
        agent = overlord.get_agent("mock_agent")

        # Verify the agent was retrieved
        assert agent == mock_agent

    def test_get_nonexistent_agent(self, overlord):
        """Test that getting a nonexistent agent raises an error."""
        # Getting a nonexistent agent should raise a ValueError
        with pytest.raises(ValueError):
            overlord.get_agent("nonexistent_agent")

    @pytest.mark.asyncio
    async def test_list_agents(self, overlord, mock_agent):
        """Test that agents can be listed."""
        # Add the mock agent to overlord for testing
        overlord.agents["mock_agent"] = mock_agent

        # Register additional agents
        mock_agent2 = MagicMock()
        mock_agent2.name = "mock_agent2"

        mock_agent3 = MagicMock()
        mock_agent3.name = "mock_agent3"

        # Note: In new API, agents would be managed through Formation
        # For this test, we'll simulate the old behavior
        overlord.agents["mock_agent2"] = mock_agent2
        overlord.agents["mock_agent3"] = mock_agent3

        # List the agents
        agents = await overlord.list_agents()

        # Verify the agents were listed
        assert len(agents) == 3
        assert "mock_agent" in agents
        assert "mock_agent2" in agents
        assert "mock_agent3" in agents

    @pytest.mark.asyncio
    async def test_add_to_buffer_memory(self, memory_overlord, mock_buffer_memory):
        """Test adding to buffer memory."""
        # Set up mock for add method
        mock_buffer_memory.add = AsyncMock()

        # Add to buffer memory
        await memory_overlord.add_to_buffer_memory(
            message="Test message",
            metadata={"test": "metadata"},
            agent_id="test_agent"
        )

        # Verify buffer memory was called
        mock_buffer_memory.add.assert_called_once_with(
            "Test message",
            metadata={"test": "metadata", "agent_id": "test_agent"}
        )

    @pytest.mark.asyncio
    async def test_add_to_buffer_memory_no_memory(self, overlord):
        """Test adding to buffer memory when not available."""
        # Override buffer_memory to None
        overlord.buffer_memory = None

        # Add to buffer memory when it's None
        result = await overlord.add_to_buffer_memory(
            message="Test message",
            metadata={"test": "metadata"}
        )

        # Verify result
        assert result is False

    @pytest.mark.asyncio
    async def test_add_to_long_term_memory(self, memory_overlord, mock_long_term_memory):
        """Test adding to long-term memory."""
        # Add to long-term memory
        result = await memory_overlord.add_to_long_term_memory(
            content="Test content",
            metadata={"test": "metadata"},
            agent_id="test_agent"
        )

        # Verify long-term memory was called
        mock_long_term_memory.add.assert_called_once_with(
            content="Test content",
            metadata={"test": "metadata", "agent_id": "test_agent"},
            embedding=None
        )

        # Verify result
        assert result == "memory_id_123"

    @pytest.mark.asyncio
    async def test_add_to_long_term_memory_no_memory(self, overlord):
        """Test adding to long-term memory when not available."""
        # Add to long-term memory when it's None
        result = await overlord.add_to_long_term_memory(
            content="Test content",
            metadata={"test": "metadata"}
        )

        # Verify result
        assert result is None

    @pytest.mark.skip("Test needs to be refactored due to API changes")
    @pytest.mark.asyncio
    async def test_search_memory(
        self,
        memory_overlord,
        mock_buffer_memory,
        mock_long_term_memory
    ):
        """Test searching memory."""
        # This test needs to be rewritten to match the current API
        pass

    @pytest.mark.skip("Test needs to be refactored due to API changes")
    def test_clear_memory(self, memory_overlord, mock_buffer_memory, mock_long_term_memory):
        """Test clearing memory."""
        # This test needs to be rewritten to match the current API
        pass

    def test_clear_memory_agent_filter(self, memory_overlord, mock_buffer_memory):
        """Test clearing memory with agent filter."""
        # Clear memory for specific agent
        memory_overlord.clear_memory(agent_id="test_agent")

        # Verify buffer memory was cleared with filter
        mock_buffer_memory.clear.assert_called_once_with(
            filter_metadata={"agent_id": "test_agent"}
        )
