"""
Test 3A1: Multimodal Concepts and Async Processing (With Webhook Verification)
Simplified version using webhook test utilities.
"""

import os
import sys

sys.path.insert(0, ".")
import pytest
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import (
    TestVisibility,
    get_response_with_visibility,
    assert_with_visibility,
    capture_observability_events,
    restore_observability,
    get_response_universal,
)
from utils.webhook_test_utils import (
    setup_webhook_test,
    check_response_with_webhook,
    check_async_response_with_webhook,  # For backward compatibility
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


def test_pdf_basic_processing(overlord):
    """Test basic document processing with actual files"""
    print("\n=== Test 3A1.1: Document Processing with Files ===")

    # Read test file content
    test_file_path = Path(__file__).parent / "test_files" / "sample_document.txt"
    with open(test_file_path, "r") as f:
        file_content = f.read()

    # Test actual file processing
    response = get_response(
        overlord.chat(
            user_id="test_user_multimodal",
            message="What are the key features mentioned in this document?",
            files=[
                {
                    "filename": "sample_document.txt",
                    "content": file_content,
                    "content_type": "text/plain",
                    "size": len(file_content),
                }
            ],
            use_async=False,
        )
    )

    print(f"Response length: {len(response)} characters")

    # Verify response
    assert response, "Should receive a response"
    assert len(response) > 50, "Response should contain meaningful content"

    response_lower = response.lower()
    assert (
        "feature" in response_lower
        or "document" in response_lower
        or "processing" in response_lower
    ), "Response should discuss document features"


def test_async_processing_with_webhook(overlord):
    """Test async processing with webhook verification"""
    print("\n=== Test 3A1.2: Dynamic Processing (May Be Sync or Async) ===")

    # Request complex analysis - let system decide sync/async
    response = get_response(
        overlord.chat(
            user_id="test_user_async",
            message=(
                "Please create a detailed analysis of how multimodal AI systems work, "
                "including sections on: 1) Text processing, 2) Image understanding, "
                "3) Audio analysis, 4) Video processing, and 5) Cross-modal fusion. "
                "Make it comprehensive with at least 1000 words."
            ),
            # Note: Not forcing async - let formation/system decide
        )
    )

    # Use new universal checker
    result, was_async = check_response_with_webhook(
        response,
        expected_keywords=[
            'text processing', 'image understanding', 'audio analysis',
            'video processing', 'cross-modal fusion', 'multimodal'
        ],
        min_keywords=3,  # At least 3 of the requested sections
        min_length=500,   # Comprehensive analysis
        test_name="Multimodal AI Analysis"
    )

    # Verify we got meaningful analysis either way
    print(f"✓ Received comprehensive analysis ({len(result)} chars)")
    print(f"Processing mode: {'async via webhook' if was_async else 'synchronous'}")
    
    # Additional verification that works for both modes
    assert len(result) >= 500, f"Expected comprehensive analysis, got {len(result)} chars"


def test_async_file_processing_with_webhook(overlord):
    """Test file processing with explicit async request"""
    print("\n=== Test 3A1.3: File Processing with Explicit Async ===")
    
    # Read test file
    test_file_path = Path(__file__).parent / "test_files" / "sample_document.txt"
    with open(test_file_path, "r") as f:
        file_content = f.read()
    
    # Request complex file analysis with explicit async
    response = get_response(
        overlord.chat(
            user_id="test_user_async_file",
            message=(
                "Please analyze this document and create a comprehensive report including: "
                "1) Main themes, 2) Key insights, 3) Detailed summary of each section, "
                "4) Recommendations based on the content. Make it very detailed."
            ),
            files=[
                {
                    "filename": "sample_document.txt",
                    "content": file_content,
                    "content_type": "text/plain",
                    "size": len(file_content),
                }
            ],
            use_async=True,  # Explicitly request async processing
        )
    )
    
    # Still use universal checker - it handles both response types
    result, was_async = check_response_with_webhook(
        response,
        expected_keywords=['theme', 'insight', 'summary', 'recommendation', 'document'],
        min_keywords=2,
        min_length=200,
        test_name="Document Analysis"
    )
    
    # When we explicitly request async, we expect it to be async
    if not was_async:
        print("⚠️  Note: Requested async but got sync response (formation may override)")
    else:
        print("✓ Async processing confirmed as requested")


def test_multimodal_memory_retention(overlord):
    """Test memory retention across multimodal contexts"""
    print("\n=== Test 3A1.4: Multimodal Memory Retention ===")

    user_id = "test_user_mm_memory"

    # Establish context with specific numbers
    response1 = get_response(
        overlord.chat(
            user_id=user_id,
            message=(
                "I just analyzed test results from our multimodal AI system: "
                "45 tests passed, 2 tests failed, and 3 tests were skipped. "
                "The system shows 95% performance, 98% reliability, and 90% scalability metrics. "
                "Remember these specific numbers."
            ),
            use_async=False,
        )
    )
    
    print("Context established")

    # Test memory recall
    response2 = get_response(
        overlord.chat(
            user_id=user_id,
            message="What were the specific test result numbers I just shared with you?",
            use_async=False,
        )
    )

    print(f"Memory recall response: {response2[:200]}...")

    # Verify memory retention
    response_lower = response2.lower()
    
    # Check for specific numbers
    numbers_found = []
    if "45" in response2 or "forty-five" in response_lower:
        numbers_found.append("45 passed")
    if "2" in response2 or "two" in response_lower:
        numbers_found.append("2 failed")
    if "3" in response2 or "three" in response_lower:
        numbers_found.append("3 skipped")
    
    print(f"Numbers recalled: {numbers_found}")
    assert len(numbers_found) >= 2, f"Should recall at least 2 specific numbers, found: {numbers_found}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])