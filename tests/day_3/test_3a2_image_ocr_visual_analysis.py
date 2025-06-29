"""
Test 3A2: Image OCR and Visual Analysis
Tests the system's conceptual understanding of extracting text from images and performing visual analysis.
"""

import sys

sys.path.insert(0, ".")
import pytest  # noqa: E402
import asyncio  # noqa: E402
from pathlib import Path  # noqa: E402

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from tests.day_3.test_utils import get_response_universal, assert_response_valid  # noqa: E402


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


@pytest.fixture
def formation():
    """Load multimodal test formation"""
    # Load the directory, not the file, to enable agent auto-discovery
    formation_path = (
        Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    )

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


def test_chart_ocr_extraction(overlord):
    """Test actual chart data extraction from file"""
    print("\n=== Test 3A2: Chart OCR Extraction with File ===")

    # Read chart description file
    chart_file_path = Path(__file__).parent / "test_files" / "chart_description.txt"
    with open(chart_file_path, "r") as f:
        chart_content = f.read()

    # Test actual file processing
    response = get_response(
        overlord.chat(
            user_id="test_user_ocr",
            message="Extract and summarize the sales data from this chart description.",
            files=[
                {
                    "filename": "chart_description.txt",
                    "content": chart_content,
                    "content_type": "text/plain",
                    "size": len(chart_content),
                }
            ],
        )
    )

    print(f"Chart File Processing Response: {response}")

    # Verify response processes the actual chart data
    is_async = assert_response_valid(
        response, 
        min_length=50, 
        required_words=["chart", "sales", "data", "processed"],
        context="chart OCR extraction"
    )
    
    if is_async:
        print("✓ File is being processed asynchronously")


def test_slide_visual_analysis(overlord):
    """Test conceptual understanding of slide visual analysis"""
    print("\n=== Test 3A2: Slide Visual Analysis ===")

    # Test understanding of slide analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_visual",
            message=(
                "If I showed you a PowerPoint slide with a title, bullet points, and a diagram, "
                "what visual elements and text would you analyze?"
            ),
        )
    )

    print(f"Slide Analysis Response: {response}")

    # Verify response mentions visual elements
    is_async = assert_response_valid(
        response,
        min_length=100,
        required_words=["layout", "text", "design", "element", "content", "visual", "slide", "bullet", "title"],
        context="slide visual analysis"
    )
    
    if is_async:
        print("✓ Slide analysis is being processed asynchronously")


def test_photo_content_description(overlord):
    """Test conceptual understanding of photo content description"""
    print("\n=== Test 3A2: Photo Content Description ===")

    # Test understanding of photo analysis
    response = get_response(
        overlord.chat(
            user_id="test_user_photo",
            message=(
                "If I showed you a photo of a beach scene with people, "
                "what details would you describe about objects, people, and setting?"
            ),
        )
    )

    print(f"Photo Description Response: {response}")

    # Verify detailed description
    assert response, "Should receive a response"
    assert len(response) > 150, "Photo description should be detailed"

    response_lower = response.lower()
    description_terms = [
        "object",
        "people",
        "scene",
        "color",
        "detail",
        "describe",
        "beach",
        "water",
        "sand",
    ]
    matches = sum(1 for term in description_terms if term in response_lower)
    assert matches >= 4, f"Response should include descriptive elements, found {matches}"


def test_image_memory_retention(overlord):
    """Test memory retention about image-related conversations"""
    print("\n=== Test 3A2: Image Memory Retention ===")

    # First, establish context about an image
    response1 = get_response(
        overlord.chat(
            user_id="test_user_memory",
            message=(
                "I'm analyzing our Q4 sales chart that shows growth trends. The bar chart has "
                "months on the X-axis and revenue in millions on the Y-axis."
            ),
        )
    )

    # Then ask about it
    memory_response = get_response(
        overlord.chat(
            user_id="test_user_memory", message="What can you tell me about the chart I mentioned?"
        )
    )

    print(f"Memory Response: {memory_response}")

    # Should remember chart context
    response_lower = memory_response.lower()
    assert any(
        term in response_lower for term in ["q4", "sales", "growth", "chart", "revenue"]
    ), "Should remember the chart context from previous message"


if __name__ == "__main__":
    # Run tests
    from concurrent.futures import ThreadPoolExecutor

    def run_test():
        formation_path = (
            Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        )

        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()

        try:
            test_chart_ocr_extraction(overlord)
            test_slide_visual_analysis(overlord)
            test_photo_content_description(overlord)
            test_image_memory_retention(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()
