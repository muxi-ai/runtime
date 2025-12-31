"""
Test POST /agents endpoint with various payloads.
"""

import pytest
import tempfile
import os
import yaml
import json
from fastapi.testclient import TestClient

from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.formation.server.server import FormationServer
from muxi.runtime.services.secrets.secrets_manager import SecretsManager


@pytest.mark.asyncio
async def test_post_agents_empty_payload():
    """Test POST /agents with empty payload - should fail with validation errors."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal formation config
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for POST agents",
            "server": {
                "api_keys": {
                    "admin_key": "test-admin-key",
                    "client_key": "test-client-key"
                }
            }
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create test client
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with empty payload
        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json={}
        )

        print("\n📝 Test: POST /agents with empty payload")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_PARAMS"
        assert "validation_errors" in data["error"]["data"]

        # Check for required fields
        validation_errors = data["error"]["data"]["validation_errors"]
        required_fields = {"schema", "id", "name", "description"}
        error_fields = {error["field"] for error in validation_errors}
        assert required_fields.issubset(error_fields)

        print("✅ Empty payload correctly rejected with validation errors")


@pytest.mark.asyncio
async def test_post_agents_required_fields_only():
    """Test POST /agents with only required fields - should succeed."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal formation config
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for POST agents",
            "server": {
                "api_keys": {
                    "admin_key": "test-admin-key",
                    "client_key": "test-client-key"
                }
            }
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create test client
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with only required fields
        payload = {
            "schema": "1.0.0",
            "id": "test-agent",
            "name": "Test Agent",
            "description": "A test agent with minimal fields"
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print("\n📝 Test: POST /agents with required fields only")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["error"] is None
        assert data["data"]["id"] == "test-agent"
        assert data["data"]["name"] == "Test Agent"
        assert data["data"]["active"] is True  # Default value
        assert data["data"]["source"] == "api"

        print("✅ Agent created successfully with required fields only")


@pytest.mark.asyncio
async def test_post_agents_all_fields():
    """Test POST /agents with all fields - should succeed."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create secrets for testing
        secrets_manager = SecretsManager(tmpdir)
        await secrets_manager.initialize()
        await secrets_manager.set_secret("AGENT_OPENAI_KEY", "sk-test123")
        await secrets_manager.set_secret("USER_CREDENTIALS_GITHUB", "ghp_test123")

        # Create formation config
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for POST agents",
            "server": {
                "api_keys": {
                    "admin_key": "test-admin-key",
                    "client_key": "test-client-key"
                }
            },
            "llm": {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "capabilities": ["text"]
                    }
                ]
            },
            "agents": []  # Start with empty agents list
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create and load formation with secrets
        os.environ["MUXI_SECRETS_DIR"] = tmpdir
        formation = Formation()
        await formation.load(config_path)

        # Create test client
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with all fields
        payload = {
            "schema": "1.0.0",
            "id": "advanced-agent",
            "name": "Advanced Test Agent",
            "description": "A fully configured test agent",
            "active": True,
            "author": "Test Author <test@example.com>",
            "url": "https://example.com/agent",
            "license": "MIT",
            "version": "1.2.3",
            "system_message": "You are an advanced test agent with all capabilities.",
            "llm_models": [
                {
                    "text": "openai/gpt-4",
                    "api_key": "${{ secrets.AGENT_OPENAI_KEY }}",
                    "settings": {
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                },
                {
                    "vision": "openai/gpt-4-vision-preview",
                    "api_key": "${{ secrets.AGENT_OPENAI_KEY }}"
                }
            ],
            "mcp_servers": [
                {
                    "id": "filesystem",
                    "auth": {
                        "type": "none"
                    }
                }
            ],
            "knowledge": [
                {
                    "type": "file",
                    "path": "/docs/api.md",
                    "description": "API documentation"
                }
            ],
            "a2a": {
                "can_receive_broadcast": True,
                "can_send_to": ["agent1", "agent2"],
                "can_receive_from": ["agent3"]
            }
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print("\n📝 Test: POST /agents with all fields")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["error"] is None

        # Check all fields were saved
        agent_data = data["data"]
        assert agent_data["id"] == "advanced-agent"
        assert agent_data["name"] == "Advanced Test Agent"
        assert agent_data["author"] == "Test Author <test@example.com>"
        assert agent_data["version"] == "1.2.3"
        assert len(agent_data["llm_models"]) == 2
        assert agent_data["llm_models"][0]["text"] == "openai/gpt-4"
        assert agent_data["a2a"]["can_receive_broadcast"] is True

        print("✅ Agent created successfully with all fields")


@pytest.mark.asyncio
async def test_post_agents_with_extra_fields():
    """Test POST /agents with required fields + random extra fields - should ignore extras."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create formation config
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for POST agents",
            "server": {
                "api_keys": {
                    "admin_key": "test-admin-key",
                    "client_key": "test-client-key"
                }
            },
            "llm": {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "capabilities": ["text"]
                    }
                ]
            },
            "agents": []  # Start with empty agents list
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create test client
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with required fields + extra fields
        payload = {
            "schema": "1.0.0",
            "id": "test-agent-extra",
            "name": "Test Agent with Extras",
            "description": "Agent with extra fields that should be ignored",
            "random_field": "should be ignored",
            "nested_random": {
                "also": "ignored"
            },
            "array_random": ["ignored", "too"]
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print("\n📝 Test: POST /agents with required + random fields")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["error"] is None

        # Check that random fields were not saved
        agent_data = data["data"]
        assert "random_field" not in agent_data
        assert "nested_random" not in agent_data
        assert "array_random" not in agent_data

        print("✅ Agent created successfully, extra fields ignored")


@pytest.mark.asyncio
async def test_post_agents_invalid_secret():
    """Test POST /agents with invalid secret reference - should fail."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create formation config
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for POST agents",
            "server": {
                "api_keys": {
                    "admin_key": "test-admin-key",
                    "client_key": "test-client-key"
                }
            },
            "llm": {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "capabilities": ["text"]
                    }
                ]
            },
            "agents": []  # Start with empty agents list
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create and load formation (no secrets manager)
        formation = Formation()
        await formation.load(config_path)

        # Create test client
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with invalid secret reference
        payload = {
            "schema": "1.0.0",
            "id": "test-agent-bad-secret",
            "name": "Test Agent with Bad Secret",
            "description": "Agent with invalid secret reference",
            "llm_models": [
                {
                    "text": "openai/gpt-4",
                    "api_key": "${{ secrets.INVALID }}"
                }
            ]
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print("\n📝 Test: POST /agents with invalid secret reference")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_REQUEST"
        assert "validation_errors" in data["error"]["data"]

        # Check for specific error about INVALID secret
        validation_errors = data["error"]["data"]["validation_errors"]
        assert any("INVALID" in error["message"] for error in validation_errors)

        print("✅ Invalid secret reference correctly rejected")


@pytest.mark.asyncio
async def test_post_agents_valid_secret():
    """Test POST /agents with valid secret reference - should succeed."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create secrets for testing
        secrets_manager = SecretsManager()
        await secrets_manager.initialize(tmpdir)
        await secrets_manager.set_secret("OPENAI_API_KEY", "sk-valid-key-123")

        # Create formation config
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for POST agents",
            "server": {
                "api_keys": {
                    "admin_key": "test-admin-key",
                    "client_key": "test-client-key"
                }
            },
            "llm": {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "capabilities": ["text"]
                    }
                ]
            },
            "agents": []  # Start with empty agents list
        }

        # Write formation config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)

        # Create and load formation with secrets
        os.environ["MUXI_SECRETS_DIR"] = tmpdir
        formation = Formation()
        await formation.load(config_path)

        # Create test client
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with valid secret reference
        payload = {
            "schema": "1.0.0",
            "id": "test-agent-good-secret",
            "name": "Test Agent with Valid Secret",
            "description": "Agent with valid secret reference",
            "llm_models": [
                {
                    "text": "openai/gpt-4",
                    "api_key": "${{ secrets.OPENAI_API_KEY }}",
                    "settings": {
                        "temperature": 0.5
                    }
                }
            ]
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print("\n📝 Test: POST /agents with valid secret reference")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["error"] is None

        # Check that secret reference is preserved (not exposed)
        agent_data = data["data"]
        assert agent_data["llm_models"][0]["api_key"] == "${{ secrets.OPENAI_API_KEY }}"

        print("✅ Agent created successfully with valid secret reference")


if __name__ == "__main__":
    import asyncio

    # Run all tests
    asyncio.run(test_post_agents_empty_payload())
    asyncio.run(test_post_agents_required_fields_only())
    asyncio.run(test_post_agents_all_fields())
    asyncio.run(test_post_agents_with_extra_fields())
    asyncio.run(test_post_agents_invalid_secret())
    asyncio.run(test_post_agents_valid_secret())
