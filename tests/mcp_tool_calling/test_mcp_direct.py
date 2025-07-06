#!/usr/bin/env python3
"""Test MCP directly without formation"""

import asyncio
import sys
import json

sys.path.insert(0, ".")

from src.muxi.runtime.services.mcp.service import MCPService
from src.muxi.runtime.services.llm import LLM


async def main():
    # Initialize MCP service
    mcp_service = MCPService.get_instance()
    
    # Register a simple filesystem MCP server
    print("Registering filesystem MCP server...")
    try:
        await mcp_service.register_mcp_server(
            server_id="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            request_timeout=10
        )
        print("✅ MCP server registered successfully")
    except Exception as e:
        print(f"❌ Failed to register MCP server: {e}")
        return
    
    # List available tools
    print("\nListing available tools...")
    tools = await mcp_service.list_tools()
    print(f"Available tools from {len(tools)} servers:")
    for server_id, server_tools in tools.items():
        print(f"\n{server_id}: {len(server_tools)} tools")
        for tool_name in list(server_tools.keys())[:3]:
            print(f"  - {tool_name}")
    
    # Test tool invocation directly
    print("\n\nTesting direct tool invocation...")
    try:
        result = await mcp_service.invoke_tool(
            server_id="filesystem",
            tool_name="write_file",
            params={
                "path": "/tmp/test_mcp.txt",
                "content": "Hello from direct MCP test!"
            }
        )
        print(f"✅ Tool invocation result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"❌ Tool invocation failed: {e}")
    
    # Clean up
    await mcp_service.unregister_server("filesystem")
    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(main())