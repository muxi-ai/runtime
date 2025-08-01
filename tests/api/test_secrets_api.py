"""
Test secrets API endpoints with visible output.
"""

import pytest
import tempfile
import os
import yaml
import json
from fastapi.testclient import TestClient

from muxi.formation.formation import Formation
from muxi.formation.server.app import create_app
from muxi.services.secrets.secrets_manager import SecretsManager


@pytest.mark.asyncio
async def test_secrets_api_operations():
    """Test all secrets API operations with visible output."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a formation config that uses a secret
        formation_config = {
            "id": "test-formation",
            "name": "Test Formation",
            "schema": "1.0.0",
            "description": "Test formation for secrets API",
            "overlord": {
                "model": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "api_key": "${{ secrets.OPENAI_API_KEY }}"
                }
            },
            "llm": {
                "api_keys": {
                    "openai": "${{ secrets.OPENAI_API_KEY }}"
                },
                "models": [
                    {
                        "name": "gpt-4",
                        "provider": "openai",
                        "capabilities": ["text"]
                    }
                ]
            }
        }
        
        # Write formation config
        config_path = os.path.join(tmpdir, "formation.yaml")
        with open(config_path, "w") as f:
            yaml.dump(formation_config, f)
            
        # Create secrets manager and store initial secrets
        secrets_manager = SecretsManager(tmpdir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("OPENAI_API_KEY", "sk-initial-key")
        await secrets_manager.store_secret("EXISTING_SECRET", "existing-value")
        
        # Create and load formation
        formation = Formation()
        await formation.load(config_path)
        
        # Create FastAPI app and test client
        app = await create_app(formation)
        client = TestClient(app)
        
        # Set up admin API key header
        headers = {"X-API-Key": "test-admin-key"}
        
        print("\n" + "="*60)
        print("SECRETS API TEST - SHOWING ALL RESPONSES")
        print("="*60)
        
        # 1. LIST SECRETS
        print("\n1. LIST SECRETS (GET /v1/secrets)")
        print("-" * 40)
        response = client.get("/v1/secrets", headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "secrets" in data
        assert data["count"] == 2
        assert "OPENAI_API_KEY" in data["secrets"]
        assert "EXISTING_SECRET" in data["secrets"]
        
        # 2. ADD NEW SECRET
        print("\n2. ADD NEW SECRET (POST /v1/secrets)")
        print("-" * 40)
        new_secret = {"key": "SOME_SECRET", "value": "test"}
        print(f"Request Body: {json.dumps(new_secret, indent=2)}")
        response = client.post("/v1/secrets", json=new_secret, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 201
        
        # Verify it was added
        print("\n   Verifying secret was added...")
        response = client.get("/v1/secrets", headers=headers)
        data = response.json()["data"]
        assert data["count"] == 3
        assert "SOME_SECRET" in data["secrets"]
        print(f"   ✓ Secret count is now {data['count']}")
        
        # 3. UPDATE SECRET
        print("\n3. UPDATE SECRET (PUT /v1/secrets/SOME_SECRET)")
        print("-" * 40)
        update_data = {"value": "test1"}
        print(f"Request Body: {json.dumps(update_data, indent=2)}")
        response = client.put("/v1/secrets/SOME_SECRET", json=update_data, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 200
        
        # 4. TRY TO DELETE SECRET IN USE
        print("\n4. TRY TO DELETE SECRET IN USE (DELETE /v1/secrets/OPENAI_API_KEY)")
        print("-" * 40)
        response = client.delete("/v1/secrets/OPENAI_API_KEY", headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 409  # Conflict - secret in use
        assert response.json()["error"]["code"] == "SECRET_IN_USE"
        
        # 5. DELETE UNUSED SECRET
        print("\n5. DELETE UNUSED SECRET (DELETE /v1/secrets/SOME_SECRET)")
        print("-" * 40)
        response = client.delete("/v1/secrets/SOME_SECRET", headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 200
        
        # Verify it was deleted
        print("\n   Verifying secret was deleted...")
        response = client.get("/v1/secrets", headers=headers)
        data = response.json()["data"]
        assert data["count"] == 2
        assert "SOME_SECRET" not in data["secrets"]
        print(f"   ✓ Secret count is now {data['count']}")
        print(f"   ✓ SOME_SECRET is no longer in the list")
        
        # 6. BONUS: Try operations on non-existent secret
        print("\n6. BONUS TESTS - ERROR HANDLING")
        print("-" * 40)
        
        print("\n   a) Update non-existent secret:")
        response = client.put("/v1/secrets/DOES_NOT_EXIST", json={"value": "test"}, headers=headers)
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 404
        
        print("\n   b) Delete non-existent secret:")
        response = client.delete("/v1/secrets/DOES_NOT_EXIST", headers=headers)
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 404
        
        print("\n   c) Create duplicate secret:")
        response = client.post("/v1/secrets", json={"key": "EXISTING_SECRET", "value": "duplicate"}, headers=headers)
        print(f"   Status Code: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 409
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED! ✓")
        print("="*60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_secrets_api_operations())