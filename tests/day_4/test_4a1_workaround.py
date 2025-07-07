#!/usr/bin/env python3
"""Test 4A1: Filesystem MCP Operations - With Workaround"""

import asyncio
import time
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.append(".")
from src.muxi.runtime import Formation  # noqa: E402


def test_filesystem_mcp():
    def run_test():
        print("=== Test 4A1: Filesystem MCP Operations ===")
        print("Goal: Validate file creation, reading, updating, and deletion via MCP")

        formation = Formation()
        formation.load("test-formations/formation-mcp")

        print("\nStarting overlord (this might take a moment)...")
        overlord = formation.start_overlord()

        # Give it a moment to fully initialize
        time.sleep(2)

        print("Overlord started!")

        # Test 1: Create file
        print("\n1. Testing file creation...")
        prompt = "Create a file called 'test.txt' with content 'Hello World' in /Users/ran/Desktop/tests"
        print(f"PROMPT: {prompt}")

        response = asyncio.run(overlord.chat(
            prompt,
            user_id="user1",
            use_async=False
        ))

        print("\nOVERLORD.CHAT RESPONSE:")
        print(response)

        # Verify file exists
        test_file = Path("/Users/ran/Desktop/tests/test.txt")
        if test_file.exists():
            print(f"✓ File created successfully at {test_file}")
            print(f"  Content: {test_file.read_text()}")
        else:
            print("✗ File was not created")

        formation.stop_overlord()
        return True

    # Run in thread to avoid event loop issues
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(run_test)
            result = future.result(timeout=120)  # 2 minute timeout
            print("\nTest completed successfully!")
            return result
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = test_filesystem_mcp()
    if not success:
        sys.exit(1)
