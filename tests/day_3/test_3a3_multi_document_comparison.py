"""
Test 3A3: Multi-Document Comparison
Tests the system's conceptual understanding of comparing and analyzing multiple documents.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path

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


def test_pdf_comparison(overlord):
    """Test conceptual understanding of PDF document comparison"""
    print("\n=== Test 3A3: PDF Document Comparison ===")
    
    # Test understanding of document comparison
    response = get_response(
        overlord.chat(
            user_id="test_user_compare",
            message="If I gave you two PDF reports to compare - one from Q3 and one from Q4 - what aspects would you analyze to identify differences and similarities?"
        )
    )
    
    print(f"PDF Comparison Response: {response}")
    
    # Verify comprehensive comparison approach
    assert response, "Should receive a response"
    assert len(response) > 150, "Response should be detailed"
    
    response_lower = response.lower()
    comparison_terms = ['compare', 'difference', 'similar', 'change', 'analyze', 'content', 'structure', 'data']
    matches = sum(1 for term in comparison_terms if term in response_lower)
    assert matches >= 4, f"Response should mention comparison concepts, found {matches}"


def test_spreadsheet_data_comparison(overlord):
    """Test conceptual understanding of spreadsheet data comparison"""
    print("\n=== Test 3A3: Spreadsheet Data Comparison ===")
    
    # Test understanding of data comparison
    response = get_response(
        overlord.chat(
            user_id="test_user_data",
            message="How would you compare data between an Excel spreadsheet and a CSV file containing sales figures? What would you look for?"
        )
    )
    
    print(f"Spreadsheet Comparison Response: {response}")
    
    # Verify data comparison understanding
    assert response, "Should receive a response"
    response_lower = response.lower()
    data_terms = ['data', 'format', 'value', 'column', 'row', 'compare', 'excel', 'csv']
    matches = sum(1 for term in data_terms if term in response_lower)
    assert matches >= 4, f"Response should mention data comparison concepts, found {matches}"


def test_document_format_differences(overlord):
    """Test understanding of different document format capabilities"""
    print("\n=== Test 3A3: Document Format Differences ===")
    
    # Test understanding of format differences
    response = get_response(
        overlord.chat(
            user_id="test_user_formats",
            message="What are the key differences between analyzing a Word document, a PowerPoint presentation, and a PDF file? What unique information can each format provide?"
        )
    )
    
    print(f"Format Differences Response: {response}")
    
    # Verify format understanding
    assert response, "Should receive a response"
    assert len(response) > 200, "Response should explain format differences"
    
    response_lower = response.lower()
    format_terms = ['word', 'powerpoint', 'pdf', 'format', 'document', 'presentation', 'edit', 'layout']
    matches = sum(1 for term in format_terms if term in response_lower)
    assert matches >= 5, f"Response should mention multiple formats, found {matches}"


def test_multi_document_synthesis(overlord):
    """Test ability to synthesize information from multiple document descriptions"""
    print("\n=== Test 3A3: Multi-Document Synthesis ===")
    
    # First, describe multiple documents
    response1 = get_response(
        overlord.chat(
            user_id="test_user_synthesis",
            message="I have three documents: 1) A financial report showing 20% revenue growth, 2) A market analysis predicting industry expansion, 3) A strategic plan proposing new product launches."
        )
    )
    
    # Then ask for synthesis
    synthesis_response = get_response(
        overlord.chat(
            user_id="test_user_synthesis",
            message="Based on the three documents I mentioned, what overall business story do they tell together?"
        )
    )
    
    print(f"Synthesis Response: {synthesis_response}")
    
    # Should synthesize information from all three documents
    response_lower = synthesis_response.lower()
    assert any(term in response_lower for term in ['growth', 'revenue', 'financial']), \
        "Should reference the financial report"
    assert any(term in response_lower for term in ['market', 'industry', 'expansion']), \
        "Should reference the market analysis"
    assert any(term in response_lower for term in ['product', 'launch', 'strategic']), \
        "Should reference the strategic plan"


if __name__ == "__main__":
    # Run tests
    from concurrent.futures import ThreadPoolExecutor
    
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()
        
        try:
            test_pdf_comparison(overlord)
            test_spreadsheet_data_comparison(overlord)
            test_document_format_differences(overlord)
            test_multi_document_synthesis(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()