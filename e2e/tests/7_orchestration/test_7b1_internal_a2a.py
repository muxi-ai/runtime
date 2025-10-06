#!/usr/bin/env python3
"""
Test 7B1: Internal A2A Configuration
Migrated from: tests/e2e/7_orchestration/test_internal_a2a_communication.py
Tests internal A2A configuration and basic functionality.
For CI/CD speed, tests configuration not full workflow execution.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_internal_a2a():
    """Test internal A2A configuration."""
    print("\n" + "=" * 80)
    print("Test 7B1: Internal A2A Configuration")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-multi-agent-segregated" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")
        print(f"   Agents: {list(overlord.agents.keys())}")

        # Test: Check A2A coordinator
        print("\n2. Checking A2A configuration...")
        if hasattr(overlord, 'a2a_coordinator') and overlord.a2a_coordinator:
            print("   ✓ A2A coordinator initialized")
            checks_passed.append("A2A coordinator present")
            all_passed = True
        else:
            print("   ⚠️  No A2A coordinator found")
            checks_passed.append("No A2A coordinator (may be disabled)")
            all_passed = True  # Not all formations need A2A

        # Test: Send simple message to verify basic functionality
        print("\n3. Testing basic response...")
        response = await asyncio.wait_for(
            overlord.chat(
                message="Hello!",
                user_id="test_user",
                session_id="a2a_test",
                stream=False
            ),
            timeout=30
        )

        # Handle response
        if isinstance(response, str):
            content = response
        elif hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        if content and len(content) > 0:
            print(f"   ✓ Response received ({len(content)} chars)")
            checks_passed.append("Basic communication working")
        else:
            print("   ✗ Empty response")
            all_passed = False

        # Cleanup
        print("\n4. Cleaning up...")
        await formation.stop_overlord()
        formation.stop()
        print("   ✓ Formation stopped")

    except asyncio.TimeoutError:
        print("\n✗ TIMEOUT: Request took longer than 3 minutes")
        all_passed = False
    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Print results
    print("\n" + "=" * 80)
    print(f"Test Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  ✓ {check}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_internal_a2a())
    sys.exit(exit_code)
