#!/usr/bin/env python3
"""Quick MCP test to see what's happening"""

import asyncio
import sys
import os

sys.path.insert(0, ".")

from src.muxi.formation.formation import Formation  # noqa: E402


async def main():
    # Set environment variables to reduce timeouts
    os.environ["MUXI_ASYNC_PROCESSING_ENABLED"] = "false"
    os.environ["MUXI_LOG_LEVEL"] = "DEBUG"

    # Create test directory if needed
    test_dir = "/tmp/muxi_test_mcp"
    os.makedirs(test_dir, exist_ok=True)

    print("Loading formation...")
    formation = Formation()
    formation.load("test-formations/formation-mcp")

    print("Starting overlord...")
    overlord = formation.start_overlord()

    print("Waiting for startup...")
    await overlord.ensure_started()

    # Check what tools are available
    if hasattr(overlord, "mcp_service"):
        print("\nChecking MCP tools...")
        tools = overlord.mcp_service.tool_registry
        print(f"Available tools: {list(tools.keys())}")
        for server, server_tools in tools.items():
            print(f"\n{server}:")
            for tool_name in list(server_tools.keys())[:3]:
                print(f"  - {tool_name}")

    print("\nSending message...")
    response = await overlord.chat(
        user_id="test_user",
        message=f"Please create a file at {test_dir}/hello.txt with the content 'Hello MCP!'",
        use_async=False,
        stream=False,
    )

    print(f"\nResponse: {response}")

    # Check if file was created
    test_file = f"{test_dir}/hello.txt"
    if os.path.exists(test_file):
        with open(test_file, "r") as f:
            content = f.read()
        print(f"\n✅ SUCCESS! File created with content: {content}")
        os.remove(test_file)
    else:
        print("\n❌ FAILED: File was not created")

    formation.stop_overlord(5.0)
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
