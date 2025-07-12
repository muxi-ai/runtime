"""
Test 3J1 with Webhooks: Corrupted File Handling
Test handling of corrupted and damaged files with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_corrupted_file_handling_with_webhooks():
    """Test corrupted file handling with webhook support"""
    print("\n=== Test 3J1 with Webhooks: Corrupted File Handling ===")
    
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
            user_id="test_user_corrupted",
            message="How would you handle corrupted files: partially damaged PDFs, truncated audio files, broken video files, and invalid image formats? What error recovery strategies would you use?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["corrupted", "file", "handle", "damaged", "error", "recovery", "strategy", "invalid"],
            min_keywords=4,
            min_length=120,
            test_name="Corrupted File Handling"
        )
        
        print(f"Corrupted File Handling Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_corrupted_file_handling_with_webhooks())