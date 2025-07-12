"""
Test 3A2: Image OCR and Visual Analysis (With Webhook Verification)
Tests the system's conceptual understanding of extracting text from images and performing visual analysis.
"""

import sys
sys.path.insert(0, ".")

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
    """Helper to get response from async chat"""
    return get_response_universal(coro)


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    # Setup webhook testing
    setup_webhook_test()
    
    formation_path = (
        Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    )

    formation = Formation()
    await formation.load(str(formation_path))

    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    overlord = await formation.start_overlord()
    yield overlord
    await formation.stop_overlord()


def test_chart_ocr_extraction_async(overlord):
    """Test actual chart data extraction from file with async processing"""
    print("\n=== Test 3A2.1: Chart OCR Extraction with Async/Webhook ===")

    # Read chart description file
    chart_file_path = Path(__file__).parent / "test_files" / "chart_description.txt"
    with open(chart_file_path, "r") as f:
        chart_content = f.read()

    # Request complex analysis to trigger async
    response = get_response(
        overlord.chat(
            user_id="test_user_ocr_async",
            message=(
                "Extract and analyze the sales data from this chart. Please provide: "
                "1) Complete data extraction with all values, "
                "2) Trend analysis across all periods, "
                "3) Statistical insights and patterns, "
                "4) Detailed recommendations based on the data."
            ),
            files=[
                {
                    "filename": "chart_description.txt",
                    "content": chart_content,
                    "content_type": "text/plain",
                    "size": len(chart_content),
                }
            ],
            use_async=True,  # Force async
        )
    )

    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['chart', 'sales', 'data', 'trend', 'analysis'],
        min_keywords=3,
        min_length=200,
        test_name="Chart OCR Analysis"
    )


def test_slide_visual_analysis_async(overlord):
    """Test conceptual understanding of slide visual analysis with async"""
    print("\n=== Test 3A2.2: Slide Visual Analysis with Async/Webhook ===")

    # Request comprehensive analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_visual_async",
            message=(
                "If I showed you a PowerPoint presentation with 10 slides, each containing "
                "titles, bullet points, diagrams, and charts, please describe in detail: "
                "1) What visual elements you would analyze on each slide type, "
                "2) How you would extract and organize the text content, "
                "3) Methods for understanding visual hierarchy and relationships, "
                "4) Approach to creating a comprehensive summary of the entire presentation."
            ),
            use_async=True,  # Force async
        )
    )

    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['slide', 'visual', 'text', 'bullet', 'title', 'diagram', 'chart', 'analysis'],
        min_keywords=4,
        min_length=300,
        test_name="Slide Visual Analysis"
    )


def test_photo_content_description_async(overlord):
    """Test photo content description with async processing"""
    print("\n=== Test 3A2.3: Photo Content Description with Async/Webhook ===")

    # Request detailed analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_photo_async",
            message=(
                "If I showed you a complex photo of a crowded beach scene during sunset with "
                "multiple activities happening, please provide an exhaustive description including: "
                "1) All visible people and their activities, "
                "2) Objects and structures in the scene, "
                "3) Environmental details like weather and lighting, "
                "4) Colors, textures, and visual composition, "
                "5) Emotional tone and atmosphere of the scene."
            ),
            use_async=True,  # Force async
        )
    )

    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['beach', 'people', 'scene', 'color', 'object', 'sunset', 'activity'],
        min_keywords=4,
        min_length=400,
        test_name="Photo Description"
    )


def test_multi_image_comparison_async(overlord):
    """Test comparing multiple images with async processing"""
    print("\n=== Test 3A2.4: Multi-Image Comparison with Async/Webhook ===")

    # Request complex comparison
    response = get_response(
        overlord.chat(
            user_id="test_user_comparison_async",
            message=(
                "If I showed you 5 different product images from our catalog, please explain "
                "how you would: 1) Extract text from each product label, "
                "2) Identify and compare visual features, "
                "3) Analyze color schemes and design patterns, "
                "4) Create a detailed comparison matrix, "
                "5) Generate recommendations for visual consistency."
            ),
            use_async=True,  # Force async
        )
    )

    # Check async response and webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['image', 'product', 'compare', 'visual', 'text', 'extract', 'analysis'],
        min_keywords=4,
        min_length=300,
        test_name="Multi-Image Comparison"
    )


def test_image_memory_retention(overlord):
    """Test memory retention about image-related conversations"""
    print("\n=== Test 3A2.5: Image Memory Retention ===")

    user_id = "test_user_memory"

    # Establish context
    response1 = get_response(
        overlord.chat(
            user_id=user_id,
            message=(
                "I'm analyzing our Q4 sales chart that shows growth trends. The bar chart has "
                "months on the X-axis and revenue in millions on the Y-axis. October showed $2.5M, "
                "November $3.1M, and December reached $4.2M."
            ),
            use_async=False,
        )
    )

    # Test memory recall
    memory_response = get_response(
        overlord.chat(
            user_id=user_id, 
            message="What specific revenue figures did I mention for the Q4 chart?",
            use_async=False,
        )
    )

    print(f"Memory Response: {memory_response[:200]}...")

    # Verify memory retention
    response_lower = memory_response.lower()
    
    # Check for specific values
    values_found = []
    if "2.5" in memory_response or "two point five" in response_lower:
        values_found.append("October $2.5M")
    if "3.1" in memory_response or "three point one" in response_lower:
        values_found.append("November $3.1M")
    if "4.2" in memory_response or "four point two" in response_lower:
        values_found.append("December $4.2M")
    
    print(f"Values recalled: {values_found}")
    assert len(values_found) >= 2, f"Should recall at least 2 revenue figures, found: {values_found}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])