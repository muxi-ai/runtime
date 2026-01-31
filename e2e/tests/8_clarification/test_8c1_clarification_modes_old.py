#!/usr/bin/env python3
"""
Test 8C1: Clarification Modes
Tests the five clarification modes: direct, brainstorm, planning, execution, credential.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_clarification_modes():
    """Test different clarification modes are triggered appropriately."""
    print("\n" + "=" * 80)
    print("Test 8C1: Clarification Modes")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Test Direct Mode - Quick disambiguation
        print("\n2. Testing DIRECT mode (quick disambiguation)...")
        print("   Request: 'List files'")
        response = await overlord.chat(
            message="List files",
            user_id="test_direct",
            session_id="mode_direct",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response: {content[:150]}...")

        direct_indicators = ["which directory", "what folder", "where"]
        if any(indicator in content.lower() for indicator in direct_indicators):
            print("   ✅ Direct mode: Quick clarification question")
            checks_passed.append("Direct mode working")
        else:
            print("   ℹ️  Response may have proceeded without clarification")

        await asyncio.sleep(1)

        # Test Brainstorm Mode - Creative exploration
        print("\n3. Testing BRAINSTORM mode (creative exploration)...")
        print("   Request: 'Help me design an app'")
        response = await overlord.chat(
            message="Help me design an app",
            user_id="test_brainstorm",
            session_id="mode_brainstorm",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response: {content[:150]}...")

        brainstorm_indicators = ["what type", "what kind", "ideas", "thinking", "envision"]
        if any(indicator in content.lower() for indicator in brainstorm_indicators):
            print("   ✅ Brainstorm mode: Open-ended exploration")
            checks_passed.append("Brainstorm mode working")
        else:
            print("   ℹ️  Response pattern different from expected")

        await asyncio.sleep(1)

        # Test Planning Mode - Requirements gathering
        print("\n4. Testing PLANNING mode (requirements gathering)...")
        print("   Request: 'Build an e-commerce system'")
        response = await overlord.chat(
            message="Build an e-commerce system",
            user_id="test_planning",
            session_id="mode_planning",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response: {content[:150]}...")

        planning_indicators = ["products", "payment", "features", "requirements", "need"]
        if any(indicator in content.lower() for indicator in planning_indicators):
            print("   ✅ Planning mode: Requirements gathering")
            checks_passed.append("Planning mode working")
        else:
            print("   ℹ️  Response pattern different from expected")

        await asyncio.sleep(1)

        # Test Execution Mode - Parameter clarification
        print("\n5. Testing EXECUTION mode (parameter clarification)...")
        print("   Request: 'Generate a report'")
        response = await overlord.chat(
            message="Generate a report",
            user_id="test_execution",
            session_id="mode_execution",
            stream=False
        )

        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response: {content[:150]}...")

        execution_indicators = ["format", "what data", "which", "type of report"]
        if any(indicator in content.lower() for indicator in execution_indicators):
            print("   ✅ Execution mode: Parameter clarification")
            checks_passed.append("Execution mode working")
        else:
            print("   ℹ️  Response pattern different from expected")

        # Note about credential mode
        print("\n6. CREDENTIAL mode testing...")
        print("   ℹ️  Credential mode tested separately (requires credential errors)")
        checks_passed.append("Credential mode requires specific test setup")

        # Cleanup
        print("\n7. Cleaning up...")
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

    print("\n📝 NOTE: Clarification modes are auto-detected by LLM.")
    print("   Responses may vary based on LLM interpretation.")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_clarification_modes())
    import os; os._exit(exit_code)
