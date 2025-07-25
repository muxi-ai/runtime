#!/usr/bin/env python3
"""
Test Group 5E: Complex Multi-Format Generation
Tests the file generation MCP's ability to handle:
- Integrated multi-format report generation
- Data pipeline creation with multiple outputs
- Interactive dashboard creation
- Error handling and recovery
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Add the runtime source to Python path
runtime_root = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(runtime_root))

from src.muxi import Formation
from test_utils import format_response

def run_single_test(test_id, test_name, prompt):
    """Run a single test"""

    def run_test():
        # Use absolute path to formation
        formation_path = runtime_root / "test-formations" / "formation-file-generation"

        # Create formation and start overlord
        formation = Formation()
        asyncio.run(formation.load(str(formation_path)))
        overlord = asyncio.run(formation.start_overlord())

        # Set up output directory
        outputs_dir = Path.cwd() / "tests" / "outputs"
        outputs_dir.mkdir(exist_ok=True, parents=True)

        try:
            print(f"\n=== {test_name} ===")
            print(f"Prompt: {prompt}")

            # Run the test
            response = asyncio.run(overlord.chat(
                prompt,
                session_id=f"test_{test_id}",
                stream=False
            ))

            # Save response
            response_data = format_response(response)
            with open(outputs_dir / f"{test_id}.json", "w") as f:
                json.dump(response_data, f, indent=2)

            print(f"Response saved to: tests/outputs/{test_id}.json")
            print(f"Artifacts found: {len(response_data['artifacts'])}")

            # List artifact types and formats
            if response_data['artifacts']:
                print("Artifact details:")
                for i, artifact in enumerate(response_data['artifacts']):
                    print(f"  {i+1}. {artifact['filename']} ({artifact['type']}/{artifact['format']})")
                    if 'size_bytes' in artifact.get('metadata', {}):
                        size = artifact['metadata']['size_bytes']
                        print(f"     Size: {size:,} bytes")

            # Check for error handling in 5e4
            content_lower = response_data['content'].lower()
            has_error_handling = any(term in content_lower for term in ['error', 'failed', 'invalid', 'syntax'])

            return response_data, has_error_handling

        finally:
            # Clean up
            asyncio.run(formation.stop_overlord())

    # Run test in thread
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        return future.result()

def main():
    """Run all tests in group 5E"""

    tests = [
        ("5e1", "Test 5E1: Integrated Report Generation",
         "Create a complete quarterly report with Excel data analysis, PowerPoint presentation, and PDF executive summary"),

        ("5e2", "Test 5E2: Data Pipeline Creation",
         "Create a sample CSV with sales data, process the CSV data, create visualization charts, and generate a Word report with findings"),

        ("5e3", "Test 5E3: Interactive Dashboard Creation",
         "Create an interactive dashboard with multiple chart types and data filters"),

        ("5e4", "Test 5E4: Error Handling & Recovery",
         "Create a chart with invalid syntax in the code")
    ]

    results = []
    test_outcomes = []

    for test_id, test_name, prompt in tests:
        try:
            result, has_error_handling = run_single_test(test_id, test_name, prompt)
            results.append(result)

            # Determine test outcome
            if test_id == "5e4":
                # Special case for error handling test
                success = has_error_handling or len(result['artifacts']) == 0
                test_outcomes.append({
                    "test_id": test_id,
                    "test_name": test_name,
                    "success": success,
                    "artifacts_created": len(result['artifacts']),
                    "error_handling": has_error_handling
                })
            else:
                # Regular tests - success if artifacts were created
                success = len(result['artifacts']) > 0
                test_outcomes.append({
                    "test_id": test_id,
                    "test_name": test_name,
                    "success": success,
                    "artifacts_created": len(result['artifacts'])
                })

            # Brief pause between tests
            time.sleep(2)

        except Exception as e:
            print(f"Error in {test_name}: {e}")
            test_outcomes.append({
                "test_id": test_id,
                "test_name": test_name,
                "success": False,
                "error": str(e)
            })

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    total_success = sum(1 for t in test_outcomes if t.get('success', False))

    for outcome in test_outcomes:
        status = "✅ PASS" if outcome.get('success') else "❌ FAIL"
        print(f"{outcome['test_name']}: {status}")
        if 'error' in outcome:
            print(f"  Error: {outcome['error']}")
        else:
            print(f"  Artifacts: {outcome['artifacts_created']}")
            if 'error_handling' in outcome:
                print(f"  Error Handling: {'Yes' if outcome['error_handling'] else 'No'}")

    print(f"\nSuccess Rate: {total_success}/{len(test_outcomes)} ({total_success/len(test_outcomes)*100:.0f}%)")

    return results, test_outcomes

if __name__ == "__main__":
    main()
