#!/usr/bin/env python3
"""Debug MCP response handling to understand the issue."""

import asyncio
import sys
sys.path.insert(0, ".")

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCRequest
import json
import uuid


async def test_raw_response():
    """Test raw MCP response to see what we're getting."""
    
    print("Testing raw MCP response...")
    
    # Create server parameters
    server_params = StdioServerParameters(
        command="python",
        args=["/Users/ran/Projects/muxi/code/mcp-testing-servers/stdio.py"]
    )
    
    # Start the MCP server
    async with stdio_client(server_params) as (read_stream, write_stream):
        
        # Send tools/list request manually
        request = JSONRPCRequest(
            jsonrpc="2.0",
            id=str(uuid.uuid4()),
            method="tools/list",
            params={}
        )
        message = SessionMessage(message=request)
        
        print(f"Sending message: {message}")
        await write_stream.send(message)
        
        # Read raw response
        response = await read_stream.receive()
        print(f"\nReceived response type: {type(response)}")
        print(f"Response: {response}")
        
        if hasattr(response, 'message'):
            print(f"\nMessage type: {type(response.message)}")
            print(f"Message: {response.message}")
            
            if hasattr(response.message, 'result'):
                print(f"\nResult type: {type(response.message.result)}")
                print(f"Result: {response.message.result}")
                
                # Check if result is the ListToolsResult
                if hasattr(response.message.result, 'tools'):
                    print(f"\nTools found! Count: {len(response.message.result.tools)}")
            
            # Try to access as dict
            if hasattr(response.message, '__dict__'):
                print(f"\nMessage dict: {response.message.__dict__}")


if __name__ == "__main__":
    asyncio.run(test_raw_response())