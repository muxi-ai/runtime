"""
Test 3A3: Multi-Document Comparison (With Webhook Verification)
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
from utils.webhook_test_utils import (
    setup_webhook_test,
    check_async_response_with_webhook,
)


def get_response(coro):
    """
    Synchronously retrieves the result from an asynchronous chat coroutine.
    """
    return get_response_universal(coro)


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    # Setup webhook testing
    setup_webhook_test()
    
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


def test_pdf_comparison_async(overlord):
    """
    Tests the system's ability to analyze and compare PDF reports with async processing.
    """
    print("\n=== Test 3A3.1: PDF Document Comparison with Async/Webhook ===")
    
    # Request comprehensive comparison analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_compare_async",
            message=(
                "If I gave you two large PDF reports to compare - a Q3 financial report (150 pages) "
                "and a Q4 financial report (175 pages) - please provide a detailed methodology for: "
                "1) Extracting and comparing all financial metrics, "
                "2) Identifying structural changes between documents, "
                "3) Analyzing textual differences in management commentary, "
                "4) Creating a comprehensive change summary with visualizations, "
                "5) Generating actionable insights from the comparison."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['pdf', 'compare', 'financial', 'report', 'difference', 'analysis', 'metrics'],
        min_keywords=4,
        min_length=400,
        test_name="PDF Comparison Analysis"
    )


def test_spreadsheet_data_comparison_async(overlord):
    """
    Tests comparing data between different spreadsheet formats with async processing.
    """
    print("\n=== Test 3A3.2: Spreadsheet Data Comparison with Async/Webhook ===")
    
    # Request detailed comparison methodology
    response = get_response(
        overlord.chat(
            user_id="test_user_data_async",
            message=(
                "How would you perform a comprehensive comparison between: "
                "1) A complex Excel workbook with 10 sheets, formulas, and pivot tables, "
                "2) Multiple CSV files with related sales data, "
                "3) A Google Sheets document with real-time data? "
                "Please detail: data extraction methods, normalization procedures, "
                "validation checks, formula reconciliation, and automated reporting."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['excel', 'csv', 'data', 'spreadsheet', 'compare', 'formula', 'sheet'],
        min_keywords=4,
        min_length=300,
        test_name="Spreadsheet Comparison"
    )


def test_document_format_analysis_async(overlord):
    """
    Tests analyzing differences between document formats with async processing.
    """
    print("\n=== Test 3A3.3: Document Format Analysis with Async/Webhook ===")
    
    # Request comprehensive format analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_formats_async",
            message=(
                "Please provide an exhaustive analysis of the differences between: "
                "1) Word documents (.docx) with tracked changes and comments, "
                "2) PowerPoint presentations with animations and speaker notes, "
                "3) PDF files with forms and digital signatures, "
                "4) HTML documents with embedded media. "
                "Include: technical structure, metadata extraction, content accessibility, "
                "editing capabilities, version control, and best use cases for each."
            ),
            use_async=True,  # Force async
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['word', 'powerpoint', 'pdf', 'format', 'document', 'html', 'structure'],
        min_keywords=5,
        min_length=500,
        test_name="Document Format Analysis"
    )


def test_multi_document_synthesis_async(overlord):
    """
    Tests synthesizing information from multiple documents with async processing.
    """
    print("\n=== Test 3A3.4: Multi-Document Synthesis with Async/Webhook ===")
    
    # First, establish document context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_synthesis",
            message=(
                "I have uploaded 5 critical business documents: "
                "1) Annual financial report showing 20% YoY revenue growth to $50M, "
                "2) Market analysis predicting 30% industry expansion with new competitors, "
                "3) Strategic plan proposing 3 new product launches worth $15M investment, "
                "4) Risk assessment highlighting supply chain and regulatory challenges, "
                "5) HR report showing 15% headcount growth needs. Remember these details."
            ),
            use_async=False,  # Context setup doesn't need async
        )
    )
    
    # Request comprehensive synthesis
    synthesis_response = get_response(
        overlord.chat(
            user_id="test_user_synthesis",
            message=(
                "Based on the 5 documents I mentioned, please create a comprehensive executive "
                "synthesis that: 1) Integrates all key findings, 2) Identifies synergies and conflicts, "
                "3) Provides strategic recommendations, 4) Highlights critical decision points, "
                "5) Creates an action plan with priorities and timelines."
            ),
            use_async=True,  # Force async for synthesis
        )
    )
    
    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        synthesis_response,
        expected_keywords=['financial', 'market', 'strategic', 'risk', 'growth', 'product', 'investment'],
        min_keywords=4,
        min_length=400,
        test_name="Multi-Document Synthesis"
    )


def test_document_memory_retention(overlord):
    """
    Tests memory retention about multiple documents.
    """
    print("\n=== Test 3A3.5: Document Memory Retention ===")
    
    user_id = "test_user_doc_memory"
    
    # Establish context with specific document details
    response1 = get_response(
        overlord.chat(
            user_id=user_id,
            message=(
                "I'm comparing three quarterly reports: Q1 showed $12.5M revenue with 85% margins, "
                "Q2 had $14.2M revenue with 82% margins, and Q3 reached $16.8M revenue with 87% margins. "
                "The reports are 45, 52, and 61 pages respectively."
            ),
            use_async=False,
        )
    )
    
    # Test memory recall
    memory_response = get_response(
        overlord.chat(
            user_id=user_id,
            message="What were the specific revenue figures and margins I mentioned for each quarter?",
            use_async=False,
        )
    )
    
    print(f"Memory Response: {memory_response[:200]}...")
    
    # Verify memory retention
    response_lower = memory_response.lower()
    
    # Check for specific values
    values_found = []
    if "12.5" in memory_response or "twelve point five" in response_lower:
        values_found.append("Q1 $12.5M")
    if "14.2" in memory_response or "fourteen point two" in response_lower:
        values_found.append("Q2 $14.2M")
    if "16.8" in memory_response or "sixteen point eight" in response_lower:
        values_found.append("Q3 $16.8M")
    if "85" in memory_response:
        values_found.append("85% margin")
    if "82" in memory_response:
        values_found.append("82% margin")
    if "87" in memory_response:
        values_found.append("87% margin")
    
    print(f"Values recalled: {values_found}")
    assert len(values_found) >= 3, f"Should recall at least 3 specific values, found: {values_found}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])