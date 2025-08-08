"""
Day 8 Test 8A2: Multi-Agent Clarification

Tests clarification for agent selection when request could be handled by multiple agents.
"""

import asyncio
import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.muxi import Formation   # noqa: E402


@pytest.mark.asyncio
async def test_multi_agent_routing_clarification():
    """Test 8A2: System asks for clarification to route to correct agent."""

    # Load multi-agent formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    formation = Formation()
    await formation.load(str(formation_path))

    # Start overlord
    overlord = await formation.start_overlord()

    try:
        # Send ambiguous request that could go to multiple agents
        response = await overlord.chat(
            message="I need help with the project",
            user_id="test_user_8a2",
            session_id="session_8a2",
            stream=False
        )

        # Should ask for clarification about what kind of help
        response_lower = response.content.lower()

        # Check for clarification about project aspect
        assert any(word in response_lower for word in [
            "what", "which", "aspect", "help", "specific", "area", "part"
        ]), f"Expected clarification about project aspect, got: {response.content}"

        # Clarify we need coding help
        response2 = await overlord.chat(
            message="I need to write Python code for data processing",
            user_id="test_user_8a2",
            session_id="session_8a2",
            stream=False
        )

        # Should route to coder agent and provide coding help
        response2_lower = response2.content.lower()
        assert any(word in response2_lower for word in [
            "python", "code", "data", "processing", "function", "import"
        ]), f"Expected coding help, got: {response2.content}"

        print("✅ Test 8A2 passed: Multi-agent routing clarification works")

    finally:
        pass  # Overlord cleanup handled by formation


@pytest.mark.asyncio
async def test_agent_specialty_clarification():
    """Test 8A2b: System clarifies between similar agent specialties."""

    # Load multi-agent formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    formation = Formation()
    await formation.load(str(formation_path))

    # Start overlord
    overlord = await formation.start_overlord()

    try:
        # Send request that could match multiple specialties
        response = await overlord.chat(
            message="Write something about AI",
            user_id="test_user_8a2b",
            session_id="session_8a2b",
            stream=False
        )

        # Should ask what kind of writing
        response_lower = response.content.lower()

        # Could ask about technical vs general writing
        assert any(phrase in response_lower for phrase in [
            "what kind",
            "what type",
            "technical",
            "blog",
            "article",
            "documentation",
            "code",
            "specific"
        ]), f"Expected clarification about writing type, got: {response.content}"

        # Clarify we want technical documentation
        response2 = await overlord.chat(
            message="Technical documentation about machine learning algorithms",
            user_id="test_user_8a2b",
            session_id="session_8a2b",
            stream=False
        )

        # Should provide technical content
        response2_lower = response2.content.lower()
        assert any(word in response2_lower for word in [
            "algorithm", "machine learning", "ml", "model", "training", "data"
        ]), f"Expected technical ML content, got: {response2.content}"

        print("✅ Test 8A2b passed: Agent specialty clarification works")

    finally:
        pass  # Overlord cleanup handled by formation


@pytest.mark.asyncio
async def test_direct_agent_request_no_clarification():
    """Test 8A2c: Direct agent requests don't need clarification."""

    # Load multi-agent formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    formation = Formation()
    await formation.load(str(formation_path))

    # Start overlord
    overlord = await formation.start_overlord()

    try:
        # Send request directly to a specific agent type
        response = await overlord.chat(
            message="@coder Write a Python function to reverse a string",
            user_id="test_user_8a2c",
            session_id="session_8a2c",
            agent_name="coder",  # Direct agent specification
            stream=False
        )

        # Should provide code directly without clarification
        response_lower = response.content.lower()

        # Should NOT ask for clarification
        clarification_words = ["what kind", "which", "clarify", "tell me more"]
        has_clarification = any(word in response_lower for word in clarification_words)

        # Should include actual code
        code_indicators = ["def", "return", "[::-1]", "reverse", "string"]
        has_code = any(indicator in response_lower for indicator in code_indicators)

        assert not has_clarification or has_code, (
            f"Expected direct code without clarification, got: {response.content}"
        )

        print("✅ Test 8A2c passed: Direct agent requests bypass clarification")

    finally:
        pass  # Overlord cleanup handled by formation


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_multi_agent_routing_clarification())
    asyncio.run(test_agent_specialty_clarification())
    asyncio.run(test_direct_agent_request_no_clarification())
    print("\n✅ All Test 8A2 tests passed!")
