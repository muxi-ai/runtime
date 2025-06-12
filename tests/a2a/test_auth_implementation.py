#!/usr/bin/env python3
"""
Simple test to verify HMAC and JWT authentication implementations
"""
import sys
import os
import asyncio

# Add path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.muxi.runtime.a2a.auth import A2AAuthManager, AuthType  # noqa: E402


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


async def test_hmac_auth():
    """Test HMAC authentication"""
    print("Testing HMAC authentication...")

    # Create mock secrets manager
    secrets_manager = MockSecretsManager()
    auth_manager = A2AAuthManager(secrets_manager)

    # Add HMAC credentials
    auth_manager.add_credentials("test-agent", AuthType.HMAC, {"secret": "test-secret"})
    print("✓ HMAC credentials added")

    # Test HMAC authentication
    headers = {"Content-Type": "application/json"}
    success, result_headers = await auth_manager.apply_authentication_with_context(
        "test-agent",
        AuthType.HMAC,
        headers,
        "http://test.com/endpoint",
        "POST",
        '{"test": "data"}',
        True,
    )

    print(f"HMAC Auth Success: {success}")
    if success:
        hmac_headers = {k: v for k, v in result_headers.items() if k.startswith("X-")}
        for key, value in hmac_headers.items():
            print(f"  {key}: {value}")
        print("✓ HMAC authentication working")
    else:
        print("✗ HMAC authentication failed")

    return success


async def test_jwt_auth():
    """Test JWT authentication"""
    print("\nTesting JWT authentication...")

    # Create mock secrets manager
    secrets_manager = MockSecretsManager()
    auth_manager = A2AAuthManager(secrets_manager)

    try:
        import jwt as jwt_lib  # noqa: F401

        print("✓ JWT library available")

        # Test with a simple symmetric key first
        auth_manager.add_credentials(
            "jwt-agent",
            AuthType.JWT,
            {
                "private_key": "test-symmetric-secret",
                "algorithm": "HS256",  # Use symmetric for simple test
            },
        )
        print("✓ JWT credentials added")

        # Test JWT authentication
        headers = {"Content-Type": "application/json"}
        success, result_headers = await auth_manager.apply_authentication_with_context(
            "jwt-agent", AuthType.JWT, headers, "http://test.com/endpoint", "POST", required=True
        )

        print(f"JWT Auth Success: {success}")
        if success and "Authorization" in result_headers:
            auth_header = result_headers["Authorization"]
            print(f"  Authorization: {auth_header[:50]}...")
            print("✓ JWT authentication working")
            return True
        else:
            print("✗ JWT authentication failed")
            return False

    except ImportError:
        print("✗ JWT library not available - install PyJWT")
        return False


async def main():
    """Run all tests"""
    print("A2A Authentication Implementation Test")
    print("=====================================")

    hmac_success = await test_hmac_auth()
    jwt_success = await test_jwt_auth()

    print("\nTest Summary:")
    print(f"HMAC: {'✓ PASS' if hmac_success else '✗ FAIL'}")
    print(f"JWT:  {'✓ PASS' if jwt_success else '✗ FAIL'}")

    if hmac_success and jwt_success:
        print("\n🎉 All authentication methods implemented successfully!")
    elif hmac_success:
        print("\n✓ HMAC implemented, JWT needs dependencies")
    else:
        print("\n❌ Some implementations need fixes")


if __name__ == "__main__":
    asyncio.run(main())
