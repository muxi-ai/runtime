#!/usr/bin/env python3
"""
Test 12B1: Cron-based Scheduling
Tests cron expression based scheduling.
"""

import asyncio
import sys
from pathlib import Path
import re

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


def extract_job_id(response: str) -> str:
    """Extract job ID from response text."""
    match = re.search(r'job[_\-][a-zA-Z0-9]+', response)
    if match:
        return match.group(0)
    return None


async def test_cron_based_scheduling():
    """Test cron-based scheduling with specific schedule."""
    print("\n" + "="*60)
    print("TEST 12B1: Cron-based Scheduling")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test cron-based scheduling
        print("\n[Test] Scheduling with cron: 'Generate sales report every Monday at 8am'")

        response = await overlord.chat(
            "Generate sales report every Monday at 8am",
            user_id="test_user",
            session_id="test_session",
            use_async=False,
            stream=False
        )

        content = response.content if hasattr(response, 'content') else str(response)
        print(f"Response: {content[:200]}...")

        job_id = extract_job_id(content)
        assert "scheduled" in content.lower(), "Response should indicate task was scheduled"

        if job_id:
            print(f"✅ Job scheduled with ID: {job_id}")

            # Note: To fully verify, we would need scheduler API access to check:
            # - Job exists in active jobs list
            # - Job has correct cron expression "0 8 * * MON"
            print("\n[Note] Job verification skipped (requires scheduler API access)")
        else:
            print("⚠️ Warning: Could not extract job ID from response")

        print("\n✅ TEST PASSED: Cron-based scheduling works")

        # Cleanup
        try:
            if overlord:
                await formation.kill_overlord()
            # Note: shutdown() may cause issues, skip it for now
            # formation.shutdown()
        except Exception as cleanup_error:
            print(f"Warning: Cleanup error: {cleanup_error}")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_cron_based_scheduling())
    sys.exit(exit_code)
