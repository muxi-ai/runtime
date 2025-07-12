"""
Test 3D2 with Webhooks: Audio + Image Fusion Analysis
Tests the system's understanding of analyzing audio and images together with webhook support.
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


def test_presentation_audio_slide_fusion_with_webhooks(overlord):
    """Test understanding of fusing presentation audio with slide images with webhook support"""
    print("\n=== Test 3D2 with Webhooks: Presentation Audio-Slide Fusion ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_fusion",
            message="How would you analyze a presenter's audio narration together with their slide images to create a comprehensive understanding of the presentation?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['audio', 'slide', 'narration', 'visual', 'combine', 'together', 'comprehensive', 'match'],
        min_keywords=4,
        min_length=150,
        test_name="Presentation Audio-Slide Fusion"
    )
    
    print(f"Audio-Slide Fusion Complete - Async: {is_async}")


def test_podcast_image_analysis_with_webhooks(overlord):
    """Test understanding of analyzing podcast audio with show notes images with webhook support"""
    print("\n=== Test 3D2 with Webhooks: Podcast-Image Analysis ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_podcast",
            message="If I have a podcast episode audio file and screenshots of the show notes with key topics and timestamps, how would you integrate these for better understanding?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['podcast', 'audio', 'screenshot', 'timestamp', 'topic', 'integrate', 'notes', 'content'],
        min_keywords=4,
        min_length=80,
        test_name="Podcast-Image Analysis"
    )
    
    print(f"Podcast-Image Analysis Complete - Async: {is_async}")


def test_audio_visual_emotion_analysis_with_webhooks(overlord):
    """Test understanding of emotion analysis across audio and images with webhook support"""
    print("\n=== Test 3D2 with Webhooks: Audio-Visual Emotion Analysis ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_emotion",
            message="How would you analyze emotions by combining voice tone from audio and facial expressions from images of the same person?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['emotion', 'voice', 'tone', 'facial', 'expression', 'feeling', 'mood', 'analyze'],
        min_keywords=4,
        min_length=50,
        test_name="Audio-Visual Emotion Analysis"
    )
    
    print(f"Emotion Analysis Complete - Async: {is_async}")


def test_audio_image_context_memory_with_webhooks(overlord):
    """Test memory retention about audio-image relationships with webhook support"""
    print("\n=== Test 3D2 with Webhooks: Audio-Image Context Memory ===")
    
    # Establish context
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_audio_image",
            message="I'm analyzing a cooking tutorial where the audio explains the recipe steps while images show the ingredients and final dish. The chef mentions using 2 cups of flour, but the ingredient image shows 3 cups."
        )
    )
    
    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['cooking', 'tutorial', 'audio', 'image', 'recipe', 'flour', 'cups'],
        min_keywords=2,
        min_length=20,
        test_name="Audio-Image Context"
    )
    
    # Ask about the discrepancy
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_audio_image",
            message="How should I handle the discrepancy I mentioned between the audio and visual information?"
        )
    )
    
    # Check memory - should recall the flour measurement issue
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['flour', 'cups', '2', '3', 'discrepancy', 'audio', 'visual', 'image'],
        min_keywords=3,
        min_length=30,
        test_name="Audio-Image Memory"
    )
    
    print(f"Audio-Image Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


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
            test_presentation_audio_slide_fusion_with_webhooks(overlord)
            test_podcast_image_analysis_with_webhooks(overlord)
            test_audio_visual_emotion_analysis_with_webhooks(overlord)
            test_audio_image_context_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())