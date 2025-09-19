#!/usr/bin/env python3
"""
Test 12A3: Schedule with Context
Tests scheduling recurring tasks with context.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_schedule_with_context():
    """Test scheduling with context like daily recurring tasks."""
    print("\n" + "="*60)
    print("TEST 12A3: Schedule with Context")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test recurring schedule with context
        print("\n[Test] Scheduling daily task: 'Every day at 9am, check for new pull requests and summarize them'")

        response = await overlord.chat(
            "Every day at 9am, check for new pull requests and summarize them",
            user_id="test_user",
            session_id="test_session",
            use_async=False,
            stream=False
        )

        content = response.content if hasattr(response, 'content') else str(response)
        print(f"Response: {content[:200]}...")

        # Verify scheduling and daily recurrence
        assert "scheduled" in content.lower(), "Response should indicate task was scheduled"
        assert "daily" in content.lower() or "every day" in content.lower(), \
            "Response should acknowledge daily recurrence"

        print("✅ Daily recurring task scheduled with context")

        # Cleanup
        await formation.kill_overlord()
        # # formation.shutdown() removed - not async  # Not async, commented out to avoid issues

        print("\n✅ TEST PASSED: Schedule with context works")
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_schedule_with_context())
    sys.exit(exit_code)
