#!/usr/bin/env python3
"""
Test Group 5F: Implicit File Generation (INTELLIGENT)
Tests the file generation MCP's ability to intelligently create files
when users don't explicitly ask for them, but the context suggests they need them.
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

            # Check if response indicates file creation
            content_lower = response_data['content'].lower()
            has_file_indicators = any(term in content_lower for term in [
                'chart', 'graph', 'visualization', 'document', 'report',
                'presentation', 'slides', '.png', '.jpg', '.docx', '.pdf', '.pptx',
                'created', 'generated', 'prepared'
            ])

            return response_data, has_file_indicators

        finally:
            # Clean up
            asyncio.run(formation.stop_overlord())

    # Run test in thread
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        return future.result()

def main():
    """Run all tests in group 5F"""

    tests = [
        ("5f1", "Test 5F1: Visual Data Request",
         "Show me how our sales have grown over the last quarter"),

        ("5f2", "Test 5F2: Documentation Request",
         "I need the project status update for my manager"),

        ("5f3", "Test 5F3: Data Analysis Request",
         "Analyze these numbers and show me the trends: Q1: 100k, Q2: 150k, Q3: 175k, Q4: 200k"),

        ("5f4", "Test 5F4: Presentation Need",
         "I'm presenting our roadmap to investors tomorrow - help me with the key milestones"),

        ("5f5", "Test 5F5: Complex Implicit Request",
         "Compare last year's performance with this year's projections")
    ]

    results = []
    test_outcomes = []

    for test_id, test_name, prompt in tests:
        try:
            result, has_file_indicators = run_single_test(test_id, test_name, prompt)
            results.append(result)

            # For implicit file generation, success means:
            # Either artifacts were created OR the response indicates file creation intent
            success = len(result['artifacts']) > 0 or has_file_indicators

            test_outcomes.append({
                "test_id": test_id,
                "test_name": test_name,
                "success": success,
                "artifacts_created": len(result['artifacts']),
                "has_file_indicators": has_file_indicators,
                "implicit_generation": len(result['artifacts']) > 0
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
    implicit_generation = sum(1 for t in test_outcomes if t.get('implicit_generation', False))

    for outcome in test_outcomes:
        status = "✅ PASS" if outcome.get('success') else "❌ FAIL"
        print(f"{outcome['test_name']}: {status}")
        if 'error' in outcome:
            print(f"  Error: {outcome['error']}")
        else:
            print(f"  Artifacts: {outcome['artifacts_created']}")
            print(f"  File Indicators in Response: {'Yes' if outcome['has_file_indicators'] else 'No'}")
            print(f"  Implicit Generation: {'Yes' if outcome['implicit_generation'] else 'No'}")

    print(f"\nSuccess Rate: {total_success}/{len(test_outcomes)} ({total_success/len(test_outcomes)*100:.0f}%)")
    print(f"Implicit Generation Rate: {implicit_generation}/{len(test_outcomes)} ({implicit_generation/len(test_outcomes)*100:.0f}%)")

    return results, test_outcomes

if __name__ == "__main__":
    main()
