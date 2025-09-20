#!/usr/bin/env python3
"""
Run all enhanced Day 2 memory tests
"""
import sys
import asyncio
import subprocess

# Test groups with descriptions
TEST_GROUPS = {
    "2I: Natural Language Extraction": [
        "test_2i1_natural_language_extraction.py",
        "test_2i2_complex_extraction.py",
        "test_2i3_context_aware_extraction.py"
    ],
    "2J: Collection Field Usage": [
        "test_2j1_collection_field_usage.py"
    ],
    "2K: Memory Integration": [
        "test_2k1_enhanced_prompt_integration.py",
        "test_2k2_memory_priority.py"
    ],
    "2L: Database Optimization": [
        "test_2l1_database_optimization.py"
    ],
    "2M: Error Resilience": [
        "test_2m1_error_resilience_no_mock.py"
    ]
}


async def run_test(test_file):
    """Run a single test file."""
    print(f"\n{'='*80}")
    print(f"Running: {test_file}")
    print('='*80)

    result = subprocess.run(
        [sys.executable, test_file],
        capture_output=False,
        text=True
    )

    return result.returncode == 0


async def main():
    """Run all enhanced Day 2 tests."""
    print("MUXI Runtime - Day 2 Enhanced Memory Tests")
    print("=" * 80)
    print("\nThese tests verify:")
    print("- Natural language memory storage (not key-value pairs)")
    print("- Age to birth year conversion")
    print("- Collection field usage without collections table")
    print("- Enhanced prompt integration")
    print("- Database optimization and indexes")
    print("- Error resilience and graceful degradation")
    print("\nAll tests use real services via chat flow - no mocks!")

    total_tests = sum(len(tests) for tests in TEST_GROUPS.values())
    passed = 0
    failed = 0

    for group_name, test_files in TEST_GROUPS.items():
        print(f"\n\n{'='*80}")
        print(f"Test Group {group_name}")
        print('='*80)

        for test_file in test_files:
            if await run_test(test_file):
                passed += 1
                print(f"✅ {test_file} PASSED")
            else:
                failed += 1
                print(f"❌ {test_file} FAILED")

    # Summary
    print(f"\n\n{'='*80}")
    print("ENHANCED TEST SUMMARY")
    print('='*80)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/total_tests)*100:.1f}%")

    if failed == 0:
        print("\n🎉 All enhanced memory tests passed!")
    else:
        print(f"\n⚠️  {failed} tests failed. Please check the output above.")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
