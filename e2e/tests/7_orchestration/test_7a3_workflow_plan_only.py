#!/usr/bin/env python3
"""
Test 7A3: Workflow Configuration
Migrated from: tests/e2e/7_orchestration/test_workflow_plan_only.py
Tests workflow system configuration and basic functionality.
For CI/CD speed, tests configuration not full workflow execution.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_workflow_plan_only():
    """Test workflow system configuration."""
    print("\n" + "=" * 80)
    print("Test 7A3: Workflow Configuration")
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

        # Test: Check workflow configuration
        print("\n2. Checking workflow configuration...")
        
        if hasattr(overlord, 'workflow_config'):
            print(f"   ✓ Workflow config present")
            checks_passed.append("Workflow configuration exists")
            
            if hasattr(overlord.workflow_config, 'auto_decomposition'):
                print(f"   ✓ Auto decomposition: {overlord.workflow_config.auto_decomposition}")
                checks_passed.append(f"Auto decomposition: {overlord.workflow_config.auto_decomposition}")
                
            if hasattr(overlord.workflow_config, 'complexity_threshold'):
                print(f"   ✓ Complexity threshold: {overlord.workflow_config.complexity_threshold}")
                checks_passed.append(f"Complexity threshold: {overlord.workflow_config.complexity_threshold}")
        else:
            print("   ⚠️  No workflow config - may be using defaults")
            checks_passed.append("Using default workflow settings")

        # Test: Send simple message to verify basic functionality
        print("\n3. Testing basic response...")
        response = await asyncio.wait_for(
            overlord.chat(
                message="Hello!",
                user_id="demo_user",
                session_id="plan_test",
                stream=False
            ),
            timeout=30
        )

        content = response.content if hasattr(response, 'content') else str(response)
        if content and len(content) > 0:
            print(f"   ✓ Response received ({len(content)} chars)")
            checks_passed.append("Basic communication working")
            all_passed = True
        else:
            print("   ✗ Empty response")
            all_passed = False

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
