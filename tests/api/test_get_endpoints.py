#!/usr/bin/env python3
"""Test GET endpoints for Formation API Server"""

import asyncio
import pytest
import httpx
import json
import os

# Set up environment variables before importing Formation
os.environ["MUXI_SECRETS_OPENAI_API_KEY"] = "test-api-key"
os.environ["MUXI_SECRETS_ANTHROPIC_API_KEY"] = "test-api-key"
os.environ["MUXI_SECRETS_GEMINI_API_KEY"] = "test-api-key"
os.environ["MUXI_SECRETS_LINEAR_MCP_TOKEN"] = "test-token"
os.environ["MUXI_SECRETS_BRAVE_API_KEY"] = "test-api-key"
os.environ["MUXI_SECRETS_FIRECRAWL_API_KEY"] = "test-api-key"

from muxi import Formation


@pytest.mark.asyncio
async def test_get_endpoints():
    """Test all GET endpoints that return configuration sections"""
    
    # Create formation instance
    formation = Formation()
    
    # Load the test formation
    await formation.load("test-formations/formation-multi-agent")
    
    # Start server non-blocking
    server = await formation.start_server(block=False)
    
    # Wait for server to start
    await asyncio.sleep(2)
    
    # Get the actual port from the server
    port = server.port
    base_url = f"http://127.0.0.1:{port}/v1"
    
    # Get the admin key from formation
    admin_key = formation._api_keys.get("admin", "")
    headers = {"X-Muxi-Admin-Key": admin_key}
    
    # Define endpoints to test
    endpoints = [
        ("/overlord", "overlord configuration"),
        ("/overlord/persona", "overlord persona"),
        ("/mcp", "MCP configuration"),
        ("/llm/settings", "LLM settings"),
        ("/logging", "logging configuration"),
        ("/memory", "memory configuration"),
        ("/async", "async settings"),
        ("/scheduler", "scheduler configuration"),
        ("/a2a", "A2A configuration")
    ]
    
    async with httpx.AsyncClient() as client:
        for endpoint, description in endpoints:
            print(f"\n{'='*60}")
            print(f"Testing GET {endpoint} - {description}")
            print(f"{'='*60}")
            
            try:
                response = await client.get(f"{base_url}{endpoint}", headers=headers)
                print(f"Status: {response.status_code}")
                
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                
                data = response.json()
                
                # Verify response structure
                assert "success" in data, "Missing 'success' field"
                assert data["success"] is True, "Request was not successful"
                assert "data" in data, "Missing 'data' field"
                assert "error" in data, "Missing 'error' field"
                assert data["error"] is None, "Unexpected error in response"
                assert "timestamp" in data, "Missing 'timestamp' field"
                assert "type" in data, "Missing 'type' field"
                assert "object" in data, "Missing 'object' field"
                
                print(f"✓ Response structure valid")
                print(f"✓ Type: {data['type']}")
                print(f"✓ Object: {data['object']}")
                
                # Print the actual data returned
                print(f"\nData returned:")
                print(json.dumps(data['data'], indent=2))
                
                # Specific checks for certain endpoints
                if endpoint == "/overlord/persona":
                    assert "persona" in data['data'], "Missing persona in response"
                    print(f"✓ Persona: {data['data']['persona'][:50]}...")
                
            except Exception as e:
                print(f"✗ Failed: {e}")
                raise
    
    # Stop server
    await server.stop()
    print("\n✓ Server stopped successfully")


@pytest.mark.asyncio  
async def test_authentication():
    """Test that endpoints require proper authentication"""
    
    # Create formation instance
    formation = Formation()
    
    # Load the test formation
    await formation.load("test-formations/formation-multi-agent")
    
    # Start server non-blocking
    server = await formation.start_server(block=False)
    
    # Wait for server to start
    await asyncio.sleep(2)
    
    port = server.port
    base_url = f"http://127.0.0.1:{port}/v1"
    
    async with httpx.AsyncClient() as client:
        # Test without auth header
        print("\nTesting without authentication...")
        response = await client.get(f"{base_url}/overlord")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Correctly rejected request without auth")
        
        # Test with wrong auth header
        print("\nTesting with invalid authentication...")
        headers = {"X-Muxi-Admin-Key": "wrong_key"}
        response = await client.get(f"{base_url}/overlord", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Correctly rejected request with invalid auth")
        
        # Test with client key on admin endpoint
        print("\nTesting with client key on admin endpoint...")
        client_key = formation._api_keys.get("client", "")
        headers = {"X-Muxi-Client-Key": client_key}
        response = await client.get(f"{base_url}/overlord", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Correctly rejected client key on admin endpoint")
    
    # Stop server
    await server.stop()
    print("\n✓ Authentication tests passed")


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_get_endpoints())
    asyncio.run(test_authentication())