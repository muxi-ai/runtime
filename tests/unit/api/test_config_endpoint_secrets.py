"""
Test that /v1/config endpoint properly masks secrets.
"""

import pytest
from muxi.formation.server.routes.admin.config import get_formation_config
from muxi.formation.formation import Formation
from fastapi import Request
from unittest.mock import Mock, MagicMock


@pytest.mark.asyncio
async def test_config_endpoint_masks_secrets():
    """Test that /v1/config endpoint returns placeholders and masks hardcoded secrets."""
    
    # Create mock formation with test config
    formation = Mock(spec=Formation)
    formation.config = {
        "id": "test-formation",
        "name": "Test Formation",
        "server": {
            "api_keys": {
                "admin_key": "sk_muxi_admin_actual_key_12345",  # Should be masked
                "client_key": "sk_muxi_client_actual_key_67890"  # Should be masked
            }
        },
        "llm": {
            "api_keys": {
                "openai": "sk-actual-openai-key-abcdef",  # Will be restored to placeholder
                "anthropic": "sk-ant-hardcoded-key-ghijkl",  # Should be masked
                "google": "AIzaSyD-actual-google-key-mnopqr"  # Should be masked
            }
        }
    }
    
    # Mock placeholder registry (only openai has a placeholder)
    formation._secret_placeholders = {
        "llm.api_keys.openai": "${{ secrets.OPENAI_API_KEY }}"
    }
    
    # Create mock request
    request = MagicMock(spec=Request)
    request.app.state.formation = formation
    request.state.request_id = "test-request-123"
    
    # Call the endpoint
    response = await get_formation_config(request)
    
    # Parse response
    response_data = response.body.decode('utf-8')
    import json
    parsed = json.loads(response_data)
    
    assert parsed["success"] is True
    assert parsed["object"] == "formation_config"
    
    config_data = parsed["data"]
    
    # Verify OpenAI key is restored to placeholder
    assert config_data["llm"]["api_keys"]["openai"] == "${{ secrets.OPENAI_API_KEY }}"
    
    # Verify hardcoded secrets are masked
    assert config_data["server"]["api_keys"]["admin_key"] == "sk_••••••••2345"
    assert config_data["server"]["api_keys"]["client_key"] == "sk_••••••••7890"
    assert config_data["llm"]["api_keys"]["anthropic"] == "sk-••••••••jkl"
    assert config_data["llm"]["api_keys"]["google"] == "AIz••••••••pqr"


@pytest.mark.asyncio
async def test_config_endpoint_preserves_non_secrets():
    """Test that /v1/config endpoint doesn't mask non-secret values."""
    
    # Create mock formation with test config
    formation = Mock(spec=Formation)
    formation.config = {
        "id": "test-formation",
        "name": "Test Formation",
        "description": "This is a test formation",
        "version": "1.0.0",
        "server": {
            "host": "0.0.0.0",
            "port": 8080,
            "api_keys": {
                "admin_key": "short"  # Too short to mask
            }
        },
        "other_config": {
            "normal_value": "not-a-secret",
            "some_number": 42
        }
    }
    
    formation._secret_placeholders = {}
    
    # Create mock request
    request = MagicMock(spec=Request)
    request.app.state.formation = formation
    request.state.request_id = "test-request-456"
    
    # Call the endpoint
    response = await get_formation_config(request)
    
    # Parse response
    response_data = response.body.decode('utf-8')
    import json
    parsed = json.loads(response_data)
    
    config_data = parsed["data"]
    
    # Verify non-secret values are preserved
    assert config_data["description"] == "This is a test formation"
    assert config_data["server"]["host"] == "0.0.0.0"
    assert config_data["server"]["port"] == 8080
    assert config_data["server"]["api_keys"]["admin_key"] == "short"  # Too short to mask
    assert config_data["other_config"]["normal_value"] == "not-a-secret"
    assert config_data["other_config"]["some_number"] == 42


if __name__ == "__main__":
    pytest.main([__file__, "-v"])