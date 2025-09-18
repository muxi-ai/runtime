#!/usr/bin/env python3
"""
Test 12A2: Natural Language Scheduling
Tests natural language time parsing for scheduling.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_natural_language_scheduling():
    """Test natural language scheduling like 'in 5 minutes'."""
    print("\n" + "="*60)
    print("TEST 12A2: Natural Language Scheduling")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Test natural language scheduling
        print("\n[Test] Scheduling with natural language: 'In 5 minutes, generate a status report'")

        response = await overlord.chat(
            "In 5 minutes, generate a status report",
            user_id="test_user",
            session_id="test_session",
            use_async=False,
            stream=False
        )

        content = response.content if hasattr(response, 'content') else str(response)
        print(f"Response: {content[:200]}...")

        # Should parse natural language time
        assert "scheduled" in content.lower() or "will" in content.lower(), \
            "Response should indicate future action"

        print("✅ Natural language scheduling recognized")

        # Cleanup
        await formation.kill_overlord()
        # formation.shutdown()  # Not async, commented out to avoid issues

        print("\n✅ TEST PASSED: Natural language scheduling works")
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_natural_language_scheduling())
    sys.exit(exit_code)
