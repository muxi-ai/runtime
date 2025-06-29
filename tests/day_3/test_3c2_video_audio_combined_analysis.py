"""
Test 3C2: Video + Audio Combined Analysis
Tests the system's understanding of analyzing both visual and audio content in videos.
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


def test_video_audio_synchronization(overlord):
    """Test understanding of video-audio synchronization analysis"""
    print("\n=== Test 3C2: Video-Audio Synchronization ===")

    response = get_response(
        overlord.chat(
            user_id="test_user_sync",
            message="How would you analyze the relationship between visual and audio content in a video? What would indicate good synchronization?"
        )
    )

    print(f"Synchronization Response: {response}")

    # Verify sync understanding
    assert response, "Should receive a response"
    response_lower = response.lower()
    sync_terms = ['sync', 'audio', 'visual', 'match', 'align', 'sound', 'lip', 'timing']
    matches = sum(1 for term in sync_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss audio-visual sync, found {matches}"


def test_demo_video_combined_analysis(overlord):
    """Test combined analysis of a product demo video"""
    print("\n=== Test 3C2: Demo Video Combined Analysis ===")

    response = get_response(
        overlord.chat(
            user_id="test_user_demo",
            message="If I showed you a software demo video with narration, what would you analyze from both the visual demonstrations and the audio explanations?"
        )
    )

    print(f"Demo Analysis Response: {response}")

    # Verify comprehensive analysis
    assert response, "Should receive a response"
    assert len(response) > 150, "Response should be detailed"

    response_lower = response.lower()
    combined_terms = ['visual', 'audio', 'narration', 'demo', 'screen', 'explain', 'show', 'voice']
    matches = sum(1 for term in combined_terms if term in response_lower)
    assert matches >= 4, f"Response should mention both visual and audio analysis, found {matches}"


def test_video_transcript_alignment(overlord):
    """Test understanding of aligning video content with transcripts"""
    print("\n=== Test 3C2: Video-Transcript Alignment ===")

    response = get_response(
        overlord.chat(
            user_id="test_user_transcript",
            message="How would you match spoken words in a video with specific visual events or slides being shown at the same time?"
        )
    )

    print(f"Transcript Alignment Response: {response}")

    # Verify alignment concepts
    assert response, "Should receive a response"
    response_lower = response.lower()
    alignment_terms = ['match', 'align', 'time', 'transcript', 'visual', 'slide', 'word', 'sync']
    matches = sum(1 for term in alignment_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss transcript alignment, found {matches}"


def test_multimodal_video_memory(overlord):
    """Test memory retention about video with audio content"""
    print("\n=== Test 3C2: Multimodal Video Memory ===")

    # Establish context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_memory",
            message="I'm analyzing a conference presentation video. The speaker discusses AI trends while showing slides with charts and diagrams. The audio quality is clear with minimal background noise."
        )
    )

    # Test memory of combined elements
    response2 = get_response(
        overlord.chat(
            user_id="test_user_memory",
            message="What can you tell me about the video content I'm working with?"
        )
    )

    print(f"Memory Response: {response2}")

    # Should remember both visual and audio aspects
    response_lower = response2.lower()
    visual_recalled = any(term in response_lower for term in ['slide', 'chart', 'diagram', 'visual'])
    audio_recalled = any(term in response_lower for term in ['speaker', 'audio', 'clear', 'noise'])
    content_recalled = any(term in response_lower for term in ['ai', 'trend', 'conference', 'presentation'])

    assert visual_recalled, "Should recall visual elements"
    assert audio_recalled or content_recalled, "Should recall audio or content elements"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"

        formation = Formation()
        formation.load(str(formation_path))
        overlord = formation.start_overlord()

        try:
            test_video_audio_synchronization(overlord)
            test_demo_video_combined_analysis(overlord)
            test_video_transcript_alignment(overlord)
            test_multimodal_video_memory(overlord)
            print("\nAll tests passed!")
        finally:
            formation.stop_overlord()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()
