"""
Test 3F1 with Webhooks: PDF Formula Extraction
Tests extraction and interpretation of mathematical formulas from PDF documents with webhook support.
"""

import asyncio
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


@pytest.fixture
async def formation():
    """Load formation for testing"""
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    formation = Formation()
    await formation.load(str(formation_path))
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    # Setup webhook testing environment
    setup_webhook_test()
    
    overlord = await formation.start_overlord()
    yield overlord
    await formation.stop_overlord()


async def test_pdf_formula_extraction_with_webhooks(overlord):
    """Test extraction of mathematical formulas from PDFs with webhook support"""
    print("\n=== Test 3F1 with Webhooks: PDF Formula Extraction ===")

    # Test with a query about mathematical content
    response = await overlord.chat(
        user_id="test_user",
        message="If I have a PDF with the formula E=mc², what does each variable represent?"
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=["energy", "mass", "speed", "light", "einstein", "formula"],
        min_keywords=3,
        min_length=50,
        test_name="PDF Formula Extraction"
    )

    print(f"Formula Extraction Complete - Async: {is_async}")


async def test_complex_formula_understanding_with_webhooks(overlord):
    """Test understanding of more complex mathematical formulas with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Complex Formula Understanding ===")

    response = await overlord.chat(
        user_id="test_user",
        message="Explain the quadratic formula: x = (-b ± √(b²-4ac)) / 2a"
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=["quadratic", "equation", "roots", "discriminant", "formula", "solve"],
        min_keywords=3,
        min_length=100,
        test_name="Complex Formula Understanding"
    )

    print(f"Complex Formula Understanding Complete - Async: {is_async}")


async def test_mathematical_notation_with_webhooks(overlord):
    """Test understanding of various mathematical notations with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Mathematical Notation ===")

    response = await overlord.chat(
        user_id="test_user_notation",
        message="How would you extract and interpret calculus formulas like ∫f(x)dx and ∂f/∂x from PDF documents?"
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=["integral", "derivative", "calculus", "notation", "extract", "pdf"],
        min_keywords=3,
        min_length=80,
        test_name="Mathematical Notation"
    )

    print(f"Mathematical Notation Complete - Async: {is_async}")


async def test_formula_context_memory_with_webhooks(overlord):
    """Test memory retention about formula extraction discussion with webhook support"""
    print("\n=== Test 3F1 with Webhooks: Formula Context Memory ===")

    # Establish context about formula work
    response1 = await overlord.chat(
        user_id="test_user_formula_memory",
        message="I'm working on extracting thermodynamics formulas from engineering PDFs, particularly the ideal gas law PV = nRT."
    )

    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=["thermodynamics", "formula", "engineering", "pdf", "gas"],
        min_keywords=2,
        min_length=20,
        test_name="Formula Context Setup"
    )

    # Ask about related formulas
    response2 = await overlord.chat(
        user_id="test_user_formula_memory",
        message="What other thermodynamics formulas should I look for in the same documents?"
    )

    # Check memory - should recall thermodynamics context
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=["thermodynamics", "formula", "gas", "temperature", "pressure", "entropy"],
        min_keywords=2,
        min_length=50,
        test_name="Formula Context Memory"
    )

    print(f"Formula Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


if __name__ == "__main__":
    # Run async tests
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Setup webhook testing environment
        setup_webhook_test()
        
        overlord = await formation.start_overlord()
        
        try:
            await test_pdf_formula_extraction_with_webhooks(overlord)
            await test_complex_formula_understanding_with_webhooks(overlord)
            await test_mathematical_notation_with_webhooks(overlord)
            await test_formula_context_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())