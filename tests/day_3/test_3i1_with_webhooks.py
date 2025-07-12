"""
Test 3I1 with Webhooks: PowerPoint Video Consistency
Test consistency validation between PowerPoint slides and video content with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_powerpoint_video_consistency_with_webhooks():
    """Test PowerPoint-video consistency validation with webhook support"""
    print("\n=== Test 3I1 with Webhooks: PowerPoint Video Consistency ===")
    
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
            user_id="test_user_ppt_video",
            message="How would you validate consistency between PowerPoint slides and a recorded presentation video? What discrepancies should you look for?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["powerpoint", "slide", "video", "consistency", "validate", "presentation", "discrepancy"],
            min_keywords=4,
            min_length=120,
            test_name="PowerPoint Video Consistency"
        )
        
        print(f"PowerPoint Video Consistency Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_powerpoint_video_consistency_with_webhooks())