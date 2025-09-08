#!/usr/bin/env python3
"""
Day 8 Test Runner

Runs all Day 8 Part 1 (8A) tests for intelligent clarification.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def run_all_tests():
    """Run all Day 8 tests."""

    print("=" * 60)
    print("Day 8: Intelligent Clarification Tests")
    print("Part 1: Base Clarification Testing (8A)")
    print("=" * 60)

    # Test 8A1: Ambiguous Request
    print("\n📝 Running Test 8A1: Ambiguous Request Clarification...")
    print("-" * 40)
    try:
        from test_8a1_ambiguous_request import (
            test_ambiguous_request_clarification,
            test_ambiguous_technical_request,
            test_no_clarification_for_clear_request
        )

        await test_ambiguous_request_clarification()
        await test_ambiguous_technical_request()
        await test_no_clarification_for_clear_request()
        print("✅ Test 8A1: All subtests passed!")
    except Exception as e:
        print(f"❌ Test 8A1 failed: {e}")
        return False

    # Test 8A2: Multi-Agent Clarification
    print("\n📝 Running Test 8A2: Multi-Agent Clarification...")
    print("-" * 40)
    try:
        from test_8a2_multi_agent_clarification import (
            test_multi_agent_routing_clarification,
            test_agent_specialty_clarification,
            test_direct_agent_request_no_clarification
        )

        await test_multi_agent_routing_clarification()
        await test_agent_specialty_clarification()
        await test_direct_agent_request_no_clarification()
        print("✅ Test 8A2: All subtests passed!")
    except Exception as e:
        print(f"❌ Test 8A2 failed: {e}")
        return False

    # Test 8A3: Removed - Credential clarification already tested in Day 4
    print("\n📝 Test 8A3: Credential Clarification")
    print("-" * 40)
    print("✅ Skipped - Already tested in Day 4")

    print("\n" + "=" * 60)
    print("✅ Day 8 Part 1 Testing Complete!")
    print("=" * 60)
    print("\nSummary:")
    print("- Test 8A1: Ambiguous Request ✅")
    print("- Test 8A2: Multi-Agent Clarification ✅")
    print("- Test 8A3: Credential Clarification - Skipped (Day 4)")
    print("\nBase clarification capabilities validated.")
    print("\nNext: Part 2 will test multiple clarification sequences")
    print("      (requires implementation of clarification stack)")

    return True


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
