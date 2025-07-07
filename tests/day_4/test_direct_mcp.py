#!/usr/bin/env python3
"""Test MCP servers directly without going through chat"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation.formation import Formation

async def test_direct_mcp():
    """Test MCP servers directly"""
    print("\n=== Direct MCP Test ===")
    
    # Load formation
    formation = Formation()
    await formation.load("test-formations/formation-mcp") 
    overlord = await formation.start_overlord()
    
    # Get MCP service
    mcp_service = overlord.mcp_service
    
    print("\nTesting System MCP directly...")
    try:
        result = await mcp_service.call_tool(
            server_id="system-mcp",
            tool_name="sys_info", 
            arguments={"info_type": "cpu"}
        )
        print(f"✓ System MCP works: {result}")
    except Exception as e:
        print(f"❌ System MCP error: {e}")
    
    print("\nTesting Filesystem MCP directly...")
    try:
        result = await mcp_service.call_tool(
            server_id="filesystem-mcp",
            tool_name="list_allowed_directories",
            arguments={}
        )
        print(f"✓ Filesystem MCP works: {result}")
    except Exception as e:
        print(f"❌ Filesystem MCP error: {e}")
        
    print("\nTesting Linear MCP directly...")
    try:
        # Try a simple list operation
        result = await mcp_service.call_tool(
            server_id="linear-mcp",
            tool_name="list_issues",
            arguments={"first": 1}  # Just get 1 issue
        )
        print(f"✓ Linear MCP works: {result}")
    except Exception as e:
        print(f"❌ Linear MCP error: {e}")
        
    print("\nTesting GitHub MCP directly...")
    try:
        # Try listing gists
        result = await mcp_service.call_tool(
            server_id="github-mcp",
            tool_name="list_gists",
            arguments={"perPage": 1}  # Just get 1 gist
        )
        print(f"✓ GitHub MCP works: {result}")
    except Exception as e:
        print(f"❌ GitHub MCP error: {e}")
    
    # Cleanup
    await formation.stop_overlord()
    
    return True

if __name__ == "__main__":
    try:
        asyncio.run(test_direct_mcp())
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)