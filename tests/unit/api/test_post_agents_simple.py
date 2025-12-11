"""
Test POST /agents endpoint with various payloads - simplified version.
"""

import pytest
import tempfile
import os
import yaml
import json
from fastapi.testclient import TestClient

from muxi.formation import Formation  # noqa: E402
from muxi.formation.server.server import FormationServer
from muxi.services.secrets.secrets_manager import SecretsManager


def get_base_config():
    """Get base formation configuration."""
    return {
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
                {"text": "test/model"}
            ]
        },
        "agents": []
    }


@pytest.mark.asyncio
async def test_post_agents_empty_payload():
    """Test POST /agents with empty payload - should fail with validation errors."""

    print("\n📝 Test: POST /agents with empty payload")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(get_base_config(), f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with empty payload
        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json={}
        )

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

    print("\n📝 Test: POST /agents with required fields only")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(get_base_config(), f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
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
async def test_post_agents_with_invalid_secret():
    """Test POST /agents with invalid secret reference - should fail."""

    print("\n📝 Test: POST /agents with invalid secret reference")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(get_base_config(), f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
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
        assert len(validation_errors) > 0
        assert validation_errors[0]["type"] == "MISSING_SECRETS"
        assert any("INVALID" in secret["name"] for secret in validation_errors[0]["missing"])

        print("✅ Invalid secret reference correctly rejected")


@pytest.mark.asyncio
async def test_post_agents_with_valid_secret():
    """Test POST /agents with valid secret reference - should succeed."""

    print("\n📝 Test: POST /agents with valid secret reference")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create secrets
        secrets_manager = SecretsManager(tmpdir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("OPENAI_API_KEY", "sk-valid-key-123")

        # Create config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(get_base_config(), f)

        # Create and load formation with secrets
        os.environ["MUXI_SECRETS_DIR"] = tmpdir
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
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

        # Clean up
        del os.environ["MUXI_SECRETS_DIR"]


@pytest.mark.asyncio
async def test_post_agents_with_all_fields():
    """Test POST /agents with all supported fields."""

    print("\n📝 Test: POST /agents with all fields")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create secrets
        secrets_manager = SecretsManager(tmpdir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("AGENT_KEY", "sk-test-123")

        # Create config
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(get_base_config(), f)

        # Create and load formation
        os.environ["MUXI_SECRETS_DIR"] = tmpdir
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Make request with all fields
        payload = {
            "schema": "1.0.0",
            "id": "full-agent",
            "name": "Full Test Agent",
            "description": "Agent with all fields",
            "active": True,
            "author": "Test Author",
            "url": "https://example.com",
            "license": "MIT",
            "version": "1.0.0",
            "system_message": "You are a test agent",
            "llm_models": [
                {
                    "text": "openai/gpt-4",
                    "api_key": "${{ secrets.AGENT_KEY }}"
                }
            ],
            "mcp_servers": [
                {"id": "test-server"}
            ],
            "knowledge": [
                {
                    "type": "file",
                    "path": "/test.md",
                    "description": "Test knowledge"
                }
            ],
            "a2a": {
                "can_receive_broadcast": True
            }
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] == "full-agent"
        assert data["data"]["author"] == "Test Author"
        assert data["data"]["license"] == "MIT"
        assert len(data["data"]["llm_models"]) == 1

        print("✅ Agent created successfully with all fields")

        # Clean up
        del os.environ["MUXI_SECRETS_DIR"]


@pytest.mark.asyncio
async def test_post_agents_duplicate_id():
    """Test POST /agents with duplicate ID - should fail."""

    print("\n📝 Test: POST /agents with duplicate ID")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config with existing agent
        config = get_base_config()
        config["agents"] = [{
            "schema": "1.0.0",
            "id": "existing-agent",
            "name": "Existing Agent",
            "description": "Already exists"
        }]

        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Try to create agent with same ID
        payload = {
            "schema": "1.0.0",
            "id": "existing-agent",
            "name": "Duplicate Agent",
            "description": "Should fail"
        }

        response = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Assertions
        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "AGENT_EXISTS"

        print("✅ Duplicate agent ID correctly rejected")


@pytest.mark.asyncio
async def test_post_agents_add_same_agent_twice():
    """Test POST /agents adding the same agent twice - should fail on second attempt."""

    print("\n📝 Test: POST /agents adding same agent twice")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config with no existing agents
        config_path = os.path.join(tmpdir, "formation.afs")
        with open(config_path, "w") as f:
            yaml.dump(get_base_config(), f)

        # Create and load formation
        formation = Formation()
        await formation.load(config_path)

        # Create server and app
        server = FormationServer(formation)
        app = server._create_app()
        client = TestClient(app)

        # Agent payload
        payload = {
            "schema": "1.0.0",
            "id": "test-agent-duplicate",
            "name": "Test Agent",
            "description": "Testing duplicate creation"
        }

        # First attempt - should succeed
        print("\n🚀 First attempt to create agent...")
        response1 = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print(f"Status: {response1.status_code}")
        print(f"Response: {json.dumps(response1.json(), indent=2)}")

        # Assertions for first attempt
        assert response1.status_code == 201
        data1 = response1.json()
        assert data1["success"] is True
        assert data1["data"]["id"] == "test-agent-duplicate"
        print("✅ First agent creation succeeded")

        # Second attempt with exact same payload - should fail
        print("\n🚫 Second attempt to create same agent...")
        response2 = client.post(
            "/v1/agents",
            headers={"X-Muxi-Admin-Key": "test-admin-key"},
            json=payload
        )

        print(f"Status: {response2.status_code}")
        print(f"Response: {json.dumps(response2.json(), indent=2)}")

        # Assertions for second attempt
        assert response2.status_code == 409
        data2 = response2.json()
        assert data2["success"] is False
        assert data2["error"]["code"] == "AGENT_EXISTS"
        assert "test-agent-duplicate" in data2["error"]["message"]

        print("✅ Second agent creation correctly rejected")


if __name__ == "__main__":
    import asyncio

    # Run tests
    asyncio.run(test_post_agents_empty_payload())
    asyncio.run(test_post_agents_required_fields_only())
    asyncio.run(test_post_agents_with_invalid_secret())
    asyncio.run(test_post_agents_with_valid_secret())
    asyncio.run(test_post_agents_with_all_fields())
    asyncio.run(test_post_agents_duplicate_id())
    asyncio.run(test_post_agents_add_same_agent_twice())
