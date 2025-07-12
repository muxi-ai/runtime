"""
Test 3C1 with Webhooks: Video Frame Analysis
Tests the system's understanding of analyzing video frames and visual content with webhook support.
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


def test_video_frame_analysis_with_webhooks(overlord):
    """Test understanding of video frame analysis concepts with webhook support"""
    print("\n=== Test 3C1 with Webhooks: Video Frame Analysis ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_video",
            message="If I gave you a presentation video, what visual elements and content could you analyze from the video frames?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['frame', 'visual', 'scene', 'object', 'motion', 'slide', 'presenter', 'content'],
        min_keywords=4,
        min_length=100,
        test_name="Video Frame Analysis"
    )
    
    print(f"Video Frame Analysis Complete - Async: {is_async}")


def test_video_temporal_analysis_with_webhooks(overlord):
    """Test understanding of temporal aspects in video with webhook support"""
    print("\n=== Test 3C1 with Webhooks: Video Temporal Analysis ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_temporal",
            message="How would you analyze changes and transitions over time in a video? What temporal patterns would you look for?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['time', 'change', 'transition', 'movement', 'sequence', 'frame', 'pattern', 'temporal'],
        min_keywords=3,
        min_length=50,
        test_name="Video Temporal Analysis"
    )
    
    print(f"Temporal Analysis Complete - Async: {is_async}")


def test_video_object_detection_with_webhooks(overlord):
    """Test understanding of object detection in video with webhook support"""
    print("\n=== Test 3C1 with Webhooks: Video Object Detection ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_objects",
            message="In a product demo video, what objects and elements would be important to detect and track throughout the frames?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['object', 'detect', 'track', 'product', 'identify', 'element', 'feature', 'demo'],
        min_keywords=4,
        min_length=50,
        test_name="Video Object Detection"
    )
    
    print(f"Object Detection Complete - Async: {is_async}")


def test_video_scene_understanding_with_webhooks(overlord):
    """Test understanding of scene analysis in video with webhook support"""
    print("\n=== Test 3C1 with Webhooks: Video Scene Understanding ===")
    
    # First establish context
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_scenes",
            message="I have a training video that switches between different scenes: instructor talking, screen recordings, and whiteboard explanations."
        )
    )
    
    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['training', 'video', 'scene', 'instructor'],
        min_keywords=1,
        min_length=20,
        test_name="Video Scene Context"
    )
    
    # Then ask about scene analysis
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_scenes",
            message="How would you analyze and categorize the different scenes I mentioned in the video?"
        )
    )
    
    # Check scene analysis - should reference specific scenes
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['instructor', 'screen', 'whiteboard', 'scene', 'analyze', 'categorize'],
        min_keywords=2,
        min_length=50,
        test_name="Video Scene Analysis"
    )
    
    print(f"Scene Understanding Complete - Context Async: {is_async1}, Analysis Async: {is_async2}")


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
            test_video_frame_analysis_with_webhooks(overlord)
            test_video_temporal_analysis_with_webhooks(overlord)
            test_video_object_detection_with_webhooks(overlord)
            test_video_scene_understanding_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())