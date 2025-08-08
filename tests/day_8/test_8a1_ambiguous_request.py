"""
Day 8 Test 8A1: Ambiguous Request Clarification

Tests the system's ability to detect ambiguous requests and ask for clarification.
"""

import asyncio
import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.muxi import Formation   # noqa: E402


@pytest.mark.asyncio
async def test_ambiguous_request_clarification():
    """Test 8A1: System detects ambiguous request and asks for clarification."""

    # Load formation with single agent
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-clarification"
    formation = Formation()
    await formation.load(str(formation_path))

    # Start overlord
    overlord = await formation.start_overlord()

    try:
        # Send ambiguous request
        response = await overlord.chat(
            message="I need help with a scraper",
            user_id="test_user_8a1",
            session_id="session_8a1",
            stream=False  # Disable streaming for testing
        )

        # Check that response asks for clarification
        response_lower = response.content.lower()
        assert any(word in response_lower for word in [
            "what", "which", "clarify", "specific", "tell me more", "kind of"
        ]), f"Expected clarification question, got: {response.content}"

        # Send clarification
        response2 = await overlord.chat(
            message="A Python web scraper for extracting product prices",
            user_id="test_user_8a1",
            session_id="session_8a1",
            stream=False
        )

        # Check that response now addresses the specific request
        response2_lower = response2.content.lower()
        assert any(word in response2_lower for word in [
            "python", "scraper", "price", "extract", "beautifulsoup", "requests", "selenium"
        ]), f"Expected specific help about Python web scraping, got: {response2.content}"

        print("✅ Test 8A1 passed: Ambiguous request clarification works")

    finally:
        pass  # Overlord cleanup handled by formation


@pytest.mark.asyncio
async def test_ambiguous_technical_request():
    """Test 8A1b: System handles ambiguous technical requests."""

    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-clarification"
    formation = Formation()
    await formation.load(str(formation_path))

    # Start overlord
    overlord = await formation.start_overlord()

    try:
        # Send ambiguous technical request
        response = await overlord.chat(
            message="Fix the bug",
            user_id="test_user_8a1b",
            session_id="session_8a1b",
            stream=False
        )

        # Should ask for more details about the bug
        response_lower = response.content.lower()
        assert any(word in response_lower for word in [
            "what", "which", "bug", "describe", "tell me", "more", "specific", "details"
        ]), f"Expected clarification about the bug, got: {response.content}"

        # Provide clarification
        response2 = await overlord.chat(
            message="The login form validation is not checking email format",
            user_id="test_user_8a1b",
            session_id="session_8a1b",
            stream=False
        )

        # Should now provide specific help
        response2_lower = response2.content.lower()
        assert any(word in response2_lower for word in [
            "email", "validation", "login", "format", "regex", "pattern", "check"
        ]), f"Expected specific help about email validation, got: {response2.content}"

        print("✅ Test 8A1b passed: Ambiguous technical request handled")

    finally:
        pass  # Overlord cleanup handled by formation


@pytest.mark.asyncio
async def test_no_clarification_for_clear_request():
    """Test 8A1c: System does not ask for clarification on clear requests."""

    # Load formation
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-clarification"
    formation = Formation()
    await formation.load(str(formation_path))

    # Start overlord
    overlord = await formation.start_overlord()

    try:
        # Send clear, specific request
        response = await overlord.chat(
            message="Write a Python function that calculates the factorial of a number",
            user_id="test_user_8a1c",
            session_id="session_8a1c",
            stream=False
        )

        # Should provide direct answer without clarification
        response_lower = response.content.lower()

        # Should NOT ask for clarification
        clarification_words = ["what", "which", "clarify", "specific", "tell me more"]
        has_clarification = any(word in response_lower for word in clarification_words)

        # Should include actual code or solution
        solution_indicators = ["def", "factorial", "return", "if n", "for", "range"]
        has_solution = any(word in response_lower for word in solution_indicators)

        assert not has_clarification or has_solution, (
            f"Expected direct solution without clarification, got: {response.content}"
        )

        print("✅ Test 8A1c passed: Clear requests don't trigger clarification")

    finally:
        pass  # Overlord cleanup handled by formation


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_ambiguous_request_clarification())
    asyncio.run(test_ambiguous_technical_request())
    asyncio.run(test_no_clarification_for_clear_request())
    print("\n✅ All Test 8A1 tests passed!")
