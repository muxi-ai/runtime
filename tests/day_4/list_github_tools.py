#!/usr/bin/env python3
"""List all GitHub MCP tools"""

import sys
sys.path.insert(0, '.')
import asyncio
import json

from src.muxi.runtime.formation import Formation

async def list_github_tools():
    """List all GitHub MCP tools"""
    print("\n=== GitHub MCP Tools List ===")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    
    # Get MCP service
    mcp_service = formation.get_service("mcp_service")
    
    # Get GitHub MCP server
    github_server = None
    for server_id, server in mcp_service.mcp_servers.items():
        if "github" in server_id:
            github_server = server
            break
    
    if github_server:
        print(f"\nGitHub MCP server: {github_server.server_id}")
        print(f"Total tools: {len(github_server.tools)}")
        print("\n" + "="*80)
        
        # List all tools sorted by name
        tools_list = sorted(github_server.tools.items())
        
        for i, (tool_name, tool_info) in enumerate(tools_list, 1):
            print(f"\n{i}. {tool_name}")
            desc = tool_info.get('description', 'No description')
            # Wrap long descriptions
            if len(desc) > 100:
                print(f"   {desc[:100]}...")
                print(f"   {desc[100:200]}..." if len(desc) > 200 else f"   {desc[100:]}")
            else:
                print(f"   {desc}")
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(list_github_tools())