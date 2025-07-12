"""
Test 3H3 with Webhooks: Extended Video Async Processing
Test async processing for extended video files with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_extended_video_async_processing_with_webhooks():
    """Test extended video async processing with webhook support"""
    print("\n=== Test 3H3 with Webhooks: Extended Video Async Processing ===")
    
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
            user_id="test_user_extended_video",
            message="How would you process a 3-hour training video with screen recordings, presenter commentary, slide transitions, and interactive elements?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["video", "hour", "training", "screen", "presenter", "slide", "transition", "process"],
            min_keywords=4,
            min_length=150,
            test_name="Extended Video Async Processing"
        )
        
        print(f"Extended Video Async Processing Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_extended_video_async_processing_with_webhooks())