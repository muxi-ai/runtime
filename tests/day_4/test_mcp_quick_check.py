#!/usr/bin/env python3
"""Quick MCP check with proper async API"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation.formation import Formation

async def test_mcp_quick():
    """Quick test to see what's happening with MCP"""
    print("\n=== Quick MCP Check ===")
    
    try:
        # Load formation with MCP enabled
        formation = Formation()
        await formation.load("test-formations/formation-mcp")
        print("✓ Formation loaded")
        
        # Check configured services
        if hasattr(formation, 'configured_services'):
            mcp_service = formation.configured_services.get('mcp_service')
            if mcp_service:
                print(f"✓ MCP service found in configured_services")
                if hasattr(mcp_service, 'servers'):
                    print(f"  Servers: {list(mcp_service.servers.keys())}")
            else:
                print("❌ No MCP service in configured_services")
        
        # Start overlord
        print("\nStarting overlord...")
        overlord = await formation.start_overlord()
        print("✓ Overlord started")
        
        # Check overlord's MCP service
        if hasattr(overlord, 'mcp_service'):
            print(f"✓ MCP service found on overlord")
            mcp = overlord.mcp_service
            
            # Check handlers
            if hasattr(mcp, 'handlers'):
                print(f"\nMCP handlers: {list(mcp.handlers.keys())}")
            
            # Check tool registry
            if hasattr(mcp, 'tool_registry'):
                print(f"\nTool registry:")
                for server_id, tools in mcp.tool_registry.items():
                    tool_count = len(tools) if isinstance(tools, dict) else 0
                    print(f"  {server_id}: {tool_count} tools")
        else:
            print("❌ No MCP service on overlord")
        
        # Quick test
        print("\nTesting a simple query...")
        response_gen = await overlord.chat(
            "List available tools",
            user_id="user1", 
            use_async=False
        )
        
        # Collect first part of response
        response = ""
        count = 0
        async for chunk in response_gen:
            response += chunk
            count += 1
            if count > 5:  # Just get first few chunks
                break
                
        print(f"\nResponse preview: {response[:200]}...")
        
        # Clean shutdown
        print("\nShutting down...")
        await formation.stop_overlord()
        print("✓ Shutdown complete")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_quick())
    sys.exit(0 if success else 1)