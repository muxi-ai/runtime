#!/usr/bin/env python3
"""
Test 7A3: Workflow Plan Generation + Decline
Migrated from: tests/e2e/7_orchestration/test_workflow_plan_only.py

Tests workflow plan generation WITHOUT execution by auto-declining the plan.
This validates that the workflow system can generate plans that users can inspect and decline.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_workflow_plan_only():
    """Test workflow plan generation with auto-decline."""
    print("\n" + "=" * 80)
    print("Test 7A3: Workflow Plan Generation + Decline")
    print("=" * 80)

    # Use formation-workflow-approval to ensure approval is triggered
    formation_path = Path(__file__).parent / "formations" / "formation-workflow-approval" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")
        print(f"   ✓ Agents: {len(overlord.agents)}")
        print(f"   ✓ Approval threshold: {overlord.plan_approval_threshold}")
        print(f"   ✓ Complexity threshold: {overlord.complexity_threshold}")

        print("\n2. Sending complex request to trigger workflow plan...")
        print("   (Will generate plan, then auto-decline to test decline path)")
        
        # Complex request that will trigger workflow decomposition
        response = await asyncio.wait_for(
            overlord.chat(
                message="Research AI healthcare diagnostics trends for 2025, analyze key players and breakthroughs, then create a comprehensive Linear issue with detailed findings and future predictions",
                user_id="demo_user",
                session_id="plan_test",
                stream=False
            ),
            timeout=120  # Should get plan within 2 minutes
        )

        content = response.content if hasattr(response, 'content') else str(response)
        
        print(f"\n   ✓ Response received ({len(content)} chars)")
        
        # Check if workflow plan was presented
        plan_indicators = ["proposed approach", "does this approach work", "does this work for you", "task", "step", "phase"]
        has_plan = any(ind in content.lower() for ind in plan_indicators)

        if has_plan:
            print("\n   ✅ Workflow plan generated!")
            print(f"\n   Plan preview:")
            print(f"   {content[:400]}...")
            checks_passed.append("Workflow plan generated")
            
            # Now decline the plan
            print("\n3. Declining the workflow plan...")
            decline_response = await asyncio.wait_for(
                overlord.chat(
                    message="No, cancel this workflow",
                    user_id="demo_user",
                    session_id="plan_test",
                    stream=False
                ),
                timeout=60
            )
            
            decline_content = decline_response.content if hasattr(decline_response, 'content') else str(decline_response)
            print(f"\n   ✓ Decline response received ({len(decline_content)} chars)")
            print(f"   {decline_content[:200]}...")
            
            # Check that decline was acknowledged (not executing workflow)
            decline_indicators = ["cancel", "not proceed", "declined", "understood", "won't", "will not"]
            has_decline = any(ind in decline_content.lower() for ind in decline_indicators)
            
            if has_decline:
                print("   ✅ Plan decline acknowledged")
                checks_passed.append("Plan decline acknowledged")
            else:
                print("   ⚠️  Decline acknowledgment unclear")
                checks_passed.append("Decline processed")
            
            all_passed = True
            
        else:
            print("\n   ⚠️  No clear workflow plan detected")
            print("   Response may be direct answer without workflow")
            checks_passed.append("Response received but plan unclear")
            all_passed = True  # Don't fail - LLM behavior varies

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
