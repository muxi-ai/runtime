"""
Test 3D1: Document + Image Cross-Analysis
Tests the system's understanding of analyzing documents and images together.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation


def get_response(coro):
    """Helper to get response from async chat"""
    result = asyncio.run(coro)
    
    # Handle async generators
    if hasattr(result, "__aiter__"):
        async def collect():
            chunks = []
            async for chunk in result:
                chunks.append(chunk)
            return "".join(chunks)
        return asyncio.run(collect())
    
    return result


@pytest.fixture
def formation():
    """Load multimodal test formation"""
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    formation.load(str(formation_path))
    
    return formation


@pytest.fixture
def overlord(formation):
    """Create overlord instance"""
    overlord = formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    formation.stop_overlord()


def test_report_chart_alignment(overlord):
    """Test understanding of aligning report text with chart data"""
    print("\n=== Test 3D1: Report-Chart Alignment ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_alignment",
            message="If I have a financial report PDF and a separate chart image showing quarterly revenue, how would you verify if the data in both sources align correctly?"
        )
    )
    
    print(f"Report-Chart Alignment Response: {response}")
    
    # Verify cross-reference approach
    assert response, "Should receive a response"
    assert len(response) > 150, "Response should be detailed"
    
    response_lower = response.lower()
    alignment_terms = ['compare', 'verify', 'align', 'data', 'chart', 'report', 'match', 'consistency']
    matches = sum(1 for term in alignment_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss cross-modal alignment, found {matches}"


def test_document_image_comprehension(overlord):
    """Test comprehensive understanding across document and image"""
    print("\n=== Test 3D1: Document-Image Comprehension ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_comprehension",
            message="How would you create a comprehensive analysis combining insights from a research paper PDF and its accompanying infographic images?"
        )
    )
    
    print(f"Comprehension Response: {response}")
    
    # Verify integrated analysis approach
    assert response, "Should receive a response"
    response_lower = response.lower()
    integration_terms = ['combine', 'insight', 'research', 'infographic', 'visual', 'text', 'comprehensive', 'analysis']
    matches = sum(1 for term in integration_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss integrated analysis, found {matches}"


def test_cross_modal_fact_checking(overlord):
    """Test understanding of fact-checking across modalities"""
    print("\n=== Test 3D1: Cross-Modal Fact Checking ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_factcheck",
            message="If a presentation slide image shows '50% growth' but the accompanying document mentions '30% growth', how would you identify and reconcile such discrepancies?"
        )
    )
    
    print(f"Fact Checking Response: {response}")
    
    # Verify discrepancy handling
    assert response, "Should receive a response"
    response_lower = response.lower()
    factcheck_terms = ['discrepancy', 'difference', 'reconcile', 'verify', 'check', 'accurate', 'conflict', 'mismatch']
    matches = sum(1 for term in factcheck_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss discrepancy handling, found {matches}"


def test_document_image_memory(overlord):
    """Test memory retention about document-image relationships"""
    print("\n=== Test 3D1: Document-Image Memory ===")
    
    # Establish context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_cross_memory",
            message="I'm analyzing a technical whitepaper about solar energy that includes efficiency graphs. The document mentions 22% efficiency while the graph shows efficiency trends from 15% to 25% over 10 years."
        )
    )
    
    # Test cross-modal memory
    response2 = get_response(
        overlord.chat(
            user_id="test_user_cross_memory",
            message="Based on what I told you about the document and graph, what's the relationship between the stated efficiency and the visual data?"
        )
    )
    
    print(f"Cross-Modal Memory Response: {response2}")
    
    # Should connect document and image information
    response_lower = response2.lower()
    assert any(term in response_lower for term in ['22%', 'twenty-two', 'efficiency']), \
        "Should remember the document's efficiency claim"
    assert any(term in response_lower for term in ['15', '25', 'trend', 'range', 'years']), \
        "Should remember the graph's data range"
    assert any(term in response_lower for term in ['solar', 'energy', 'whitepaper']), \
        "Should remember the context"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()
        
        try:
            test_report_chart_alignment(overlord)
            test_document_image_comprehension(overlord)
            test_cross_modal_fact_checking(overlord)
            test_document_image_memory(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()