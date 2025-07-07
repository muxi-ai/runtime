#!/usr/bin/env python3
"""
Test MUXI-level shutdown implementation.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi.runtime import Formation  # noqa: E402


async def test_sync_shutdown():
    """Test synchronous shutdown method."""
    print("=== Testing Formation.shutdown() ===\n")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("✅ Formation and overlord started")
    print("📝 Calling formation.shutdown() for immediate shutdown...")
    
    # This will exit the process cleanly
    formation.shutdown(0)


async def test_async_shutdown():
    """Test async shutdown method."""
    print("=== Testing Formation.ashutdown() ===\n")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("✅ Formation and overlord started")
    
    # Test MCP functionality
    if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
        server_count = len(overlord.mcp_service.handlers)
        print(f"✅ MCP service active: {server_count} server(s)")
    
    print("\n📝 Calling await formation.ashutdown() for graceful shutdown...")
    
    # This will exit the process cleanly with async shutdown
    await formation.ashutdown(0)


async def test_without_shutdown():
    """Test without shutdown to show the error."""
    print("=== Testing WITHOUT shutdown (expect errors) ===\n")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("✅ Formation and overlord started")
    await formation.stop_overlord()
    print("✅ Stopped normally")
    print("\n⚠️  Exiting without shutdown - expect async generator errors below:")


if __name__ == "__main__":
    import sys
    
    # Choose which test to run
    if len(sys.argv) > 1:
        if sys.argv[1] == "sync":
            asyncio.run(test_sync_shutdown())
        elif sys.argv[1] == "async":
            asyncio.run(test_async_shutdown())
        elif sys.argv[1] == "error":
            asyncio.run(test_without_shutdown())
        else:
            print("Usage: python test_muxi_shutdown.py [sync|async|error]")
    else:
        # Default: test async shutdown
        asyncio.run(test_async_shutdown())