"""
Test 3F4 with Webhooks: Video Frame Extraction
Extract and analyze frames from video files with webhook support.
"""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_video_frame_extraction_with_webhooks():
    """Test video frame extraction and analysis with webhook support"""
    print("\n=== Test 3F4 with Webhooks: Video Frame Extraction and Analysis ===")
    print("Goal: Extract and analyze frames from video files with webhook support")
    
    # Setup webhook testing environment
    setup_webhook_test()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    try:
        # Test conceptual video understanding if no real video file
        video_path = Path("test-docs/demo.mov")
        if not video_path.exists():
            print(f"Video file not found at {video_path}, testing conceptual video analysis...")
            
            # Test video analysis understanding
            response = await overlord.chat(
                user_id="test_user_video_concept",
                message="If I upload a product demo video showing a software interface with buttons, menus, and user interactions, how would you extract and analyze the key frames?"
            )
            
            # Use universal webhook checker
            result, is_async = check_response_with_webhook(
                response,
                expected_keywords=["frame", "extract", "video", "analysis", "visual", "software", "interface"],
                min_keywords=4,
                min_length=100,
                test_name="Video Frame Conceptual Understanding"
            )
            
            print(f"Video Frame Conceptual Test Complete - Async: {is_async}")
            return
        
        # If video file exists, test real video processing
        with open(video_path, "rb") as f:
            video_content = f.read()
        
        # Send request with video file
        print("Sending video frame analysis request...")
        response = await overlord.chat(
            user_id="test_user_video",
            message="Please analyze this video. Extract key frames and describe what's happening in the video, including any text or important visual elements.",
            files=[{
                "filename": video_path.name,
                "content": video_content,
                "content_type": "video/quicktime",
                "size": len(video_content),
            }],
        )
        
        # Use universal webhook checker for video processing (likely async)
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["video", "frame", "analysis", "visual", "content", "scene"],
            min_keywords=3,
            min_length=50,
            timeout=120.0,  # Give more time for video processing
            test_name="Real Video Frame Extraction"
        )
        
        print(f"Real Video Frame Extraction Complete - Async: {is_async}")
        
    finally:
        print("🔚 Stopping overlord...")
        await loop.run_in_executor(None, formation.stop_overlord)


async def test_video_analysis_methodology_with_webhooks():
    """Test understanding of video analysis methodology with webhook support"""
    print("\n=== Test 3F4 with Webhooks: Video Analysis Methodology ===")
    
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
            user_id="test_user_video_method",
            message="What are the best strategies for extracting meaningful frames from different types of videos: tutorials, presentations, meetings, and product demos?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["frame", "extract", "video", "tutorial", "presentation", "meeting", "demo", "strategy"],
            min_keywords=4,
            min_length=150,
            test_name="Video Analysis Methodology"
        )
        
        print(f"Video Analysis Methodology Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    async def run_all_tests():
        await test_video_frame_extraction_with_webhooks()
        await test_video_analysis_methodology_with_webhooks()
        print("\nAll video frame extraction webhook tests completed!")
    
    asyncio.run(run_all_tests())