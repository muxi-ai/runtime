#!/usr/bin/env python3
"""Direct test of MCP server to verify it's working correctly."""

import asyncio
import sys
sys.path.insert(0, ".")

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
import json


async def test_mcp_directly():
    """Test MCP server directly using the MCP SDK."""
    
    print("Testing MCP server directly...")
    
    # Create server parameters
    server_params = StdioServerParameters(
        command="python",
        args=["/Users/ran/Projects/muxi/code/mcp-testing-servers/stdio.py"]
    )
    
    # Start the MCP server and create a session
    async with stdio_client(server_params) as (read_stream, write_stream):
        
        # Create an MCP client session
        async with ClientSession(read_stream, write_stream) as client:
            
            # Initialize the connection
            await client.initialize()
            
            # List tools using the client
            tools_response = await client.list_tools()
            
            print(f"Tools response type: {type(tools_response)}")
            print(f"Tools response: {tools_response}")
            
            # If tools_response has attributes
            if hasattr(tools_response, '__dict__'):
                print(f"Tools response attributes: {tools_response.__dict__}")
            
            # Try to access tools directly
            if hasattr(tools_response, 'tools'):
                print(f"Number of tools: {len(tools_response.tools)}")
                for tool in tools_response.tools:
                    print(f"Tool: {tool}")


if __name__ == "__main__":
    asyncio.run(test_mcp_directly())