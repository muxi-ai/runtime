"""Test MCP server authentication via environment variables."""
import pytest
import os
import asyncio
from pathlib import Path

from muxi import Formation
from muxi.utils.user_dirs import get_user_dir


@pytest.mark.asyncio
async def test_mcp_env_auth_hardcoded():
    """Test MCP server with hardcoded environment variable authentication."""
    # Get path to test formation directory
    test_dir = Path(__file__).parent / "formations" / "formation-mcp"
    
    try:
        # Create formation
        formation = Formation()
        await formation.load(str(test_dir / "formation.yaml"))
        
        # Start overlord
        overlord = await formation.start_overlord()
        
        # List available MCP servers
        servers = await formation.list_mcp_servers()
        assert "web-search-mcp" in servers, f"Expected web-search-mcp in servers, got: {list(servers.keys())}"
        
        # Check that the server is connected
        server_info = servers["web-search-mcp"]
        assert server_info["connected"], "Web search MCP server should be connected"
        
        # List tools - web search should provide search tool
        tools = await formation.list_mcp_tools()
        web_search_tools = tools.get("web-search-mcp", [])
        
        # Check that we have at least one tool (search)
        assert len(web_search_tools) > 0, "Web search MCP should provide at least one tool"
        
        # Just having tools is success - we don't need to test the actual search
        print(f"SUCCESS: Found {len(web_search_tools)} tools from web-search-mcp")
        if web_search_tools:
            print(f"Available tools: {[t['name'] for t in web_search_tools]}")
        
    finally:
        # Clean up
        if 'formation' in locals() and hasattr(formation, 'stop'):
            await formation.stop()
        pass  # Formation doesn't have cleanup method


@pytest.mark.asyncio
async def test_mcp_env_auth_secrets():
    """Test MCP server with environment variables from secrets."""
    # Get path to test formation directory
    test_dir = Path(__file__).parent / "formations" / "formation-mcp"
    
    # Create a modified version of web-search.yaml that uses secrets
    web_search_yaml = test_dir / "mcp" / "web-search.yaml"
    web_search_secrets_yaml = test_dir / "mcp" / "web-search-secrets.yaml"
    
    # Read original content
    original_content = web_search_yaml.read_text()
    
    # Modify to use secrets
    secrets_content = original_content.replace(
        'BRAVE_API_KEY: "BSAhY6DecKH5SF6pE5FEr-jagPAl_gF"',
        'BRAVE_API_KEY: "${{ secrets.BRAVE_API_KEY }}"'
    )
    
    # Write modified content
    web_search_secrets_yaml.write_text(secrets_content)
    
    try:
        # Create formation with secrets
        formation = Formation()
        
        # Set up secrets before loading
        formation.secrets = {
            "BRAVE_API_KEY": "BSAhY6DecKH5SF6pE5FEr-jagPAl_gF"
        }
        
        await formation.load(test_dir / "formation.yaml")
        
        # Start overlord
        overlord = await formation.start_overlord()
        
        # List available MCP servers - should still work with secrets
        servers = await overlord.list_mcp_servers()
        assert "web-search-mcp" in servers or "web-search-secrets-mcp" in servers
        
        # Get the actual server name (might be modified)
        server_name = "web-search-mcp" if "web-search-mcp" in servers else "web-search-secrets-mcp"
        server_info = servers[server_name]
        assert server_info["connected"], "Web search MCP server should be connected"
        
        # List tools
        tools = await overlord.list_mcp_tools()
        web_search_tools = tools.get(server_name, [])
        assert len(web_search_tools) > 0, "Web search MCP should provide tools"
        
    finally:
        # Clean up
        if 'formation' in locals() and hasattr(formation, 'stop'):
            await formation.stop()
        pass  # Formation doesn't have cleanup method
        # Remove temporary file
        if web_search_secrets_yaml.exists():
            web_search_secrets_yaml.unlink()


@pytest.mark.asyncio
async def test_mcp_env_auth_user_credentials():
    """Test MCP server with environment variables from user credentials."""
    # Get path to test formation directory
    test_dir = Path(__file__).parent / "formations" / "formation-mcp"
    
    # Create a modified version that uses user credentials
    web_search_yaml = test_dir / "mcp" / "web-search.yaml"
    web_search_user_yaml = test_dir / "mcp" / "web-search-user.yaml"
    
    # Read original content
    original_content = web_search_yaml.read_text()
    
    # Modify to use user credentials
    user_content = original_content.replace(
        'BRAVE_API_KEY: "BSAhY6DecKH5SF6pE5FEr-jagPAl_gF"',
        'BRAVE_API_KEY: "${{ user.credentials.BRAVE_SEARCH }}"'
    )
    
    # Write modified content
    web_search_user_yaml.write_text(user_content)
    
    try:
        # Create formation
        formation = Formation()
        await formation.load(str(test_dir / "formation.yaml"))
        
        # Set up user credentials using the credential store
        from muxi.services.secrets import UserCredentialStore
        
        # Get user directory
        user_dir = get_user_dir(f"users/test_user")
        
        # Initialize credential store
        cred_store = UserCredentialStore(str(user_dir))
        await cred_store.initialize()
        
        # Store user credential
        await cred_store.store_credential(
            "test_user",
            "BRAVE_SEARCH",
            "BSAhY6DecKH5SF6pE5FEr-jagPAl_gF"
        )
        
        # Set the credential store in formation
        formation._user_credential_store = cred_store
        
        # Start overlord
        overlord = await formation.start_overlord()
        
        # Test with user-specific credentials
        response = await overlord.chat(
            "Can you search for information about Python?",
            user_id="test_user"
        )
        
        assert response is not None
        
        # The MCP server should be available for this user
        servers = await overlord.list_mcp_servers()
        assert any("web-search" in name for name in servers.keys())
        
    finally:
        # Clean up
        if 'formation' in locals() and hasattr(formation, 'stop'):
            await formation.stop()
        pass  # Formation doesn't have cleanup method
        if 'cred_store' in locals():
            await cred_store.cleanup()
        # Remove temporary file
        if web_search_user_yaml.exists():
            web_search_user_yaml.unlink()


@pytest.mark.asyncio
async def test_mcp_env_auth_multiple_vars():
    """Test that multiple environment variables are passed correctly."""
    from muxi.services.mcp.transports.command import CommandLineTransport
    
    # Test the transport directly
    auth_config = {
        "type": "env",
        "BRAVE_API_KEY": "test_key",
        "DUMMY_KEY": "DUMMY_VALUE",
        "ANOTHER_VAR": "another_value"
    }
    
    # Create transport with env auth
    transport = CommandLineTransport(
        command="echo",
        args=["test"],
        auth=auth_config,
        request_timeout=30
    )
    
    # Check that all env vars were added (except 'type')
    assert "BRAVE_API_KEY" in transport.env
    assert transport.env["BRAVE_API_KEY"] == "test_key"
    assert "DUMMY_KEY" in transport.env
    assert transport.env["DUMMY_KEY"] == "DUMMY_VALUE"
    assert "ANOTHER_VAR" in transport.env
    assert transport.env["ANOTHER_VAR"] == "another_value"
    assert "type" not in transport.env  # 'type' should be excluded
    
    # Test merging with existing env vars
    existing_env = {"EXISTING_VAR": "existing_value"}
    transport2 = CommandLineTransport(
        command="echo",
        args=["test"],
        env=existing_env,
        auth=auth_config,
        request_timeout=30
    )
    
    # Check that both existing and auth env vars are present
    assert "EXISTING_VAR" in transport2.env
    assert transport2.env["EXISTING_VAR"] == "existing_value"
    assert "BRAVE_API_KEY" in transport2.env
    assert transport2.env["BRAVE_API_KEY"] == "test_key"
    assert "DUMMY_KEY" in transport2.env
    assert transport2.env["DUMMY_KEY"] == "DUMMY_VALUE"