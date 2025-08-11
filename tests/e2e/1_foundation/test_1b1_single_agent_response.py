"""
Day 1 - Test Group 1B: Basic Agent Communication Tests

Tests basic agent responses and multi-agent routing functionality.
"""
import pytest
import asyncio
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.formation import Formation


class TestBasicCommunication:
    """Test Group 1B: Basic Agent Communication"""

    async def test_1b1_single_agent_response(self):
        """Test 1B1: Single Agent Response"""
        # Load single-agent formation
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-basic"))
        overlord = await formation.start_overlord()

        # Test basic helpfulness query
        response = await overlord.chat("What can you help me with?", user_id="test_user", stream=False)
        assert response is not None
        # Response is MuxiResponse object, extract content
        response_text = response.content if hasattr(response, 'content') else str(response)
        assert len(response_text) > 0

        # Verify response mentions helping (case-insensitive)
        response_lower = response_text.lower()
        assert any(word in response_lower for word in ["help", "assist", "support", "can"])

        # Test another simple interaction
        response2 = await overlord.chat("Tell me a fun fact", user_id="test_user", stream=False)
        assert response2 is not None
        response2_text = response2.content if hasattr(response2, 'content') else str(response2)
        assert len(response2_text) > 0

        await formation.stop_overlord()

    async def test_1b2_agent_routing_validation(self):
        """Test 1B2: Agent Routing Validation"""
        # Load multi-agent formation
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-multi-agent"))
        overlord = await formation.start_overlord()

        # Test 1: Math query should route to appropriate agent
        response = await overlord.chat("Calculate 2+2", stream=False, user_id="test_user")
        assert response is not None
        response_text = response.content if hasattr(response, 'content') else str(response)
        assert "4" in response_text

        # Test 2: Different types of queries for routing
        # Research query
        research_response = await overlord.chat("What are the latest trends in renewable energy?", stream=False, user_id="test_user")
        assert research_response is not None
        research_text = research_response.content if hasattr(research_response, 'content') else str(research_response)
        assert len(research_text) > 50  # Should be substantive

        # General query
        general_response = await overlord.chat("How are you today?", stream=False, user_id="test_user")
        assert general_response is not None

        await formation.stop_overlord()

    async def test_1b_response_consistency(self):
        """Additional Test: Response Consistency"""
        # Ensure agents provide consistent quality responses
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-basic"))
        overlord = await formation.start_overlord()

        # Multiple queries to test consistency
        queries = [
            "Hello",
            "What's the weather like?",
            "Can you help me learn Python?",
            "What's 10 divided by 2?"
        ]

        responses = []
        for query in queries:
            response = await overlord.chat(query, stream=False, user_id="test_user")
            assert response is not None
            response_text = response.content if hasattr(response, 'content') else str(response)
            assert len(response_text) > 0
            assert not response_text.isspace()  # Not just whitespace
            responses.append(response_text)

        # All responses should be unique (not canned responses)
        assert len(set(responses)) == len(responses)

        await formation.stop_overlord()

    async def test_1b_error_handling(self):
        """Additional Test: Basic Error Handling in Communication"""
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-basic"))
        overlord = await formation.start_overlord()

        # Test with empty message
        response = await overlord.chat("", user_id="test_user")
        # Should handle gracefully, possibly ask for clarification
        assert response is not None

        # Test with very long message
        long_message = "Please help me with " + " and ".join([f"task {i}" for i in range(100)])
        response = await overlord.chat(long_message, user_id="test_user")
        assert response is not None

        await formation.stop_overlord()
