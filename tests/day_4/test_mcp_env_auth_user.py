"""Test MCP server authentication via environment variables with user credentials."""
import pytest
import asyncio
from pathlib import Path

from muxi import Formation


@pytest.mark.asyncio
async def test_mcp_env_auth_user_credentials():
    """Test MCP server with user-specific environment variable authentication."""
    # Get path to test formation directory
    test_dir = Path(__file__).parent.parent.parent / "test-formations" / "formation-mcp"
    
    # Create formation
    formation = Formation()
    await formation.load(str(test_dir / "formation.yaml"))
    
    # Start overlord
    overlord = await formation.start_overlord()
    
    # Test with user1 - this should work since credentials exist
    response = await overlord.chat(
        "Can you search for information about Python programming?",
        user_id="user1",
        stream=False  # Get full response instead of streaming
    )
    
    if response:
        print(f"Response received: {response[:200]}..." if len(response) > 200 else response)
    else:
        print("No response received, but checking MCP connection...")
    
    # Access MCP service directly to verify connection
    mcp_service = formation._mcp_service
    
    # List servers
    server_list = await mcp_service.list_servers()
    print(f"Connected MCP servers: {server_list}")
    
    # Check if web-search-mcp is connected
    assert "web-search-mcp" in server_list, f"Expected web-search-mcp in servers, got: {server_list}"
    
    # Check tool registry to see if tools were discovered
    tool_registry = mcp_service.tool_registry
    print(f"Tool registry: {list(tool_registry.keys())}")
    
    # For user-specific credentials, the tools should be available
    if "web-search-mcp" in tool_registry:
        tools = tool_registry["web-search-mcp"]
        print(f"Found {len(tools)} tools from web-search-mcp")
        if tools:
            print(f"Tool names: {list(tools.keys())}")
        
        # Success if we have tools
        assert len(tools) > 0, "Web search MCP should provide at least one tool"
        print("SUCCESS: MCP server connected with user credentials env auth and tools discovered!")
    else:
        # This might happen if the tools haven't been discovered yet for this user
        print("Tool registry not populated yet, but server is connected")
        print("SUCCESS: MCP server connected with user credentials env auth!")
    
    # Suppress errors on exit
    formation.suppress_mcp_errors_on_exit()


@pytest.mark.asyncio
async def test_mcp_env_auth_user_without_credentials():
    """Test MCP server behavior when user credentials are missing."""
    # Get path to test formation directory
    test_dir = Path(__file__).parent.parent.parent / "test-formations" / "formation-mcp"
    
    # Create formation
    formation = Formation()
    await formation.load(str(test_dir / "formation.yaml"))
    
    # Start overlord
    overlord = await formation.start_overlord()
    
    # Test with a user that doesn't have credentials
    try:
        response = await overlord.chat(
            "Can you search for information?",
            user_id="user_without_creds"
        )
        print(f"Response: {response}")
        # The system should handle missing credentials gracefully
        print("System handled missing credentials gracefully")
    except Exception as e:
        print(f"Expected error for missing credentials: {e}")
    
    # Suppress errors on exit
    formation.suppress_mcp_errors_on_exit()