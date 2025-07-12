"""
Test 3C3 with Webhooks: Video Summarization
Tests the system's understanding of creating summaries from video content with webhook support.
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


def test_presentation_video_summary_with_webhooks(overlord):
    """Test understanding of presentation video summarization with webhook support"""
    print("\n=== Test 3C3 with Webhooks: Presentation Video Summary ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_summary",
            message="What key elements would you include in a summary of a technical presentation video? How would you structure it?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['summary', 'key', 'point', 'main', 'topic', 'structure', 'overview', 'conclusion'],
        min_keywords=4,
        min_length=150,
        test_name="Presentation Video Summary"
    )
    
    print(f"Presentation Summary Complete - Async: {is_async}")


def test_video_highlight_extraction_with_webhooks(overlord):
    """Test understanding of extracting highlights from video with webhook support"""
    print("\n=== Test 3C3 with Webhooks: Video Highlight Extraction ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_highlights",
            message="How would you identify and extract the most important moments or highlights from a long video recording?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['highlight', 'important', 'moment', 'key', 'extract', 'identify', 'significant', 'clip'],
        min_keywords=3,
        min_length=50,
        test_name="Video Highlight Extraction"
    )
    
    print(f"Highlight Extraction Complete - Async: {is_async}")


def test_multi_speaker_video_summary_with_webhooks(overlord):
    """Test understanding of summarizing videos with multiple speakers with webhook support"""
    print("\n=== Test 3C3 with Webhooks: Multi-Speaker Video Summary ===")
    
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_speakers",
            message="If a panel discussion video has 4 different speakers, how would you organize the summary to capture each person's contributions?"
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['speaker', 'panel', 'discussion', 'contribution', 'organize', 'summary', 'person'],
        min_keywords=3,
        min_length=80,
        test_name="Multi-Speaker Video Summary"
    )
    
    print(f"Multi-Speaker Summary Complete - Async: {is_async}")


def test_video_summary_memory_with_webhooks(overlord):
    """Test memory retention about video summary discussion with webhook support"""
    print("\n=== Test 3C3 with Webhooks: Video Summary Memory ===")
    
    # Establish context about video content
    response1 = asyncio.run(
        overlord.chat(
            user_id="test_user_memory",
            message="I'm working on summarizing a training video about data analysis techniques. It covers statistical methods, visualization tools, and data cleaning procedures."
        )
    )
    
    # Check context setup
    result1, is_async1 = check_response_with_webhook(
        response1,
        expected_keywords=['training', 'video', 'data', 'analysis'],
        min_keywords=1,
        min_length=20,
        test_name="Video Summary Context"
    )
    
    # Test memory of video content
    response2 = asyncio.run(
        overlord.chat(
            user_id="test_user_memory",
            message="What are the main topics I should focus on when creating the summary?"
        )
    )
    
    # Check memory - should recall specific topics
    result2, is_async2 = check_response_with_webhook(
        response2,
        expected_keywords=['statistical', 'visualization', 'data', 'cleaning', 'analysis', 'method'],
        min_keywords=2,
        min_length=30,
        test_name="Video Summary Memory"
    )
    
    print(f"Summary Memory Test Complete - Setup Async: {is_async1}, Memory Async: {is_async2}")


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
            test_presentation_video_summary_with_webhooks(overlord)
            test_video_highlight_extraction_with_webhooks(overlord)
            test_multi_speaker_video_summary_with_webhooks(overlord)
            test_video_summary_memory_with_webhooks(overlord)
            print("\nAll webhook tests passed!")
        finally:
            await formation.stop_overlord()
    
    asyncio.run(run_test())