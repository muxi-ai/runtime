"""
Test 3I2 with Webhooks: Image Slides Presentation Match
Test matching between presentation slides and extracted images with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_image_slides_presentation_match_with_webhooks():
    """Test image-slides presentation matching with webhook support"""
    print("\n=== Test 3I2 with Webhooks: Image Slides Presentation Match ===")
    
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
            user_id="test_user_image_slides",
            message="How would you match individual slide images with corresponding sections in a presentation document? What visual and content features would you compare?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["image", "slide", "presentation", "match", "visual", "content", "feature", "compare"],
            min_keywords=4,
            min_length=120,
            test_name="Image Slides Presentation Match"
        )
        
        print(f"Image Slides Presentation Match Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_image_slides_presentation_match_with_webhooks())