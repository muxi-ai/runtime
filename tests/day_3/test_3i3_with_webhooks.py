"""
Test 3I3 with Webhooks: Spreadsheet Format Conversion
Test spreadsheet format conversion and data preservation with webhook support.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


async def test_spreadsheet_format_conversion_with_webhooks():
    """Test spreadsheet format conversion with webhook support"""
    print("\n=== Test 3I3 with Webhooks: Spreadsheet Format Conversion ===")
    
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
            user_id="test_user_spreadsheet",
            message="How would you handle converting between different spreadsheet formats (Excel, CSV, Google Sheets) while preserving formulas, formatting, and data integrity?"
        )
        
        # Use universal webhook checker
        result, is_async = check_response_with_webhook(
            response,
            expected_keywords=["spreadsheet", "format", "conversion", "excel", "csv", "formula", "formatting", "integrity"],
            min_keywords=4,
            min_length=120,
            test_name="Spreadsheet Format Conversion"
        )
        
        print(f"Spreadsheet Format Conversion Complete - Async: {is_async}")
        
    finally:
        await loop.run_in_executor(None, formation.stop_overlord)


if __name__ == "__main__":
    asyncio.run(test_spreadsheet_format_conversion_with_webhooks())