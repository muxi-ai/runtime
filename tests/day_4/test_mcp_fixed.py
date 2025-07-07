#!/usr/bin/env python3
"""Test MCP with proper error suppression"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation.formation import Formation

async def test_mcp_with_suppression():
    """Test MCP servers with error suppression enabled"""
    print("\n=== Test MCP with Error Suppression ===")
    
    # Create formation and enable error suppression
    formation = Formation()
    formation.suppress_mcp_errors_on_exit()  # Enable before loading
    
    # Load formation
    await formation.load("test-formations/formation-mcp")
    print("✓ Formation loaded")
    
    # Start overlord
    overlord = await formation.start_overlord()
    print("✓ Overlord started")
    
    # Quick test
    print("\nTesting a simple query...")
    response_gen = await overlord.chat(
        "What MCP tools are available?",
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        if len(response) > 200:
            break
            
    print(f"Response preview: {response[:200]}...")
    
    # Check MCP service
    if hasattr(overlord, 'mcp_service'):
        mcp = overlord.mcp_service
        print(f"\nMCP servers connected: {list(mcp.handlers.keys())}")
        
    # Graceful shutdown
    print("\nShutting down...")
    await formation.stop_overlord()
    print("✓ Shutdown complete")
    
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_mcp_with_suppression())
        print("\n✅ Test completed successfully")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)