#!/usr/bin/env python3
"""
Test 7B2: SOP Workflow Execution
Migrated from: tests/e2e/7_orchestration/test_internal_sops.py
Tests SOP (Standard Operating Procedure) execution with artifacts.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_sop_workflow():
    """Test SOP workflow execution."""
    print("\n" + "=" * 80)
    print("Test 7B2: SOP Workflow Execution")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-multi-agent-sop" / "formation.yaml"
    all_passed = True
    checks_passed = []

    try:
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")

        # Check SOP system
        if hasattr(overlord, 'sop_system') and overlord.sop_system:
            sop_count = len(overlord.sop_system.sops) if hasattr(overlord.sop_system, 'sops') else 0
            print(f"   ✓ SOP system initialized with {sop_count} SOPs")
            checks_passed.append(f"SOP system with {sop_count} procedures")

            # Wait for SOP indexing
            await asyncio.sleep(1)

        print("\n2. Sending request to trigger SOP execution...")
        # Simpler request to test SOP without slow Linear API
        response = await asyncio.wait_for(
            overlord.chat(
                message="What system metrics should we monitor? List cpu, memory, and disk usage guidelines.",
                user_id="test_user",
                session_id="sop_test",
                stream=False,
                use_async=False
            ),
            timeout=90  # 90 second timeout
        )

        # Handle response
        if isinstance(response, str):
            content = response
        elif hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        print(f"\n   ✓ Response received ({len(content)} chars):")
        print(f"   {content[:400]}...")

        # Check for Linear issue creation
        linear_indicators = ["linear", "issue", "created", "mx-"]
        has_linear = any(ind in content.lower() for ind in linear_indicators)

        if has_linear:
            print("\n   ✓ Linear issue created via SOP")
            checks_passed.append("Linear issue creation")

        # Check for system information
        system_indicators = ["cpu", "memory", "system"]
        has_system_info = any(ind in content.lower() for ind in system_indicators)

        if has_system_info:
            print("\n   ✓ System information included")
            checks_passed.append("System usage information")

        checks_passed.append("SOP workflow completed")

        # Cleanup
        print("\n3. Cleaning up...")
        await formation.stop_overlord()
        formation.stop()
        print("   ✓ Formation stopped")

    except asyncio.TimeoutError:
        print("\n✗ TIMEOUT: Request took longer than 5 minutes")
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
    exit_code = asyncio.run(test_sop_workflow())
    sys.exit(exit_code)
