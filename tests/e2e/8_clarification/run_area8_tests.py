#!/usr/bin/env python3
"""
Area 8: Clarification & Enhanced Information Flow - Comprehensive Test Runner

This script runs all Area 8 tests covering:
- 8A: Single Clarification Patterns
- 8B: Information Flow
- 8C: Multiple Clarification Sequences
"""
import asyncio
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


async def run_test_file(test_file: str, test_name: str) -> Tuple[str, bool, float]:
    """Run a single test file and return results."""
    print(f"\n{'='*60}")
    print(f"Running: {test_name}")
    print('='*60)
    
    start_time = time.time()
    
    try:
        # Import and run the test
        module_name = test_file.replace('.py', '')
        module = __import__(module_name)
        
        # Look for main test function or run_tests function
        if hasattr(module, 'run_tests'):
            result = await module.run_tests()
        else:
            # Find the main test function (should match the file name pattern)
            test_func_name = module_name.replace('test_', 'test_')
            if hasattr(module, test_func_name):
                test_func = getattr(module, test_func_name)
                result = await test_func()
            else:
                print(f"⚠️ No test function found in {test_file}")
                result = False
        
        elapsed = time.time() - start_time
        return test_name, result, elapsed
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ Error running {test_name}: {e}")
        import traceback
        traceback.print_exc()
        return test_name, False, elapsed


async def main():
    """Run all Area 8 tests."""
    print("\n" + "="*80)
    print(" "*20 + "AREA 8: CLARIFICATION TESTS")
    print(" "*15 + "Comprehensive Test Suite Execution")
    print("="*80)
    
    # Change to test directory
    test_dir = Path(__file__).parent
    import os
    os.chdir(test_dir)
    
    # Define all test files in execution order
    test_files = [
        # Group 8A: Single Clarification Patterns
        ("test_8a1_ambiguous_request.py", "8A1: Ambiguous Request Clarification"),
        ("test_8a2_multi_agent_clarification.py", "8A2: Multi-Agent Clarification"),
        
        # Group 8B: Information Flow
        ("test_8b1_context_propagation.py", "8B1: Context Propagation"),
        ("test_8b2_information_extraction.py", "8B2: Information Extraction"),
        ("test_8b3_multi_turn_context.py", "8B3: Multi-turn Context Management"),
        
        # Group 8C: Multiple Clarification Sequences
        ("test_8c1_credential_rejection_flow.py", "8C1: Credential Rejection Flow"),
        ("test_8c2_multi_step_clarification.py", "8C2: Multi-step Clarification"),
        ("test_8c3_complex_parameter_collection.py", "8C3: Complex Parameter Collection"),
    ]
    
    # Run all tests
    results: List[Tuple[str, bool, float]] = []
    total_start = time.time()
    
    for test_file, test_name in test_files:
        if Path(test_file).exists():
            result = await run_test_file(test_file, test_name)
            results.append(result)
        else:
            print(f"\n⚠️ Test file not found: {test_file}")
            results.append((test_name, False, 0))
    
    total_elapsed = time.time() - total_start
    
    # Print summary
    print("\n" + "="*80)
    print(" "*25 + "TEST EXECUTION SUMMARY")
    print("="*80)
    
    # Group results by test group
    groups = {
        "8A": [],
        "8B": [],
        "8C": []
    }
    
    for name, passed, elapsed in results:
        group = name[:2]
        if group in groups:
            groups[group].append((name, passed, elapsed))
    
    # Print results by group
    for group_name, group_results in groups.items():
        if group_results:
            print(f"\nGroup {group_name}:")
            for name, passed, elapsed in group_results:
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"  {name:<45} {status} ({elapsed:.2f}s)")
    
    # Calculate statistics
    total_tests = len(results)
    passed_tests = sum(1 for _, passed, _ in results if passed)
    failed_tests = total_tests - passed_tests
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print("\n" + "-"*80)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} ({pass_rate:.1f}%)")
    print(f"Failed: {failed_tests}")
    print(f"Total Time: {total_elapsed:.2f}s")
    
    # Feature validation
    print("\n" + "="*80)
    print(" "*20 + "FEATURE VALIDATION SUMMARY")
    print("="*80)
    
    features = {
        "Single Clarification": all(p for n, p, _ in results if n.startswith("8A")),
        "Information Flow": all(p for n, p, _ in results if n.startswith("8B")),
        "Multiple Sequences": all(p for n, p, _ in results if n.startswith("8C")),
    }
    
    for feature, validated in features.items():
        status = "✅ Validated" if validated else "❌ Issues Found"
        print(f"{feature:<30} {status}")
    
    # Test plan compliance
    print("\n" + "="*80)
    print(" "*18 + "TEST PLAN COMPLIANCE STATUS")
    print("="*80)
    
    if pass_rate >= 90:
        print("✅ AREA 8 COMPLETE: All clarification features validated")
        print("   - Single clarification patterns working")
        print("   - Information flow and context management verified")
        print("   - Multiple clarification sequences implemented")
        print("   - Complex parameter collection functional")
    elif pass_rate >= 70:
        print("⚠️ AREA 8 PARTIAL: Most features working, some issues remain")
    else:
        print("❌ AREA 8 INCOMPLETE: Significant issues found")
    
    # Final status
    print("\n" + "="*80)
    if passed_tests == total_tests:
        print(" "*25 + "🎉 ALL TESTS PASSED! 🎉")
    else:
        print(f" "*20 + f"⚠️ {failed_tests} TEST(S) NEED ATTENTION ⚠️")
    print("="*80 + "\n")
    
    return passed_tests == total_tests


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)