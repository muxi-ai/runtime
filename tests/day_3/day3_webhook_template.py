"""
Template for Day 3 tests with webhook verification.
This shows the pattern to apply to all day 3 tests.
"""

# Standard imports
import sys
sys.path.insert(0, ".")
import pytest
from pathlib import Path

# Formation imports
from src.muxi.runtime.formation.formation import Formation

# Test utilities
from tests.day_3.test_utils import get_response_universal
from tests.day_3.webhook_test_utils import (
    setup_webhook_test,
    check_async_response_with_webhook,
)


# PATTERN 1: Simple sync test (no changes needed)
def test_sync_example(overlord):
    """Example of sync test - no webhook needed"""
    response = get_response_universal(
        overlord.chat(
            user_id="test_user",
            message="Simple question",
            use_async=False,
        )
    )
    
    # Normal assertions
    assert response
    assert len(response) > 10


# PATTERN 2: Async test with webhook verification
def test_async_with_webhook(overlord):
    """Example of async test with webhook verification"""
    
    # Make async request
    response = get_response_universal(
        overlord.chat(
            user_id="test_user",
            message="Complex request that triggers async processing...",
            use_async=True,  # Force async
        )
    )
    
    # Use the helper to check async response and wait for webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['keyword1', 'keyword2', 'keyword3'],  # What to look for in result
        min_keywords=2,      # How many keywords must be found
        min_length=100,      # Minimum result length
        test_name="Test Name"  # For logging
    )
    
    # Optional: Additional checks on webhook result
    if webhook_result:
        # Do more specific verification
        pass


# PATTERN 3: File processing with async/webhook
def test_file_async_with_webhook(overlord):
    """Example of file processing with webhook"""
    
    # Read file
    with open("test_file.txt", "r") as f:
        content = f.read()
    
    # Request with file
    response = get_response_universal(
        overlord.chat(
            user_id="test_user",
            message="Analyze this file...",
            files=[{
                "filename": "test_file.txt",
                "content": content,
                "content_type": "text/plain",
                "size": len(content),
            }],
            use_async=True,
        )
    )
    
    # Check webhook
    webhook_result = check_async_response_with_webhook(
        response,
        expected_keywords=['file', 'analysis', 'content'],
        min_keywords=2,
        min_length=50,
        test_name="File Analysis"
    )


# PATTERN 4: Fixture with webhook setup
@pytest.fixture
async def formation():
    """Formation fixture with webhook setup"""
    # Setup webhook testing
    setup_webhook_test()
    
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-name"
    formation = Formation()
    await formation.load(str(formation_path))
    return formation


# MIGRATION GUIDE:
# 
# For each test file in day 3:
# 
# 1. Add imports:
#    from tests.day_3.webhook_test_utils import (
#        setup_webhook_test,
#        check_async_response_with_webhook,
#    )
#
# 2. In formation fixture, add:
#    setup_webhook_test()
#
# 3. For each async test:
#    - After getting response, replace manual async checking with:
#      webhook_result = check_async_response_with_webhook(
#          response,
#          expected_keywords=[...],  # Keywords relevant to the test
#          min_keywords=N,          # How many must match
#          min_length=N,            # Min result length
#          test_name="Test Name"
#      )
#
# 4. The helper will:
#    - Detect if response is async
#    - Extract request ID
#    - Wait for webhook
#    - Verify webhook content
#    - Handle both async and sync responses gracefully
#
# 5. Tests will pass whether webhook is received or not (graceful degradation)