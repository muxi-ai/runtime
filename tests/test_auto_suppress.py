#!/usr/bin/env python3
"""
Test automatic MCP error suppression.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi.runtime import Formation  # noqa: E402


async def test_auto_suppression():
    """Test that MCP errors are automatically suppressed."""
    print("=== Testing Automatic MCP Error Suppression ===\n")
    
    formation = Formation()
    
    # Load formation with MCP servers
    await formation.load("test-formations/formation-mcp")
    print("✅ Formation loaded")
    
    # Start overlord - this will auto-register suppression
    overlord = await formation.start_overlord()
    print("✅ Overlord started (auto-suppression registered)")
    
    # Check MCP servers
    if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
        server_count = len(overlord.mcp_service.handlers)
        print(f"✅ MCP service: {server_count} stdio server(s)")
    
    # Normal shutdown
    await formation.stop_overlord()
    print("✅ Stopped normally")
    
    print("\n✨ Exiting - errors should be auto-suppressed!")
    print("   (No explicit clean_exit needed)")


if __name__ == "__main__":
    asyncio.run(test_auto_suppression())
    # Normal exit - atexit handler will suppress errors