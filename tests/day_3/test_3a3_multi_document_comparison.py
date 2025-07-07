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
from tests.day_3.test_utils import get_response_universal, assert_response_valid


def get_response(coro):
    """
    Synchronously retrieves the result from an asynchronous chat coroutine.
    
    Parameters:
        coro: An awaitable representing the asynchronous chat operation.
    
    Returns:
        The result produced by the asynchronous chat coroutine.
    """
    return get_response_universal(coro)


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    await formation.load(str(formation_path))
    
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await formation.stop_overlord()


def test_pdf_comparison(overlord):
    """
    Tests the system's ability to conceptually analyze and compare two PDF reports.
    
    Sends a prompt about comparing Q3 and Q4 PDF reports, then validates that the response demonstrates understanding of document comparison by checking for sufficient length and the presence of key comparison concepts.
    """
    print("\n=== Test 3A3: PDF Document Comparison ===")
    
    # Test understanding of document comparison
    response = get_response(
        overlord.chat(
            user_id="test_user_compare",
            message="If I gave you two PDF reports to compare - one from Q3 and one from Q4 - what aspects would you analyze to identify differences and similarities?",
            use_async=False  # Force sync mode for testing
        )
    )
    
    print(f"PDF Comparison Response: {response}")
    
    # Verify comprehensive comparison approach
    is_async = assert_response_valid(
        response, 
        min_length=150,
        required_words=['compare', 'difference', 'similar', 'change', 'analyze', 'content', 'structure', 'data'],
        context="PDF comparison"
    )
    
    if not is_async:
        # Only check for multiple terms if we got a sync response
        response_lower = response.lower()
        comparison_terms = ['compare', 'difference', 'similar', 'change', 'analyze', 'content', 'structure', 'data']
        matches = sum(1 for term in comparison_terms if term in response_lower)
        assert matches >= 4, f"Response should mention comparison concepts, found {matches}"


def test_spreadsheet_data_comparison(overlord):
    """
    Validates the system's ability to conceptually compare data between Excel spreadsheets and CSV files.
    
    Sends a prompt about comparing sales figures in different spreadsheet formats, prints the response, and checks for sufficient length and presence of key data comparison terms. If the response is synchronous, asserts that multiple relevant concepts are mentioned.
    """
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
    is_async = assert_response_valid(
        response,
        min_length=50,
        required_words=['data', 'format', 'value', 'column', 'row', 'compare', 'excel', 'csv'],
        context="spreadsheet comparison"
    )
    
    if not is_async:
        # Only check for multiple terms if we got a sync response
        response_lower = response.lower()
        data_terms = ['data', 'format', 'value', 'column', 'row', 'compare', 'excel', 'csv']
        matches = sum(1 for term in data_terms if term in response_lower)
        assert matches >= 4, f"Response should mention data comparison concepts, found {matches}"


def test_document_format_differences(overlord):
    """
    Tests the system's ability to explain key differences in analyzing Word documents, PowerPoint presentations, and PDF files.
    
    Sends a prompt about document format differences to the overlord, validates the response for sufficient length and presence of relevant terms, and asserts that multiple format-specific concepts are addressed in synchronous responses.
    """
    print("\n=== Test 3A3: Document Format Differences ===")
    
    # Test understanding of format differences
    response = get_response(
        overlord.chat(
            user_id="test_user_formats",
            message="What are the key differences between analyzing a Word document, a PowerPoint presentation, and a PDF file? What unique information can each format provide?",
            use_async=False  # Force sync mode for testing
        )
    )
    
    print(f"Format Differences Response: {response}")
    
    # Verify format understanding
    is_async = assert_response_valid(
        response,
        min_length=200,
        required_words=['word', 'powerpoint', 'pdf', 'format', 'document', 'presentation', 'edit', 'layout'],
        context="format differences"
    )
    
    if not is_async:
        # Only check for multiple terms if we got a sync response
        response_lower = response.lower()
        format_terms = ['word', 'powerpoint', 'pdf', 'format', 'document', 'presentation', 'edit', 'layout']
        matches = sum(1 for term in format_terms if term in response_lower)
        assert matches >= 5, f"Response should mention multiple formats, found {matches}"


def test_multi_document_synthesis(overlord):
    """
    Tests whether the system can synthesize and integrate information from multiple described documents into a coherent business narrative.
    
    Sends descriptions of a financial report, market analysis, and strategic plan to the overlord, then requests an overall synthesis. Asserts that the response references key aspects from each document type.
    """
    print("\n=== Test 3A3: Multi-Document Synthesis ===")
    
    # First, describe multiple documents
    response1 = get_response(
        overlord.chat(
            user_id="test_user_synthesis",
            message="I have three documents: 1) A financial report showing 20% revenue growth, 2) A market analysis predicting industry expansion, 3) A strategic plan proposing new product launches.",
            use_async=False  # Force sync mode for testing
        )
    )
    
    # Then ask for synthesis
    synthesis_response = get_response(
        overlord.chat(
            user_id="test_user_synthesis",
            message="Based on the three documents I mentioned, what overall business story do they tell together?",
            use_async=False  # Force sync mode for testing
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
    
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        try:
            test_pdf_comparison(overlord)
            test_spreadsheet_data_comparison(overlord)
            test_document_format_differences(overlord)
            test_multi_document_synthesis(overlord)
            print("\nAll tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())
