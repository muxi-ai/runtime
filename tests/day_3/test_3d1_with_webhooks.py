"""
Test 3D1 with Webhooks: Document + Image Cross-Analysis
Tests the system's understanding of analyzing documents and images together with webhook support.
"""

import sys

sys.path.insert(0, ".")
import pytest  # noqa: E402
import asyncio  # noqa: E402
from pathlib import Path  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


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
    # Setup webhook testing environment
    setup_webhook_test()
    
    overlord = await formation.start_overlord()

    yield overlord

    # Cleanup
    await formation.stop_overlord()


def test_report_chart_alignment_with_webhooks(overlord):
    """Test understanding of aligning report text with chart data with webhook support"""
    print("\n=== Test 3D1 with Webhooks: Report-Chart Alignment ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_alignment",
            message=(
                "If I have a financial report PDF and a separate chart image showing quarterly "
                "revenue, how would you verify if the data in both sources align correctly?"
            ),
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['compare', 'verify', 'align', 'data', 'chart', 'report', 'match', 'consistency'],
        min_keywords=4,
        min_length=150,
        test_name="Report-Chart Alignment"
    )

    print(f"Report-Chart Alignment Complete - Async: {is_async}")


def test_document_image_comprehension_with_webhooks(overlord):
    """Test comprehensive understanding across document and image with webhook support"""
    print("\n=== Test 3D1 with Webhooks: Document-Image Comprehension ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_comprehension",
            message=(
                "How would you create a comprehensive analysis combining insights from a research "
                "paper PDF and its accompanying infographic images?"
            ),
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['combine', 'insight', 'research', 'infographic', 'visual', 'text', 'comprehensive', 'analysis'],
        min_keywords=4,
        min_length=100,
        test_name="Document-Image Comprehension"
    )

    print(f"Document-Image Comprehension Complete - Async: {is_async}")


def test_cross_modal_fact_checking_with_webhooks(overlord):
    """Test understanding of fact-checking across modalities with webhook support"""
    print("\n=== Test 3D1 with Webhooks: Cross-Modal Fact Checking ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_fact_check",
            message=(
                "How would you fact-check information by comparing claims in a news article "
                "against data shown in accompanying charts and images?"
            ),
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['fact', 'check', 'compare', 'claim', 'article', 'chart', 'image', 'verify'],
        min_keywords=3,
        min_length=80,
        test_name="Cross-Modal Fact Checking"
    )

    print(f"Cross-Modal Fact Checking Complete - Async: {is_async}")


def test_document_image_memory_with_webhooks(overlord):
    """Test memory retention about document-image relationships with webhook support"""
    print("\n=== Test 3D1 with Webhooks: Document-Image Memory ===")

    # Establish context about document and image work
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_doc_image",
            message="I'm working with a scientific paper that has multiple data tables and corresponding bar charts. The paper discusses climate change trends from 2000-2020."
        )
    )

    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['scientific', 'paper', 'table', 'chart', 'climate'],
        min_keywords=1,
        min_length=20,
        test_name="Document-Image Context"
    )

    # Ask about cross-referencing
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_doc_image",
            message="How should I cross-reference the data I mentioned to ensure consistency?"
        )
    )

    # Check memory - should recall the scientific paper context
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['table', 'chart', 'data', 'scientific', 'climate', 'trend', '2000', '2020'],
        min_keywords=2,
        min_length=30,
        test_name="Document-Image Memory"
    )

    print(f"Document-Image Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


if __name__ == "__main__":
    # Run with async support
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"

        formation = Formation()
        await formation.load(str(formation_path))
        
        # Setup webhook testing environment
        setup_webhook_test()

        overlord = await formation.start_overlord()

        try:
            test_report_chart_alignment_with_webhooks(overlord)
            test_document_image_comprehension_with_webhooks(overlord)
            test_cross_modal_fact_checking_with_webhooks(overlord)
            test_document_image_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()

    asyncio.run(run_test())