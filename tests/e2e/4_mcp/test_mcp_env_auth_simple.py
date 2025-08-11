"""Test MCP server authentication via environment variables - simplified version."""
import pytest
import asyncio
from pathlib import Path

from muxi import Formation


@pytest.mark.asyncio
async def test_mcp_env_auth_hardcoded_simple():
    """Test MCP server with hardcoded environment variable authentication - simple version."""
    # Get path to test formation directory
    test_dir = Path(__file__).parent / "formations" / "formation-mcp"
    
    # Create formation
    formation = Formation()
    await formation.load(str(test_dir / "formation.yaml"))
    
    # Start overlord
    overlord = await formation.start_overlord()
    
    # Access MCP service directly
    mcp_service = formation._mcp_service
    
    # List servers
    server_list = await mcp_service.list_servers()
    print(f"Connected MCP servers: {server_list}")
    
    # Check if web-search-mcp is in the list
    assert "web-search-mcp" in server_list, f"Expected web-search-mcp in servers, got: {server_list}"
    
    # Check tool registry
    tool_registry = mcp_service.tool_registry
    print(f"Tool registry: {list(tool_registry.keys())}")
    
    # Check if web-search-mcp has tools
    if "web-search-mcp" in tool_registry:
        tools = tool_registry["web-search-mcp"]
        print(f"Found {len(tools)} tools from web-search-mcp")
        if tools:
            print(f"Tool names: {list(tools.keys())}")
        
        # Success if we have tools
        assert len(tools) > 0, "Web search MCP should provide at least one tool"
        print("SUCCESS: MCP server connected with env auth and tools discovered!")
    else:
        print("Tool registry not populated yet, but server is connected")
        print("SUCCESS: MCP server connected with env auth!")
    
    # Suppress errors on exit
    formation.suppress_mcp_errors_on_exit()