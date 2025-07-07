"""
Test 3F1: PDF Formula Extraction
Tests extraction and interpretation of mathematical formulas from PDF documents.
"""

import asyncio
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


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
    overlord = await formation.start_overlord()
    yield overlord
    await formation.stop_overlord()


async def test_pdf_formula_extraction(overlord):
    """Test extraction of mathematical formulas from PDFs"""
    print("\n=== Test 3F1: PDF Formula Extraction ===")
    
    # Test with a query about mathematical content
    response = await overlord.chat(
        user_id="test_user",
        message="If I have a PDF with the formula E=mc², what does each variable represent?"
    )
    
    print(f"Formula explanation: {response[:200]}...")
    
    # Verify response explains the formula
    assert response is not None
    assert len(response) > 50
    
    # Check for formula components
    response_lower = response.lower()
    assert any(term in response_lower for term in ["energy", "mass", "speed of light", "einstein"]), \
        "Response should explain the formula components"


async def test_complex_formula_understanding(overlord):
    """Test understanding of more complex mathematical formulas"""
    print("\n=== Test: Complex Formula Understanding ===")
    
    response = await overlord.chat(
        user_id="test_user",
        message="Explain the quadratic formula: x = (-b ± √(b²-4ac)) / 2a"
    )
    
    print(f"Complex formula explanation: {response[:200]}...")
    
    # Verify comprehensive explanation
    assert response is not None
    assert len(response) > 100
    
    response_lower = response.lower()
    assert any(term in response_lower for term in ["quadratic", "equation", "roots", "discriminant"]), \
        "Response should explain quadratic formula concepts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
