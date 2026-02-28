#!/usr/bin/env python3
"""
Test 7A4: Workflow Resilience
Migrated from: e2e/tests/7_orchestration/test_workflow_resilience_integration.py
Tests resilience features during workflow execution with error handling.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_workflow_resilience():
    """Test workflow resilience and error handling."""
    print("\n" + "=" * 80)
    print("Test 7A4: Workflow Resilience")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-multi-agent" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Check for resilience features
        if hasattr(overlord, 'resilience_enabled'):
            print(f"   ✓ Resilience enabled: {overlord.resilience_enabled}")
            checks_passed.append("Resilience configuration present")

        print("\n2. Sending request that may trigger errors...")
        # Send a simpler request that tests workflow but doesn't take forever
        response = await overlord.chat(
            message="Analyze the current market trends and create a brief summary",
            user_id="test_user",
            session_id="resilience_test",
            stream=False
        )

        # Handle response
        content = response.content if hasattr(response, 'content') else str(response)
        print(f"\n   ✓ Response received ({len(content)} chars):")
        print(f"   {content[:200]}...")
        checks_passed.append("Request handled successfully")

        # Check for error handling indicators
        if hasattr(response, 'metadata') and response.metadata:
            if 'errors' in response.metadata:
                print(f"\n   Errors encountered: {response.metadata['errors']}")
                checks_passed.append("Error information captured")

        # Cleanup
        print("\n3. Cleaning up...")
        await formation.stop_overlord()
        formation.stop()
        print("   ✓ Formation stopped")

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
    import os

    exit_code = asyncio.run(test_workflow_resilience())

    if exit_code == 0:

        print("SUCCESS", flush=True)

    os._exit(exit_code)
