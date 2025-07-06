#!/usr/bin/env python3
"""Simple test to verify MCP tools are being passed to LLM"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_test():
    """Run the test."""
    formation_path = Path("test-formations/formation-mcp")
    
    # Load formation
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()
    
    # Wait for overlord to be ready
    await overlord.ensure_started()
    
    # Get MCP service and list tools
    mcp_service = overlord.get_mcp_service()
    tools = await mcp_service.list_tools()
    
    print(f"\nAvailable MCP servers and tools:")
    for server_id, server_tools in tools.items():
        print(f"\n{server_id}: {len(server_tools)} tools")
        for tool in server_tools[:3]:
            print(f"  - {tool['name']}: {tool.get('description', '')[:60]}...")
    
    # Simple test
    print("\n\nTesting simple file operation...")
    response = await overlord.chat(
        user_id="test_user", 
        message="Please create a file at /Users/ran/Desktop/test_from_mcp.txt with the content 'Hello from MCP tools!'",
        use_async=False,
        stream=False,
    )
    
    print(f"\nResponse type: {type(response)}")
    print(f"Response: {response}")
    
    # Check if file was created
    test_file = Path("/Users/ran/Desktop/test_from_mcp.txt")
    if test_file.exists():
        print(f"\n✅ Success! File created with content: {test_file.read_text()}")
        test_file.unlink()  # Clean up
    else:
        print("\n❌ File was not created")
    
    # Stop overlord
    formation.stop_overlord(10.0)
    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(run_test())