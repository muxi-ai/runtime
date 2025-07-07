#!/usr/bin/env python3
"""Check GitHub MCP tools for gist-specific functionality"""

import sys
sys.path.insert(0, '.')
import asyncio

from src.muxi.runtime.formation import Formation

async def test_github_gist_tools():
    """Check GitHub MCP for gist-specific tools"""
    print("\n=== GitHub Gist Tools Check ===")
    
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
        print(f"\nFound GitHub MCP server: {github_server.server_id}")
        print(f"Total tools: {len(github_server.tools)}")
        
        # Look for gist-related tools
        print("\nSearching for gist-related tools:")
        gist_tools = []
        for tool_name, tool_info in github_server.tools.items():
            if "gist" in tool_name.lower() or "gist" in str(tool_info.get("description", "")).lower():
                gist_tools.append((tool_name, tool_info))
                print(f"\n  Tool: {tool_name}")
                print(f"  Description: {tool_info.get('description', 'No description')[:200]}")
        
        if not gist_tools:
            print("\n  No gist-specific tools found!")
            
        # List all tools that might create content
        print("\n\nAll content creation tools:")
        for tool_name, tool_info in github_server.tools.items():
            desc = str(tool_info.get("description", "")).lower()
            if any(word in desc for word in ["create", "file", "content", "repository"]):
                print(f"\n  Tool: {tool_name}")
                print(f"  Description: {tool_info.get('description', 'No description')[:200]}")
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(test_github_gist_tools())