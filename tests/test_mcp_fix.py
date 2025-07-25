#!/usr/bin/env python3
"""
Test if MCP stdio error is fixed with Formation-level initialization.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi import Formation  # noqa: E402


async def test_mcp_fix():
    """Test MCP error fix."""
    print("=== Testing MCP stdio fix ===")
    print("1. Creating Formation...")

    formation = Formation()

    print("2. Loading formation with MCP servers...")
    await formation.load("test-formations/formation-mcp")

    print("3. Starting overlord (MCP servers registered in Formation)...")
    overlord = await formation.start_overlord()

    print("4. Check if MCP service is available...")
    if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
        print(f"   ✅ MCP service available: {overlord.mcp_service}")
        print(f"   ✅ Registered servers: {len(overlord.mcp_service.servers)}")
    else:
        print("   ❌ No MCP service found!")

    print("\n5. Testing a simple chat...")
    response = overlord.chat("test_user", "Hello")
    print(f"   Response: {response[:100]}...")

    print("\n6. Stopping overlord...")
    await formation.stop_overlord()

    print("\n=== Test completed ===")
    print("✅ If no 'async generator' error appeared, the fix worked!")


if __name__ == "__main__":
    asyncio.run(test_mcp_fix())
