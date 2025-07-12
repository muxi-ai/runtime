"""
Test 3C2 with Webhooks: Video + Audio Combined Analysis
Tests the system's understanding of analyzing both visual and audio content in videos with webhook support.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
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


def test_video_audio_synchronization_with_webhooks(overlord):
    """Test understanding of video-audio synchronization analysis with webhook support"""
    print("\n=== Test 3C2 with Webhooks: Video-Audio Synchronization ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_sync",
            message="How would you analyze the relationship between visual and audio content in a video? What would indicate good synchronization?"
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['sync', 'audio', 'visual', 'match', 'align', 'sound', 'lip', 'timing'],
        min_keywords=3,
        min_length=50,
        test_name="Video-Audio Synchronization"
    )

    print(f"Synchronization Analysis Complete - Async: {is_async}")


def test_demo_video_combined_analysis_with_webhooks(overlord):
    """Test combined analysis of a product demo video with webhook support"""
    print("\n=== Test 3C2 with Webhooks: Demo Video Combined Analysis ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_demo",
            message="If I showed you a software demo video with narration, what would you analyze from both the visual demonstrations and the audio explanations?"
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['visual', 'audio', 'narration', 'demo', 'screen', 'explain', 'show', 'voice'],
        min_keywords=4,
        min_length=150,
        test_name="Demo Video Combined Analysis"
    )

    print(f"Demo Analysis Complete - Async: {is_async}")


def test_video_transcript_alignment_with_webhooks(overlord):
    """Test understanding of aligning video content with transcripts with webhook support"""
    print("\n=== Test 3C2 with Webhooks: Video-Transcript Alignment ===")

    response = asyncio.run(
        overlord.chat(
            user_id="test_user_transcript",
            message="How would you match spoken words in a video with specific visual events or slides being shown at the same time?"
        )
    )

    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['match', 'align', 'time', 'transcript', 'visual', 'slide', 'word', 'sync'],
        min_keywords=3,
        min_length=50,
        test_name="Video-Transcript Alignment"
    )

    print(f"Transcript Alignment Complete - Async: {is_async}")


def test_multimodal_video_memory_with_webhooks(overlord):
    """Test memory retention about video with audio content with webhook support"""
    print("\n=== Test 3C2 with Webhooks: Multimodal Video Memory ===")

    # Establish context
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_memory",
            message="I'm analyzing a conference presentation video. The speaker discusses AI trends while showing slides with charts and diagrams. The audio quality is clear with minimal background noise."
        )
    )

    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['conference', 'presentation', 'video', 'speaker'],
        min_keywords=1,
        min_length=20,
        test_name="Video Context Setup"
    )

    # Test memory of combined elements
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_memory",
            message="What can you tell me about the video content I'm working with?"
        )
    )

    # Check memory - should recall visual, audio, and content elements
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['slide', 'chart', 'diagram', 'speaker', 'audio', 'ai', 'trend', 'conference'],
        min_keywords=2,
        min_length=30,
        test_name="Multimodal Video Memory"
    )

    print(f"Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


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
            test_video_audio_synchronization_with_webhooks(overlord)
            test_demo_video_combined_analysis_with_webhooks(overlord)
            test_video_transcript_alignment_with_webhooks(overlord)
            test_multimodal_video_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()

    asyncio.run(run_test())