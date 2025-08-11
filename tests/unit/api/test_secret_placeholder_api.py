"""
Integration tests for secret placeholder restoration in API endpoints.

Tests ensure that no actual secret values are exposed through API responses.
"""

import pytest
import httpx
from pathlib import Path
import tempfile
import yaml
import json
import os

from muxi.formation import Formation
from muxi.formation.server import FormationServer


@pytest.fixture
async def formation_with_secrets():
    """Create a formation with various secret configurations."""
    formation_config = {
        "id": "test-secrets-formation",
        "name": "Test Secrets Formation",
        "description": "Formation for testing secret placeholder restoration",
        "schema": "1.0.0",
        "version": "1.0.0",
        "llm": {
            "provider": "openai",
            "model": "gpt-4",
            "models": [
                {
                    "name": "gpt-4",
                    "provider": "openai",
                    "capabilities": ["text", "vision"]
                }
            ],
            "api_keys": {
                "openai": "${{ secrets.OPENAI_API_KEY }}",
                "backup": "direct-key-should-not-show"
            },
            "capabilities": {
                "vision": True,
                "function_calling": True,
                "streaming": True
            }
        },
        "server": {
            "host": "127.0.0.1",
            "port": 8080,
            "api_keys": {
                "admin_key": "${{ secrets.ADMIN_KEY }}",
                "client_key": "${{ secrets.CLIENT_KEY }}"
            }
        },
        "agents": [
            {
                "id": "agent1",
                "name": "Test Agent",
                "description": "Agent with secrets",
                "model": {
                    "provider": "anthropic",
                    "model": "claude-3",
                    "api_key": "${{ secrets.AGENT_API_KEY }}"
                }
            }
        ],
        "mcp": {
            "servers": [
                {
                    "id": "test-server",
                    "name": "Test MCP Server",
                    "description": "Test MCP server for API tests",
                    "type": "command",
                    "command": "test-mcp",
                    "env": {
                        "API_TOKEN": "${{ secrets.MCP_TOKEN }}",
                        "OTHER_VAR": "not-a-secret"
                    }
                }
            ]
        },
        "overlord": {
            "persona": "Test overlord",
            "api_key": "${{ secrets.OVERLORD_KEY }}"
        }
    }
    
    # Create temp directory and files
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write formation config
        config_path = Path(temp_dir) / "formation.yaml"
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)
        
        # Create secrets file
        secrets_path = Path(temp_dir) / "secrets.enc"
        secrets = {
            "OPENAI_API_KEY": "actual-openai-key-12345",
            "ADMIN_KEY": "actual-admin-key-67890",
            "CLIENT_KEY": "actual-client-key-abcde",
            "AGENT_API_KEY": "actual-agent-key-fghij",
            "MCP_TOKEN": "actual-mcp-token-klmno",
            "OVERLORD_KEY": "actual-overlord-key-pqrst",
            "USER_CREDENTIALS_USER_KEY": "actual-user-key-uvwxy"
        }
        # Save as JSON (unencrypted for testing)
        with open(secrets_path, "w") as f:
            json.dump(secrets, f)
        
        # Create mock secrets manager
        class MockSecretsManager:
            async def get_secret(self, key):
                return secrets.get(key, f"missing-{key}")
            
            def get_secret_sync(self, key):
                return secrets.get(key, f"missing-{key}")
        
        # Create and load formation with mock secrets
        formation = Formation()
        formation.secrets_manager = MockSecretsManager()
        await formation.load(str(config_path))
        
        # Start server
        server = FormationServer(formation)
        await server.start_server()
        
        yield formation, server
        
        # Cleanup
        await server.stop_server()


@pytest.mark.asyncio
async def test_formation_endpoint_no_secrets(formation_with_secrets):
    """Test that /v1/formation endpoint returns placeholders, not actual secrets."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/formation",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check LLM secrets
        llm_config = data["data"]["llm"]
        assert llm_config["api_keys"]["openai"] == "${{ secrets.OPENAI_API_KEY }}"
        assert "actual-openai-key" not in str(data)
        
        # Direct keys should not be exposed
        assert "direct-key-should-not-show" not in str(data)
        
        # Check server secrets
        server_config = data["data"]["server"]
        assert server_config["api_keys"]["admin_key"] == "${{ secrets.ADMIN_KEY }}"
        assert server_config["api_keys"]["client_key"] == "${{ secrets.CLIENT_KEY }}"
        assert "actual-admin-key" not in str(data)
        assert "actual-client-key" not in str(data)


@pytest.mark.asyncio
async def test_llm_settings_endpoint_no_secrets(formation_with_secrets):
    """Test that /v1/llm/settings endpoint returns placeholders."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/llm/settings",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that secrets are restored to placeholders
        api_keys = data["data"]["api_keys"]
        assert api_keys["openai"] == "${{ secrets.OPENAI_API_KEY }}"
        assert "actual-openai-key" not in str(data)


@pytest.mark.asyncio
async def test_agents_list_endpoint_no_secrets(formation_with_secrets):
    """Test that /v1/agents endpoint returns placeholders in agent configs."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/agents",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check agent secrets
        agents = data["data"]["agents"]
        assert len(agents) > 0
        agent = agents[0]
        assert agent["model"]["api_key"] == "${{ secrets.AGENT_API_KEY }}"
        assert "actual-agent-key" not in str(data)


@pytest.mark.asyncio
async def test_individual_agent_endpoint_no_secrets(formation_with_secrets):
    """Test that /v1/agents/{id} endpoint returns placeholders."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/agents/agent1",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check agent secrets
        agent = data["data"]
        assert agent["model"]["api_key"] == "${{ secrets.AGENT_API_KEY }}"
        assert "actual-agent-key" not in str(data)


@pytest.mark.asyncio
async def test_mcp_servers_endpoint_no_secrets(formation_with_secrets):
    """Test that /v1/mcp/servers endpoint returns placeholders."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/mcp/servers",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check MCP server secrets
        servers = data["data"]
        assert len(servers) > 0
        server_config = servers[0]
        assert server_config["env"]["API_TOKEN"] == "${{ secrets.MCP_TOKEN }}"
        assert server_config["env"]["USER_KEY"] == "${{ user.credentials.USER_KEY }}"
        assert "actual-mcp-token" not in str(data)
        assert "actual-user-key" not in str(data)


@pytest.mark.asyncio
async def test_overlord_endpoint_no_secrets(formation_with_secrets):
    """Test that /v1/overlord endpoint returns placeholders."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/overlord",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check overlord secrets
        overlord_config = data["data"]
        assert overlord_config["api_key"] == "${{ secrets.OVERLORD_KEY }}"
        assert "actual-overlord-key" not in str(data)


@pytest.mark.asyncio
async def test_config_endpoint_summary_no_secrets(formation_with_secrets):
    """Test that /v1/config endpoint doesn't expose secrets in summary."""
    formation, server = formation_with_secrets
    base_url = f"http://127.0.0.1:{server.port}"
    admin_key = formation.config["server"]["api_keys"]["admin_key"]
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/v1/config",
            headers={"X-Muxi-Admin-Key": admin_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Config endpoint returns summary, not full config
        # But ensure no secrets leak through
        assert "actual-" not in str(data)
        assert "direct-key-should-not-show" not in str(data)