"""
Test 3G4 with Webhooks: Video Content Description Accuracy
Validate accuracy of video content descriptions with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_video_content_description_accuracy_with_webhooks():
    """Test video content description accuracy validation with webhook support"""
    print("\n=== Test 3G4 with Webhooks: Video Content Description Accuracy ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        response = await overlord.chat(
            user_id="test_user_video_accuracy",
            message="How do you validate the accuracy of video content descriptions for different video types: presentations, tutorials, meetings, demos, and animated content?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["video", "content", "description", "accuracy", "validate", "presentation", "tutorial", "meeting"],
            min_keywords=4,
            min_length=150,
            test_name="Video Content Description Accuracy"
        )
        
        print(f"Video Content Description Accuracy Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_video_analysis_quality_metrics_with_webhooks():
    """Test understanding of video analysis quality metrics with webhook support"""
    print("\n=== Test 3G4 with Webhooks: Video Analysis Quality Metrics ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        response = await overlord.chat(
            user_id="test_user_video_quality",
            message="What metrics can be used to assess video analysis quality: object detection accuracy, scene recognition precision, temporal consistency, and content completeness?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["video", "analysis", "quality", "metric", "detection", "recognition", "temporal", "consistency"],
            min_keywords=4,
            min_length=120,
            test_name="Video Analysis Quality Metrics"
        )
        
        print(f"Video Analysis Quality Metrics Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_video_description_completeness_with_webhooks():
    """Test understanding of video description completeness with webhook support"""
    print("\n=== Test 3G4 with Webhooks: Video Description Completeness ===")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        response = await overlord.chat(
            user_id="test_user_video_completeness",
            message="How do you ensure comprehensive video descriptions that capture visual elements, audio content, text overlays, scene transitions, and key moments?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["video", "description", "comprehensive", "visual", "audio", "text", "overlay", "transition"],
            min_keywords=4,
            min_length=120,
            test_name="Video Description Completeness"
        )
        
        print(f"Video Description Completeness Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_video_content_description_accuracy_with_webhooks()
        await test_video_analysis_quality_metrics_with_webhooks()
        await test_video_description_completeness_with_webhooks()
        print("\nAll video content description accuracy webhook tests completed!")
    
    asyncio.run(run_all_tests())