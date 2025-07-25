#!/usr/bin/env python3
"""Minimal MCP test"""

import asyncio
import sys
import os

sys.path.insert(0, ".")

from src.muxi.formation.formation import Formation  # noqa: E402


async def main():
    # Set environment variables
    os.environ["MUXI_ASYNC_PROCESSING_ENABLED"] = "false"
    os.environ["MUXI_LOG_LEVEL"] = "DEBUG"

    # Create minimal formation dict
    formation_dict = {
        "name": "test-mcp",
        "version": "1.0.0",
        "agents": [{
            "id": "test_agent",
            "model": "openai/gpt-4o-mini"
        }],
        "mcp": {
            "servers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@mcp-servers/filesystem"],
                    "env": {
                        "MCP_FILESYSTEM_ROOT": "/tmp"
                    }
                }
            }
        }
    }

    print("Creating formation...")
    formation = Formation()
    formation._load_from_dict(formation_dict)

    print("Starting overlord...")
    overlord = await formation.start_overlord()

    print("Waiting for startup...")
    await overlord.ensure_started()

    print("Sending message...")
    response = await overlord.chat(
        user_id="test_user",
        message="Please create a file at /tmp/hello.txt with the content 'Hello MCP!'",
        use_async=False,
        stream=False,
    )

    print(f"\nResponse: {response}")

    test_file = "/tmp/hello.txt"

    # Check if file was created
    try:
        if os.path.exists(test_file):
            with open(test_file, "r") as f:
                content = f.read()
            print(f"\n✅ SUCCESS! File created with content: {content}")
        else:
            print("\n❌ FAILED: File was not created")
    finally:
        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)
    await formation.stop_overlord(5.0)
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
