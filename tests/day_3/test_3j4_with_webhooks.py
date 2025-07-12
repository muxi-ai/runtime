"""
Test 3J4 with Webhooks: Timeout Handling Large Files
Test timeout handling for large file processing with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_timeout_handling_large_files_with_webhooks():
    """Test timeout handling for large files with webhook support"""
    print("\n=== Test 3J4 with Webhooks: Timeout Handling Large Files ===")
    
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
            user_id="test_user_timeout",
            message="How would you handle processing timeouts for large files? What retry strategies, partial processing, and graceful degradation approaches would you implement?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["timeout", "large", "file", "retry", "partial", "processing", "graceful", "degradation"],
            min_keywords=4,
            min_length=120,
            test_name="Timeout Handling Large Files"
        )
        
        print(f"Timeout Handling Large Files Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_timeout_handling_large_files_with_webhooks())