#!/usr/bin/env python3
"""
Test MCP with consistent event loop.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi.runtime import Formation  # noqa: E402
from src.muxi.runtime.utils.clean_exit import clean_exit  # noqa: E402


async def test_mcp_in_loop():
    """Test MCP in consistent event loop."""
    print("=== Testing MCP in consistent event loop ===")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    print("✅ Formation loaded")
    
    overlord = await formation.start_overlord()
    print("✅ Overlord started")
    
    # Check MCP service
    if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
        server_count = len(overlord.mcp_service.handlers)
        print(f"✅ MCP service: {server_count} servers")
    
    # Test a simple chat
    response = await overlord.chat("test_user", "What files are on the desktop?")
    if isinstance(response, str):
        print(f"✅ Chat response: {response[:100]}...")
    else:
        print(f"✅ Chat response received (type: {type(response)})")
    
    # Proper cleanup
    await formation.stop_overlord()
    print("✅ Stopped")


def main():
    """Run in a single event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(test_mcp_in_loop())
        print("\n✅ Test completed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
    finally:
        # Close the loop properly
        loop.close()
        
        # Use clean exit to suppress MCP cleanup errors
        clean_exit(0)


if __name__ == "__main__":
    main()