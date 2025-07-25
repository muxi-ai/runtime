"""
Test Group 5A: Chart Generation using built-in File Generation MCP

This test validates the system's ability to generate various chart types
using the built-in file generation MCP server.

Based on Test Report: tests/reports/5a.md
Status: ✅ COMPLETED (3/3 PASSED)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.overlord.overlord import MuxiOverlord


async def test_5a1_basic_chart_creation():
    """Test 5A1: Basic Chart Creation

    Expected: Generate a bar chart file with Q1 sales data
    Validated: ✅ PASSED - File created: Q1_sales_barchart.png
    """
    print("\n" + "="*50)
    print("TEST 5A1: Basic Chart Creation")
    print("="*50)

    # Initialize overlord with file generation formation
    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-file-generation"
    overlord = MuxiOverlord(formation_path=str(formation_path))

    try:
        print("Loading formation...")
        await overlord.initialize()
        print(f"✅ Formation loaded: {overlord.formation_config.id}")

        # Test prompt from report
        prompt = "Create a bar chart showing Q1 sales: Jan $100k, Feb $150k, Mar $200k"
        print(f"📝 Prompt: {prompt}")

        # Send message and get response
        print("🔄 Processing request...")
        response = await overlord.process_user_message(prompt, stream=False)

        # Validate response
        print(f"📄 Response content: {response.content[:200]}...")
        print(f"🎯 Artifacts generated: {len(response.artifacts)}")

        # Validate artifacts
        if response.artifacts:
            artifact = response.artifacts[0]
            print(f"📁 Artifact type: {artifact.type}")
            print(f"📁 Artifact format: {artifact.format}")
            print(f"📁 Artifact filename: {artifact.filename}")

            # Validate it's a complete base64 data URL
            if artifact.data_url and artifact.data_url.startswith("data:image/png;base64,"):
                print("✅ Artifact contains complete base64 data URL")
            else:
                print("❌ Artifact missing proper base64 data URL")

            if artifact.thumbnail and artifact.thumbnail.startswith("data:image/png;base64,"):
                print("✅ Artifact contains thumbnail")
            else:
                print("⚠️ Artifact missing thumbnail")

        # Save test results
        output_file = Path(__file__).parent.parent / "outputs" / "5a1.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "test": "5A1",
                "status": "PASSED" if response.artifacts else "FAILED",
                "artifacts_count": len(response.artifacts),
                "response_preview": response.content[:200],
                "artifacts": [
                    {
                        "type": artifact.type,
                        "format": artifact.format,
                        "filename": artifact.filename,
                        "has_data_url": bool(artifact.data_url and artifact.data_url.startswith("data:")),
                        "has_thumbnail": bool(artifact.thumbnail and artifact.thumbnail.startswith("data:"))
                    } for artifact in response.artifacts
                ]
            }, indent=2)

        print(f"💾 Results saved to: {output_file}")

        return len(response.artifacts) > 0

    finally:
        await overlord.cleanup()


async def test_5a2_advanced_data_visualization():
    """Test 5A2: Advanced Data Visualization

    Expected: Generate a line chart with trend analysis
    Validated: ✅ PASSED - Tool execution successful
    """
    print("\n" + "="*50)
    print("TEST 5A2: Advanced Data Visualization")
    print("="*50)

    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-file-generation"
    overlord = MuxiOverlord(formation_path=str(formation_path))

    try:
        await overlord.initialize()
        print(f"✅ Formation loaded: {overlord.formation_config.id}")

        prompt = "Create a line chart with trend analysis for monthly revenue growth"
        print(f"📝 Prompt: {prompt}")

        print("🔄 Processing request...")
        response = await overlord.process_user_message(prompt, stream=False)

        print(f"📄 Response content: {response.content[:200]}...")
        print(f"🎯 Artifacts generated: {len(response.artifacts)}")

        # Save test results
        output_file = Path(__file__).parent.parent / "outputs" / "5a2.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "test": "5A2",
                "status": "PASSED" if response.artifacts else "FAILED",
                "artifacts_count": len(response.artifacts),
                "response_preview": response.content[:200],
                "artifacts": [
                    {
                        "type": artifact.type,
                        "format": artifact.format,
                        "filename": artifact.filename,
                        "has_data_url": bool(artifact.data_url and artifact.data_url.startswith("data:")),
                        "has_thumbnail": bool(artifact.thumbnail and artifact.thumbnail.startswith("data:"))
                    } for artifact in response.artifacts
                ]
            }, indent=2)

        print(f"💾 Results saved to: {output_file}")

        return len(response.artifacts) > 0

    finally:
        await overlord.cleanup()


async def test_5a3_multiple_chart_types():
    """Test 5A3: Multiple Chart Types

    Expected: Generate multiple chart files (pie chart and bar chart)
    Validated: ✅ PASSED - 2 separate artifacts generated
    """
    print("\n" + "="*50)
    print("TEST 5A3: Multiple Chart Types")
    print("="*50)

    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-file-generation"
    overlord = MuxiOverlord(formation_path=str(formation_path))

    try:
        await overlord.initialize()
        print(f"✅ Formation loaded: {overlord.formation_config.id}")

        prompt = "Create both a pie chart and bar chart showing market share data"
        print(f"📝 Prompt: {prompt}")

        print("🔄 Processing request...")
        response = await overlord.process_user_message(prompt, stream=False)

        print(f"📄 Response content: {response.content[:200]}...")
        print(f"🎯 Artifacts generated: {len(response.artifacts)}")

        # Validate multiple artifacts
        if len(response.artifacts) >= 2:
            print("✅ Multiple artifacts generated as expected")
            for i, artifact in enumerate(response.artifacts):
                print(f"📁 Artifact {i+1}: {artifact.filename} ({artifact.format})")
        else:
            print("⚠️ Expected multiple artifacts, got:", len(response.artifacts))

        # Save test results
        output_file = Path(__file__).parent.parent / "outputs" / "5a3.json"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "test": "5A3",
                "status": "PASSED" if len(response.artifacts) >= 2 else "FAILED",
                "artifacts_count": len(response.artifacts),
                "response_preview": response.content[:200],
                "artifacts": [
                    {
                        "type": artifact.type,
                        "format": artifact.format,
                        "filename": artifact.filename,
                        "has_data_url": bool(artifact.data_url and artifact.data_url.startswith("data:")),
                        "has_thumbnail": bool(artifact.thumbnail and artifact.thumbnail.startswith("data:"))
                    } for artifact in response.artifacts
                ]
            }, indent=2)

        print(f"💾 Results saved to: {output_file}")

        return len(response.artifacts) >= 2

    finally:
        await overlord.cleanup()


async def run_test_group_5a():
    """Run all Test Group 5A tests"""
    print("🚀 Starting Test Group 5A: Chart Generation")
    print("Formation: test-formations/formation-file-generation")

    results = {}

    # Run all tests
    results["5A1"] = await test_5a1_basic_chart_creation()
    results["5A2"] = await test_5a2_advanced_data_visualization()
    results["5A3"] = await test_5a3_multiple_chart_types()

    # Summary
    passed = sum(1 for result in results.values() if result)
    total = len(results)

    print("\n" + "="*50)
    print(f"TEST GROUP 5A SUMMARY")
    print("="*50)
    print(f"Tests passed: {passed}/{total}")

    for test_id, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {test_id}: {status}")

    print(f"\nOverall status: {'✅ PASSED' if passed == total else '❌ FAILED'}")

    return passed == total


if __name__ == "__main__":
    asyncio.run(run_test_group_5a())
