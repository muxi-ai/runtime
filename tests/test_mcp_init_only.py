#!/usr/bin/env python3
"""
Test MCP initialization only.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi.runtime import Formation  # noqa: E402


async def test_mcp_init():
    """Test MCP initialization without chat."""
    print("Starting MCP init test...")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    print("✅ Formation loaded")
    
    overlord = await formation.start_overlord()
    print("✅ Overlord started")
    
    # Check MCP service
    if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
        # Use handlers instead of servers
        server_count = len(overlord.mcp_service.handlers)
        print(f"✅ MCP service: {server_count} servers")
        for server_id in overlord.mcp_service.handlers:
            conn = overlord.mcp_service.connections.get(server_id, {})
            print(f"  - {server_id}: {conn.get('transport_type', 'command')}")
    
    print("\nStopping...")
    await formation.stop_overlord()
    print("✅ Done")


if __name__ == "__main__":
    # Run normally to allow proper cleanup
    try:
        asyncio.run(test_mcp_init())
    except Exception as e:
        print(f"Error: {e}")