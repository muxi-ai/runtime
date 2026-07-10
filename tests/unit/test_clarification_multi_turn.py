"""Unit tests for multi-turn clarification functionality.

Tests the integration between Overlord and UnifiedClarificationSystem
to ensure multi-turn clarification works correctly.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.formation.overlord.clarification import (
    ClarificationResult,
    UnifiedClarificationSystem,
)


class MockOverlord:
    """Mock Overlord class for testing clarification flow."""

    def __init__(self):
        # Core attributes
        self.formation_id = "test_formation"
        self._pending_clarifications = {}
        self.auto_decomposition = False

        # Mock clarification system
        self.clarification = Mock(spec=UnifiedClarificationSystem)
        self.clarification.needs_clarification = AsyncMock()
        self.clarification.looks_like_credential_token = AsyncMock(return_value=False)
        self.clarification.extract_token_from_text = AsyncMock(return_value=None)

        # Mock credential resolver
        self.credential_resolver = None

        # Mock agents
        self.agents = {}
        self.default_agent = None

        # Mock other components
        self.llm = Mock()
        self.agent_router = Mock()
        self.buffer_memory_manager = None
        self.observability_manager = Mock()
        self.logger = Mock()

    async def _process_sync_chat_simplified(
        self, message, agent_name, user_id, session_id, request_id
    ):
        """Simplified version of _process_sync_chat for testing."""

        # Check if message contains a credential token
        contains_token = (
            await self.clarification.looks_like_credential_token(message)
            if (session_id and self.clarification)
            else False
        )

        # Handle credential tokens
        if session_id and contains_token:
            if session_id in self._pending_clarifications:
                clarification_info = self._pending_clarifications[session_id]
                if clarification_info.get("type") == "credential":
                    service = clarification_info.get("service")
                    if self.credential_resolver:
                        extracted_token = (
                            await self.clarification.extract_token_from_text(message)
                            if self.clarification
                            else None
                        )
                        if extracted_token:
                            await self.credential_resolver.set_credential(
                                service=service, credential=extracted_token, user_id=user_id
                            )
                            del self._pending_clarifications[session_id]
                            return MuxiResponse(
                                role="assistant",
                                content=f"Credential for {service} has been stored.",
                                metadata={},
                            )

        # Check if clarification is needed - NO BYPASS for responses
        if not agent_name and self.clarification and request_id:
            clarification_result = await self.clarification.needs_clarification(
                message=message,
                request_id=request_id,
                session_id=session_id,
                context={"user_id": user_id},
            )

            if clarification_result.action == "clarify":
                # Store minimal info - just request_id for reuse
                if session_id:
                    self._pending_clarifications[session_id] = {
                        "request_id": request_id,
                        "type": clarification_result.mode,
                    }

                return MuxiResponse(
                    role="assistant",
                    content=clarification_result.question,
                    metadata={"clarification": True, "mode": clarification_result.mode},
                )

            elif clarification_result.action == "execute":
                # Clarification complete - clean up
                if session_id in self._pending_clarifications:
                    del self._pending_clarifications[session_id]

                # Use the enhanced request from clarification
                message = clarification_result.request

        # Process with agent (simplified)
        if agent_name and agent_name in self.agents:
            agent = self.agents[agent_name]
            result = await agent.process(message, user_id=user_id)
            return MuxiResponse(role="assistant", content=result["content"], metadata={})

        # Default response
        return MuxiResponse(role="assistant", content=f"Processing: {message}", metadata={})


@pytest.fixture
async def mock_overlord():
    """Create a mock Overlord for testing."""
    return MockOverlord()


@pytest.mark.asyncio
async def test_clarification_not_bypassed_for_responses(mock_overlord):
    """Test that clarification responses are NOT bypassed."""
    overlord = mock_overlord

    # Setup: First message triggers clarification
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="clarify", mode="direct", question="What would you like to build?", request=None
    )

    # First request: "Build it"
    response1 = await overlord._process_sync_chat_simplified(
        message="Build it",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_123",
    )

    # Verify clarification was triggered
    assert overlord.clarification.needs_clarification.called
    assert response1.content == "What would you like to build?"
    assert "test_session" in overlord._pending_clarifications
    assert overlord._pending_clarifications["test_session"]["request_id"] == "req_123"

    # Reset mock for second call
    overlord.clarification.needs_clarification.reset_mock()

    # Setup: Second message (response to clarification) should also go through clarification
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="clarify",
        mode="direct",
        question="What specifically would you like to build?",
        request=None,
    )

    # Second request: "I want to build a" (still ambiguous)
    response2 = await overlord._process_sync_chat_simplified(
        message="I want to build a",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_123",  # Same request_id for continuity
    )

    # Verify clarification was NOT bypassed
    assert overlord.clarification.needs_clarification.called
    assert response2.content == "What specifically would you like to build?"


@pytest.mark.asyncio
async def test_execute_action_cleans_up_pending_clarification(mock_overlord):
    """Test that execute action cleans up pending clarifications."""
    overlord = mock_overlord

    # Setup: Add a pending clarification
    overlord._pending_clarifications["test_session"] = {"request_id": "req_123", "type": "direct"}

    # Setup: Clarification returns execute action
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="execute",
        mode="direct",
        question=None,
        request="Build a website",  # Enhanced request
    )

    # Process message
    response = await overlord._process_sync_chat_simplified(
        message="a website",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_123",
    )

    # Verify pending clarification was cleaned up
    assert "test_session" not in overlord._pending_clarifications

    # Verify the enhanced request was processed
    assert "Build a website" in response.content


@pytest.mark.asyncio
async def test_clarification_stores_minimal_state(mock_overlord):
    """Test that clarification only stores minimal state."""
    overlord = mock_overlord

    # Setup: Clarification returns clarify action
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="clarify", mode="brainstorm", question="Could you elaborate on that?", request=None
    )

    # Process message
    await overlord._process_sync_chat_simplified(
        message="Do something complex",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_456",
    )

    # Verify only minimal state is stored
    assert "test_session" in overlord._pending_clarifications
    pending = overlord._pending_clarifications["test_session"]
    assert pending["request_id"] == "req_456"
    assert pending["type"] == "brainstorm"

    # Verify we're NOT storing the original message or user_id
    assert "original_message" not in pending
    assert "user_id" not in pending


@pytest.mark.asyncio
async def test_clarification_called_without_agent_name(mock_overlord):
    """Test that clarification is only called when no specific agent is requested."""
    overlord = mock_overlord

    # Setup mock agent
    mock_agent = Mock()
    mock_agent.process = AsyncMock(return_value={"content": "Done with task"})
    overlord.agents = {"specific_agent": mock_agent}

    # Test with specific agent - clarification should NOT be called
    await overlord._process_sync_chat_simplified(
        message="Do something",
        agent_name="specific_agent",
        user_id="test_user",
        session_id="test_session",
        request_id="req_789",
    )

    # Verify clarification was NOT called
    assert not overlord.clarification.needs_clarification.called

    # Reset and test without agent - clarification SHOULD be called
    overlord.clarification.needs_clarification.reset_mock()
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="execute", mode=None, question=None, request="Do something"
    )

    await overlord._process_sync_chat_simplified(
        message="Do something",
        agent_name=None,  # No specific agent
        user_id="test_user",
        session_id="test_session",
        request_id="req_790",
    )

    # Verify clarification WAS called
    assert overlord.clarification.needs_clarification.called


@pytest.mark.asyncio
async def test_credential_token_detection_still_works(mock_overlord):
    """Test that credential token detection still functions."""
    overlord = mock_overlord

    # Setup: Message contains a token
    overlord.clarification.looks_like_credential_token.return_value = True
    overlord.clarification.extract_token_from_text.return_value = "ghp_secrettoken123"

    # Setup: Add pending credential clarification
    overlord._pending_clarifications["test_session"] = {
        "request_id": "req_111",
        "type": "credential",
        "service": "github",
    }

    # Setup credential resolver
    overlord.credential_resolver = Mock()
    overlord.credential_resolver.set_credential = AsyncMock()

    # Process message with token
    await overlord._process_sync_chat_simplified(
        message="Here is my token: ghp_secrettoken123",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_111",
    )

    # Verify token was detected and extracted
    assert overlord.clarification.looks_like_credential_token.called
    assert overlord.clarification.extract_token_from_text.called

    # Verify credential was stored
    overlord.credential_resolver.set_credential.assert_called_with(
        service="github", credential="ghp_secrettoken123", user_id="test_user"
    )

    # Verify pending clarification was cleaned up
    assert "test_session" not in overlord._pending_clarifications


@pytest.mark.asyncio
async def test_multi_turn_clarification_flow(mock_overlord):
    """Test complete multi-turn clarification flow."""
    overlord = mock_overlord

    # Turn 1: Initial ambiguous request
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="clarify", mode="direct", question="What would you like to build?", request=None
    )

    response1 = await overlord._process_sync_chat_simplified(
        message="Build it",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_multi_1",
    )

    assert response1.content == "What would you like to build?"
    assert overlord._pending_clarifications["test_session"]["request_id"] == "req_multi_1"

    # Turn 2: Still ambiguous response
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="clarify", mode="direct", question="What kind of application?", request=None
    )

    response2 = await overlord._process_sync_chat_simplified(
        message="an application",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_multi_1",  # Same request_id
    )

    assert response2.content == "What kind of application?"
    assert overlord._pending_clarifications["test_session"]["request_id"] == "req_multi_1"

    # Turn 3: Clear response - execute
    overlord.clarification.needs_clarification.return_value = ClarificationResult(
        action="execute", mode="direct", question=None, request="Build a web application"
    )

    response3 = await overlord._process_sync_chat_simplified(
        message="a web application",
        agent_name=None,
        user_id="test_user",
        session_id="test_session",
        request_id="req_multi_1",  # Same request_id
    )

    # Verify clarification complete
    assert "test_session" not in overlord._pending_clarifications
    assert "Build a web application" in response3.content


class _RecallGateOverlord:
    """Bare-attribute overlord stub for the recall-question memory gate.

    A plain object (not Mock) so ``hasattr`` checks in the gate reflect
    exactly the attributes configured here.
    """

    def __init__(self, vector_results, graph_block):
        self.buffer_memory = None
        self.extraction_model = None
        self.persistent_memory_manager = Mock(
            search_long_term_memory=AsyncMock(return_value=vector_results)
        )
        self.knowledge_graph = Mock(get_context_block=AsyncMock(return_value=graph_block))
        self._classifier = Mock(classify_binary=AsyncMock(return_value=(True, 0.9)))

    async def _get_local_classifier(self):
        return self._classifier


class TestRecallGateKnowledgeGraph:
    """Recall questions answerable from the knowledge graph skip clarification.

    KG attribute rendering fix: facts stored as entity attributes (emails,
    roles) live only in the graph, so the memory gate must consult it --
    otherwise recall questions bounce to clarification and the agent
    (whose context carries the rendered graph block) never runs.
    """

    @pytest.mark.asyncio
    async def test_graph_facts_count_as_memory_answer(self):
        overlord = _RecallGateOverlord(
            vector_results=[], graph_block="User (person): email: jordan@automaze.io"
        )
        system = UnifiedClarificationSystem(overlord)
        assert await system._is_recall_question_with_answer(
            "What is my email address?", {"user_id": "0"}
        )
        overlord.knowledge_graph.get_context_block.assert_awaited_once_with(
            "0", query_text="What is my email address?"
        )

    @pytest.mark.asyncio
    async def test_empty_graph_does_not_skip_clarification(self):
        overlord = _RecallGateOverlord(vector_results=[], graph_block="")
        system = UnifiedClarificationSystem(overlord)
        assert not await system._is_recall_question_with_answer(
            "What is my email address?", {"user_id": "0"}
        )

    @pytest.mark.asyncio
    async def test_vector_results_short_circuit_before_graph(self):
        overlord = _RecallGateOverlord(
            vector_results=[{"text": "favorite color is blue"}], graph_block=""
        )
        system = UnifiedClarificationSystem(overlord)
        assert await system._is_recall_question_with_answer(
            "What is my favorite color?", {"user_id": "0"}
        )
        overlord.knowledge_graph.get_context_block.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_graph_lookup_failure_is_isolated(self):
        overlord = _RecallGateOverlord(vector_results=[], graph_block="")
        overlord.knowledge_graph.get_context_block.side_effect = RuntimeError("db down")
        system = UnifiedClarificationSystem(overlord)
        assert not await system._is_recall_question_with_answer(
            "What is my email address?", {"user_id": "0"}
        )


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
