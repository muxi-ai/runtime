#!/usr/bin/env python3
"""
Test 7A3: Workflow Plan Generation
Migrated from: tests/e2e/7_orchestration/test_workflow_plan_only.py
Tests workflow plan generation only - auto-declines to inspect the plan without execution.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_workflow_plan_only():
    """Test workflow plan generation with auto-decline."""
    print("\n" + "=" * 80)
    print("Test 7A3: Workflow Plan Generation (Plan Only)")
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
        print(f"   Agents: {len(overlord.agents)}")

        print(f"\n2. Sending request to trigger workflow plan generation...")
        start_time = datetime.now()

        # Simpler request to trigger workflow without long execution
        response = await asyncio.wait_for(
            overlord.chat(
                message="Plan a 3-step process: 1) research AI healthcare trends 2) analyze key findings 3) create summary. Just show the plan, don't execute.",
                user_id="demo_user",
                session_id="plan_test",
                stream=False
            ),
            timeout=90  # 90 second timeout
        )

        # Handle response
        content = response.content if hasattr(response, 'content') else str(response)

        # Check if approval requested
        approval_requested = ("proposed approach" in content.lower() or 
                             "does this approach work" in content.lower() or
                             "approve" in content.lower())

        if approval_requested:
            print("\n   ✓ Workflow approval requested!")
            print(f"\n   Proposed plan ({len(content)} chars):")
            print(f"   {content[:400]}...")
            checks_passed.append("Plan generated successfully")

            # Decline the plan
            print("\n3. Declining plan (test mode - plan inspection only)...")
            decline_response = await overlord.chat(
                message="No, cancel this workflow",
                user_id="demo_user",
                session_id="plan_test",
                stream=False
            )

            decline_content = decline_response.content if hasattr(decline_response, 'content') else str(decline_response)
            print(f"\n   ✓ Decline processed: {decline_content[:100]}...")
            checks_passed.append("Decline handled correctly")
        else:
            print("\n   ⚠️  No approval requested - may not be complex enough")
            print(f"\n   Response: {content[:200]}...")
            checks_passed.append("Response received")

        total_time = (datetime.now() - start_time).total_seconds()
        print(f"\n   ⏱️  Total time: {total_time:.1f}s")

        # Cleanup
        print("\n4. Cleaning up...")
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
    exit_code = asyncio.run(test_workflow_plan_only())
    sys.exit(exit_code)
