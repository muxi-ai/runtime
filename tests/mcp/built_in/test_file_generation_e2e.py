#!/usr/bin/env python3
"""
Mini end-to-end test for File Generation MCP.
This script demonstrates the full capability of generating files through MUXI.
"""

import asyncio
import os
import sys
import tempfile
import yaml
from pathlib import Path

# Add runtime source to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime import Formation


async def test_file_generation():
    """Test file generation capability end-to-end."""
    # Configuration for the test
    # Note: Uses environment variable for API key for security
    config = {
        "schema": "1.0.0",
        "id": "file-gen-test",
        "description": "Test file generation capability",
        "llm": {
            "api_keys": {
                "openai": os.environ.get("OPENAI_API_KEY", "test-key-for-testing")
            },
            "models": [
                {"text": "gpt-3.5-turbo", "provider": "openai"}
            ]
        },
        "agents": [{
            "schema": "1.0.0",
            "id": "file-creator",
            "name": "File Creator",
            "description": "Agent that creates files"
        }],
        "runtime": {
            "built_in_mcps": ["file-generation"]  # Enable file generation MCP
        }
    }

    # Create temporary directory for the test
    with tempfile.TemporaryDirectory() as tmpdir:
        # Save configuration
        config_path = Path(tmpdir) / "formation.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Change to temp directory so outputs go there
        original_cwd = os.getcwd()
        os.chdir(tmpdir)

        try:
            print("🚀 Starting MUXI Runtime with File Generation MCP...")

            # Create and load formation
            formation = Formation()
            formation.load(str(config_path))

            # Start overlord
            overlord = formation.start_overlord()
            print("✅ Formation loaded and Overlord started")

            # Test 1: Generate a simple chart
            print("\n📊 Test 1: Generating a bar chart...")
            response1 = await overlord.chat(
                "Create a bar chart showing monthly revenue for Q1 2024: January $50k, February $65k, March $80k. Save it as revenue_chart.png",
                user_id="test-user"
            )
            print(f"Response: {response1}")

            # Test 2: Generate a data file
            print("\n📄 Test 2: Generating a JSON data file...")
            response2 = await overlord.chat(
                "Create a JSON file with sample user data including name, email, and age for 3 users",
                user_id="test-user"
            )
            print(f"Response: {response2}")

            # Test 3: Generate a CSV spreadsheet
            print("\n📊 Test 3: Generating a CSV file...")
            response3 = await overlord.chat(
                "Create a CSV file with a simple sales report: Product, Quantity, Price columns with 5 sample products",
                user_id="test-user"
            )
            print(f"Response: {response3}")

            # Check generated files
            print("\n📁 Checking generated files...")
            outputs_dir = Path(tmpdir) / "outputs"
            if outputs_dir.exists():
                files = list(outputs_dir.iterdir())
                print(f"Found {len(files)} generated files:")
                for file in files:
                    print(f"  - {file.name} ({file.stat().st_size} bytes)")
            else:
                print("No outputs directory found")

            # Cleanup
            print("\n🧹 Cleaning up...")
            formation.stop_overlord()
            formation.stop()
            print("✅ Test completed successfully!")

        finally:
            os.chdir(original_cwd)


if __name__ == "__main__":
    print("=" * 60)
    print("File Generation MCP - End-to-End Test")
    print("=" * 60)

    try:
        asyncio.run(test_file_generation())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
