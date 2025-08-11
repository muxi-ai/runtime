#!/usr/bin/env python3
"""
Test Group 5C: Spreadsheet Generation - Fixed version
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

from muxi import Formation
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
        outputs_dir = Path.cwd() / "outputs"
        outputs_dir.mkdir(exist_ok=True)

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
            with open(outputs_dir / f"{test_id}_fixed.json", "w") as f:
                json.dump(response_data, f, indent=2)

            print(f"Response saved to: outputs/{test_id}_fixed.json")
            print(f"Artifacts found: {len(response_data['artifacts'])}")

            return response_data

        finally:
            # Clean up
            asyncio.run(formation.stop_overlord())

    # Run test in thread
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        return future.result()

def main():
    """Run all tests in group 5C"""

    tests = [
        ("5c1", "Test 5C1: Excel File Creation",
         "Create an Excel file with sales data: Product A: 100 units, Product B: 150 units, Product C: 75 units"),

        ("5c2", "Test 5C2: Complex Data Analysis",
         "Generate a spreadsheet with pivot tables and charts for quarterly sales analysis"),

        ("5c3", "Test 5C3: Financial Models",
         "Create a financial model spreadsheet with revenue projections and cost analysis")
    ]

    results = []

    for test_id, test_name, prompt in tests:
        try:
            result = run_single_test(test_id, test_name, prompt)
            results.append(result)

            # Brief pause between tests
            time.sleep(2)

        except Exception as e:
            print(f"Error in {test_name}: {e}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for i, (test_id, test_name, _) in enumerate(tests):
        if i < len(results):
            print(f"{test_name}: {len(results[i]['artifacts'])} artifacts")

    return results

if __name__ == "__main__":
    main()
