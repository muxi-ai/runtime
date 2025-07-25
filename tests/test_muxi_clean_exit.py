#!/usr/bin/env python3
"""
Test MUXI-level clean_exit implementation.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi import Formation  # noqa: E402


async def test_sync_shutdown():
    """Test synchronous shutdown method."""
    print("=== Testing Formation.shutdown() ===\n")

    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()

    print("✅ Formation and overlord started")
    print("📝 Calling formation.clean_exit() for clean shutdown...")

    # This will exit the process cleanly
    formation.clean_exit(0)


async def test_async_clean_exit():
    """Test async clean_exit method."""
    print("=== Testing Formation.aclean_exit() ===\n")

    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()

    print("✅ Formation and overlord started")

    # Test MCP functionality
    if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
        server_count = len(overlord.mcp_service.handlers)
        print(f"✅ MCP service active: {server_count} server(s)")

    print("\n📝 Calling await formation.aclean_exit() for clean async shutdown...")

    # This will exit the process cleanly with async shutdown
    await formation.aclean_exit(0)


async def test_without_clean_exit():
    """Test without clean_exit to show the error."""
    print("=== Testing WITHOUT clean_exit (expect errors) ===\n")

    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()

    print("✅ Formation and overlord started")
    await formation.stop_overlord()
    print("✅ Stopped normally")
    print("\n⚠️  Exiting without clean_exit - expect async generator errors below:")


if __name__ == "__main__":
    import sys

    # Choose which test to run
    if len(sys.argv) > 1:
        if sys.argv[1] == "sync":
            asyncio.run(test_sync_clean_exit())
        elif sys.argv[1] == "async":
            asyncio.run(test_async_clean_exit())
        elif sys.argv[1] == "error":
            asyncio.run(test_without_clean_exit())
        else:
            print("Usage: python test_muxi_clean_exit.py [sync|async|error]")
    else:
        # Default: test async clean exit
        asyncio.run(test_async_clean_exit())
