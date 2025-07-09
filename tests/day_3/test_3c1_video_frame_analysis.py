"""
Test 3C1: Video Frame Analysis
Tests the system's understanding of analyzing video frames and visual content.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from src.muxi.runtime.formation.formation import Formation
from tests.day_3.test_utils import get_response_universal


def get_response(coro):
    """Helper to get response from async chat"""
    return get_response_universal(coro)


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
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await formation.stop_overlord()


def test_video_frame_analysis(overlord):
    """Test understanding of video frame analysis concepts"""
    print("\n=== Test 3C1: Video Frame Analysis ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_video",
            message="If I gave you a presentation video, what visual elements and content could you analyze from the video frames?"
        )
    )
    
    print(f"Video Frame Analysis Response: {response}")
    
    # Verify comprehensive analysis approach
    assert response, "Should receive a response"
    assert len(response) > 100, "Response should be detailed"
    
    response_lower = response.lower()
    video_terms = ['frame', 'visual', 'scene', 'object', 'motion', 'slide', 'presenter', 'content']
    matches = sum(1 for term in video_terms if term in response_lower)
    assert matches >= 4, f"Response should mention video analysis concepts, found {matches}"


def test_video_temporal_analysis(overlord):
    """Test understanding of temporal aspects in video"""
    print("\n=== Test 3C1: Video Temporal Analysis ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_temporal",
            message="How would you analyze changes and transitions over time in a video? What temporal patterns would you look for?"
        )
    )
    
    print(f"Temporal Analysis Response: {response}")
    
    # Verify temporal understanding
    assert response, "Should receive a response"
    response_lower = response.lower()
    temporal_terms = ['time', 'change', 'transition', 'movement', 'sequence', 'frame', 'pattern', 'temporal']
    matches = sum(1 for term in temporal_terms if term in response_lower)
    assert matches >= 3, f"Response should discuss temporal analysis, found {matches}"


def test_video_object_detection(overlord):
    """Test understanding of object detection in video"""
    print("\n=== Test 3C1: Video Object Detection ===")
    
    response = get_response(
        overlord.chat(
            user_id="test_user_objects",
            message="In a product demo video, what objects and elements would be important to detect and track throughout the frames?"
        )
    )
    
    print(f"Object Detection Response: {response}")
    
    # Verify object detection concepts
    assert response, "Should receive a response"
    response_lower = response.lower()
    detection_terms = ['object', 'detect', 'track', 'product', 'identify', 'element', 'feature', 'demo']
    matches = sum(1 for term in detection_terms if term in response_lower)
    assert matches >= 4, f"Response should mention object detection concepts, found {matches}"


def test_video_scene_understanding(overlord):
    """Test understanding of scene analysis in video"""
    print("\n=== Test 3C1: Video Scene Understanding ===")
    
    # First establish context
    response1 = get_response(
        overlord.chat(
            user_id="test_user_scenes",
            message="I have a training video that switches between different scenes: instructor talking, screen recordings, and whiteboard explanations."
        )
    )
    
    # Then ask about scene analysis
    response2 = get_response(
        overlord.chat(
            user_id="test_user_scenes",
            message="How would you analyze and categorize the different scenes I mentioned in the video?"
        )
    )
    
    print(f"Scene Understanding Response: {response2}")
    
    # Should reference the specific scenes mentioned
    response_lower = response2.lower()
    assert any(term in response_lower for term in ['instructor', 'screen', 'whiteboard', 'scene']), \
        "Should reference the specific scenes from context"


if __name__ == "__main__":
    # Run with ThreadPoolExecutor to avoid event loop issues
    async def run_test():
        formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
        
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        try:
            test_video_frame_analysis(overlord)
            test_video_temporal_analysis(overlord)
            test_video_object_detection(overlord)
            test_video_scene_understanding(overlord)
            print("\nAll tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())