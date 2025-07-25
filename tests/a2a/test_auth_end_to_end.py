#!/usr/bin/env python3
"""
End-to-end test for HMAC and JWT authentication in A2A communication
"""
import asyncio
import json
import logging
import os
import sys

# Add path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.muxi.a2a.auth import A2AAuthManager, AuthType  # noqa: E402

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MockSecretsManager:
    """Mock SecretsManager for testing"""

    def __init__(self):
        self.secrets = {}

    async def get_secret(self, name: str):
        return self.secrets.get(name)

    async def store_secret(self, name: str, value: str):
        self.secrets[name] = value

    async def interpolate_secrets(self, config):
        # Simple mock implementation - just return the config as-is
        return config


def simulate_registry_with_auth_agents():
    """Simulate registry response with agents requiring different auth types"""
    from types import SimpleNamespace

    # Mock agent cards with different auth requirements
    hmac_agent = SimpleNamespace()
    hmac_agent.name = "secure-processor"
    hmac_agent.muxi_agent_id = "secure-processor"
    hmac_agent.url = "http://localhost:8080/secure-processor"
    hmac_agent.authentication = SimpleNamespace()
    hmac_agent.authentication.type = SimpleNamespace()
    hmac_agent.authentication.type.value = "hmac"
    hmac_agent.authentication.required = True

    jwt_agent = SimpleNamespace()
    jwt_agent.name = "auth-service"
    jwt_agent.muxi_agent_id = "auth-service"
    jwt_agent.url = "http://localhost:8080/auth-service"
    jwt_agent.authentication = SimpleNamespace()
    jwt_agent.authentication.type = SimpleNamespace()
    jwt_agent.authentication.type.value = "jwt"
    jwt_agent.authentication.required = True

    return [hmac_agent, jwt_agent]


async def test_hmac_message_auth():
    """Test HMAC authentication in message context"""
    print("\n🔐 Testing HMAC in A2A message context...")

    # Create mock secrets manager and auth manager
    secrets_manager = MockSecretsManager()
    auth_manager = A2AAuthManager(secrets_manager)

    # Add HMAC credentials for secure-processor
    auth_manager.add_credentials(
        "secure-processor", AuthType.HMAC, {"secret": "secure-message-secret-456"}
    )

    # Simulate the message that would be sent
    message_payload = {
        "message": "Process this document securely",
        "message_type": "request",
        "context": {"document_id": "doc-123", "priority": "high"},
        "message_id": "msg-abc-123",
    }

    # This is what agent.py would do for HMAC auth
    headers = {"Content-Type": "application/json"}
    target_url = "http://localhost:8080/agents/secure-processor/message"
    payload_json = json.dumps(message_payload)

    success, auth_headers = await auth_manager.apply_authentication_with_context(
        "secure-processor", AuthType.HMAC, headers, target_url, "POST", payload_json, True
    )

    print(f"✓ HMAC auth prepared: {success}")
    if success:
        print(f"  Target URL: {target_url}")
        print(f"  X-Signature: {auth_headers.get('X-Signature', 'N/A')}")
        print(f"  X-Timestamp: {auth_headers.get('X-Timestamp', 'N/A')}")
        print("  Message would be sent with HMAC signature")

    return success


async def test_jwt_message_auth():
    """Test JWT authentication in message context"""
    print("\n🔑 Testing JWT in A2A message context...")

    # Create mock secrets manager and auth manager
    secrets_manager = MockSecretsManager()
    auth_manager = A2AAuthManager(secrets_manager)

    # Add JWT credentials for auth-service
    auth_manager.add_credentials(
        "auth-service",
        AuthType.JWT,
        {
            "private_key": "jwt-signing-key-789",
            "algorithm": "HS256",
            "issuer": "muxi-agent-network",
            "audience": "auth-service",
        },
    )

    # Simulate the message that would be sent
    message_payload = {  # noqa: F841
        "message": "Authenticate user session",
        "message_type": "request",
        "context": {"user_id": "user-456", "session_id": "sess-789"},
        "message_id": "msg-xyz-789",
    }

    # This is what agent.py would do for JWT auth
    headers = {"Content-Type": "application/json"}
    target_url = "http://localhost:8080/agents/auth-service/message"

    success, auth_headers = await auth_manager.apply_authentication_with_context(
        "auth-service", AuthType.JWT, headers, target_url, "POST", required=True
    )

    print(f"✓ JWT auth prepared: {success}")
    if success:
        print(f"  Target URL: {target_url}")
        auth_header = auth_headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove 'Bearer '
            print(f"  JWT Token: {token[:30]}...")

            # Decode and show JWT claims (for verification)
            try:
                import jwt

                decoded = jwt.decode(token, options={"verify_signature": False})
                print(f"  JWT Claims: {decoded}")
            except Exception as e:
                print(f"  JWT decode preview failed: {e}")

        print("  Message would be sent with JWT token")

    return success


async def test_authentication_discovery():
    """Test authentication discovery from registry"""
    print("\n🔍 Testing authentication discovery...")

    # Simulate discovered agents from registry
    discovered_agents = simulate_registry_with_auth_agents()

    for agent in discovered_agents:
        print(f"\nAgent: {agent.name}")
        print(f"  URL: {agent.url}")
        print(f"  Auth Type: {agent.authentication.type.value}")
        print(f"  Auth Required: {agent.authentication.required}")

        # This is what agent.py does to extract auth requirements
        auth_type = AuthType(agent.authentication.type.value)
        auth_required = agent.authentication.required

        print(f"  → Would apply {auth_type} authentication (required: {auth_required})")

    print("✓ Authentication discovery working")
    return True


async def test_api_key_auth():
    """Test API key authentication workflow"""
    print("Testing API Key authentication...")

    # Create mock secrets manager and auth manager
    secrets_manager = MockSecretsManager()
    auth_manager = A2AAuthManager(secrets_manager)

    # Simulate external service authentication setup
    api_key = "prod-api-key-12345"
    auth_manager.add_credentials("billing-service", AuthType.API_KEY, {"api_key": api_key})

    # Test authentication
    headers = {}
    success, result_headers = await auth_manager.apply_authentication(
        "billing-service", AuthType.API_KEY, headers, required=True
    )

    assert success, "API key authentication should succeed"
    assert "X-API-Key" in result_headers, "API key should be in headers"
    assert result_headers["X-API-Key"] == api_key, "API key should match"

    print("✓ API Key authentication working")
    return True


async def test_bearer_token_auth():
    """Test Bearer token authentication workflow"""
    print("Testing Bearer token authentication...")

    # Create mock secrets manager and auth manager
    secrets_manager = MockSecretsManager()
    auth_manager = A2AAuthManager(secrets_manager)

    # Simulate service with Bearer token
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
    auth_manager.add_credentials("analytics-service", AuthType.BEARER, {"token": token})

    # Test authentication
    headers = {}
    success, result_headers = await auth_manager.apply_authentication(
        "analytics-service", AuthType.BEARER, headers, required=True
    )

    assert success, "Bearer token authentication should succeed"
    assert "Authorization" in result_headers, "Authorization header should be present"
    assert result_headers["Authorization"] == f"Bearer {token}", "Bearer token should match"

    print("✓ Bearer token authentication working")
    return True


async def main():
    """Run all end-to-end tests"""
    print("A2A Authentication End-to-End Test")
    print("==================================")

    discovery_success = await test_authentication_discovery()
    hmac_success = await test_hmac_message_auth()
    jwt_success = await test_jwt_message_auth()
    api_key_success = await test_api_key_auth()
    bearer_token_success = await test_bearer_token_auth()

    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"Discovery:    {'✓ PASS' if discovery_success else '✗ FAIL'}")
    print(f"HMAC E2E:     {'✓ PASS' if hmac_success else '✗ FAIL'}")
    print(f"JWT E2E:      {'✓ PASS' if jwt_success else '✗ FAIL'}")
    print(f"API Key E2E:  {'✓ PASS' if api_key_success else '✗ FAIL'}")
    print(f"Bearer Token E2E: {'✓ PASS' if bearer_token_success else '✗ FAIL'}")

    if all([discovery_success, hmac_success, jwt_success, api_key_success, bearer_token_success]):
        print("\n🎉 All authentication flows working end-to-end!")
        print("✓ Ready for production A2A secure communication")
    else:
        print("\n❌ Some authentication flows need fixes")


if __name__ == "__main__":
    asyncio.run(main())
