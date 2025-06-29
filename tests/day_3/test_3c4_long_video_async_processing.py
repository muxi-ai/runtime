"""
Test 3C4: Long Video Async Processing
Tests the system's understanding of processing long videos asynchronously.
"""

import pytest
import asyncio
import time
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


def test_long_video_challenges(overlord):
    """Test understanding of long video processing challenges"""
    print("\n=== Test 3C4: Long Video Processing Challenges ===")

    response = get_response(
        overlord.chat(
            user_id="test_user_challenges",
            message=(
                "What are the main challenges when processing a 10-hour video file? "
                "How would you handle memory and processing constraints?"
            ),
        )
    )

    print(f"Long Video Challenges Response: {response}")

    # Verify comprehensive understanding
    assert response, "Should receive a response"
    assert len(response) > 150, "Response should be detailed"

    response_lower = response.lower()
    challenge_terms = ['memory', 'process', 'chunk', 'stream', 'constraint', 'large', 'efficient', 'resource']
    matches = sum(1 for term in challenge_terms if term in response_lower)
    assert matches >= 4, f"Response should discuss processing challenges, found {matches}"


def test_video_streaming_approach(overlord):
    """Test understanding of streaming video processing"""
    print("\n=== Test 3C4: Video Streaming Approach ===")

    response = get_response(
        overlord.chat(
            user_id="test_user_streaming",
            message=(
                "How would streaming processing work for analyzing a long video? "
                "What are the advantages over loading the entire file?"
            ),
        )
    )

    print(f"Streaming Approach Response: {response}")

    # Verify streaming concepts
    assert response, "Should receive a response"
    response_lower = response.lower()
    streaming_terms = ['stream', 'chunk', 'buffer', 'memory', 'real-time', 'process', 'load', 'efficient']
    matches = sum(1 for term in streaming_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss streaming concepts, found {matches}"


def test_async_video_processing_request(overlord):
    """Test async processing for complex video analysis request"""
    print("\n=== Test 3C4: Async Video Processing Request ===")

    start_time = time.time()

    # Request comprehensive video analysis that should trigger async
    response = get_response(
        overlord.chat(
            user_id="test_user_async_video",
            message=(
                "Please create a comprehensive analysis plan for a 3-hour documentary video, "
                "including: 1) Scene detection and segmentation, 2) Speaker identification and "
                "tracking, 3) Visual element cataloging, 4) Audio transcription with timestamps, "
                "5) Thematic analysis across the entire video. Make this extremely detailed."
            ),
            use_async=True,  # Force async processing
        )
    )

    duration = time.time() - start_time
    print(f"Response received in {duration:.2f} seconds")
    print(f"Async Video Response: {response}")

    # Check if we got async response
    if isinstance(response, dict) and 'request_id' in response:
        print(f"✓ Received async response with request ID: {response['request_id']}")
        assert response['status'] == 'processing', "Status should be 'processing'"
        assert duration < 10, "Async response should return quickly"
    else:
        # Synchronous response is also valid
        print("Note: Response was synchronous")
        assert len(response) > 400, "Should receive very detailed analysis plan"


def test_video_processing_memory(overlord):
    """Test memory about video processing requirements"""
    print("\n=== Test 3C4: Video Processing Memory ===")

    # Establish context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_video_memory",
            message=(
                "I have a 4K resolution video that's 6 hours long. "
                "It's a recording of a live coding workshop with multiple screen shares and presenter views."
            ),
        )
    )

    # Ask about processing approach
    response2 = get_response(
        overlord.chat(
            user_id="test_user_video_memory",
            message=(
                "Given the video specifications I mentioned, what processing approach would you recommend?"
            ),
        )
    )

    print(f"Processing Recommendation Response: {response2}")

    # Should remember video details
    response_lower = response2.lower()
    assert any(term in response_lower for term in ["4k", "resolution", "high", "quality"]), \
        "Should remember the 4K resolution"
    assert any(term in response_lower for term in ["hour", "long", "duration", "6"]), \
        "Should remember the 6-hour duration"
    assert any(term in response_lower for term in ["coding", "workshop", "screen", "presenter"]), \
        "Should remember the content type"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = (
            Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        )

        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()

        try:
            test_long_video_challenges(overlord)
            test_video_streaming_approach(overlord)
            test_async_video_processing_request(overlord)
            test_video_processing_memory(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()
