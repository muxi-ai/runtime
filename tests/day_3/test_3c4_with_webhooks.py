"""
Test 3C4 with Webhooks: Long Video Async Processing
Tests the system's understanding of processing long videos asynchronously with webhook support.
"""

import pytest
import asyncio
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
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


def test_long_video_challenges_with_webhooks(overlord):
    """Test understanding of long video processing challenges with webhook support"""
    print("\n=== Test 3C4 with Webhooks: Long Video Processing Challenges ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_challenges",
            message=(
                "What are the main challenges when processing a 10-hour video file? "
                "How would you handle memory and processing constraints?"
            ),
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['memory', 'process', 'chunk', 'stream', 'constraint', 'large', 'efficient', 'resource'],
        min_keywords=4,
        min_length=150,
        test_name="Long Video Processing Challenges"
    )

    print(f"Long Video Challenges Complete - Async: {is_async}")


def test_video_streaming_approach_with_webhooks(overlord):
    """Test understanding of streaming video processing with webhook support"""
    print("\n=== Test 3C4 with Webhooks: Video Streaming Approach ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_streaming",
            message=(
                "How would streaming processing work for analyzing a long video? "
                "What are the advantages over loading the entire file?"
            ),
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['stream', 'chunk', 'buffer', 'memory', 'real-time', 'process', 'load', 'efficient'],
        min_keywords=3,
        min_length=50,
        test_name="Video Streaming Approach"
    )

    print(f"Streaming Approach Complete - Async: {is_async}")


def test_video_async_request_with_webhooks(overlord):
    """Test actual async processing for complex video task with webhook support"""
    print("\n=== Test 3C4 with Webhooks: Video Async Request ===")

    # Request complex video processing that should trigger async
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_async_video",
            message=(
                "Please create a comprehensive processing plan for a 8-hour conference video, including: "
                "1) Frame analysis and scene detection, 2) Audio transcription and speaker identification, "
                "3) Slide extraction and OCR, 4) Content summarization by topic, 5) Key moment identification, "
                "6) Quality assessment throughout. Make it detailed and actionable."
            ),
        )
    )

    # Use universal webhook checker - expect this complex request to be async
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['frame', 'analysis', 'transcription', 'speaker', 'slide', 'ocr', 'summary', 'plan'],
        min_keywords=4,
        min_length=300,
        timeout=60.0,  # Give more time for this very complex request
        test_name="Video Async Processing Plan"
    )

    print(f"Async Video Request Complete - Async: {is_async}")


def test_video_processing_memory_with_webhooks(overlord):
    """Test memory retention about video processing discussion with webhook support"""
    print("\n=== Test 3C4 with Webhooks: Video Processing Memory ===")

    # Establish context about video work
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_memory",
            message="I'm working with webinar recordings that are typically 2-3 hours long. They include PowerPoint presentations and Q&A sessions."
        )
    )

    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['webinar', 'recording', 'hour', 'powerpoint'],
        min_keywords=1,
        min_length=20,
        test_name="Video Processing Context"
    )

    # Ask about optimization for the specific context
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_memory",
            message="What's the best approach for processing the video files I mentioned?"
        )
    )

    # Check memory - should recall webinar context
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['webinar', 'hour', 'powerpoint', 'presentation', 'session', '2', '3'],
        min_keywords=1,
        min_length=30,
        test_name="Video Processing Memory"
    )

    print(f"Processing Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


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
            test_long_video_challenges_with_webhooks(overlord)
            test_video_streaming_approach_with_webhooks(overlord)
            test_video_async_request_with_webhooks(overlord)
            test_video_processing_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()

    asyncio.run(run_test())