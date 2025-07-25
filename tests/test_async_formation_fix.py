#!/usr/bin/env python3
"""
Test script to verify that async Formation fixes the MCP stdio error.

This test creates a Formation with MCP servers using the new async API
to check if the error is eliminated.

NOTE: It turns out overlord.chat() is already async, so we can't keep
it synchronous as originally planned.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi import Formation  # noqa: E402


async def test_async_formation_mcp():
    """Test MCP with async Formation API."""
    print("=" * 60)
    print("Testing Async Formation MCP Fix")
    print("=" * 60)

    formation = Formation()

    # Load configuration - now async
    print("\n1. Loading formation configuration (async)...")
    await formation.load("test-formations/formation-mcp")
    print("   ✅ Formation loaded")

    # Start overlord - now async, MCP connections created here
    print("\n2. Starting overlord (async - MCP connections created)...")
    overlord = await formation.start_overlord()
    print("   ✅ Overlord started")
    print(f"   Overlord instance: {overlord}")

    # Test using the overlord - chat is async too!
    print("\n3. Testing async chat with MCP tools...")
    try:
        response = await overlord.chat("test_user", "List the allowed directories for file operations")
        print(f"   ✅ Chat response: {response[:200]}...")
    except Exception as e:
        print(f"   ❌ Chat error: {e}")

    # Clean shutdown - now async
    print("\n4. Stopping overlord (async)...")
    await formation.stop_overlord()
    print("   ✅ Overlord stopped")

    print("\n" + "=" * 60)
    print("TEST COMPLETE - Check above for MCP async generator errors")
    print("If no 'async generator cleanup' error appeared, the fix worked!")
    print("=" * 60)


if __name__ == "__main__":
    print("Starting test with async Formation...")
    print("This test should NOT show the MCP async generator cleanup error.\n")

    # Run the test in a single event loop
    asyncio.run(test_async_formation_mcp())

    print("\nTest finished. No clean_exit() needed with async Formation!")
