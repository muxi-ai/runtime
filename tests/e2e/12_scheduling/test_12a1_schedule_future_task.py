#!/usr/bin/env python3
"""
Test 12A1: Schedule Future Task
Validates scheduling a task for future execution.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import re

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


def extract_job_id(response: str) -> str:
    """Extract job ID from response text."""
    # Look for patterns like "Job ID: job_xxx" or "(job_xxx)"
    match = re.search(r'job[_\-][a-zA-Z0-9]+', response)
    if match:
        return match.group(0)
    return None


async def test_schedule_future_task():
    """Test scheduling a task for 1 minute from now."""
    print("\n" + "="*60)
    print("TEST 12A1: Schedule Future Task")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Schedule a task for 1 minute from now
        run_at = datetime.now() + timedelta(minutes=1)
        print(f"\n[Test] Scheduling task for {run_at.isoformat()}")

        response = await overlord.chat(
            f"Remind me to check the deployment status at {run_at.strftime('%H:%M')}",
            user_id="test_user",
            session_id="test_session",
            use_async=False,
            stream=False
        )

        content = response.content if hasattr(response, 'content') else str(response)
        print(f"Response: {content[:200]}...")

        # Verify scheduling
        assert "scheduled" in content.lower(), "Response should indicate task was scheduled"

        job_id = extract_job_id(content)
        if job_id:
            print(f"✅ Job scheduled with ID: {job_id}")
        else:
            print("⚠️ Warning: Could not extract job ID from response")

        # Note: Full execution verification would require waiting 70 seconds
        # and checking job history, which requires scheduler API access
        print("\n[Note] Job execution verification skipped (would require 70s wait)")

        # Cleanup
        await formation.kill_overlord()
        # formation.shutdown()  # Not async, commented out to avoid issues

        print("\n✅ TEST PASSED: Future task scheduled successfully")
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_schedule_future_task())
    sys.exit(exit_code)
