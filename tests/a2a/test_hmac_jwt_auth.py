"""
Test HMAC and JWT authentication for A2A communication.
"""

import os
import hmac
import hashlib
import json
from typing import Dict

import pytest

# Set up path for imports
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime"))

from muxi.runtime.a2a.auth import A2AAuthManager, AuthType, AuthCredentials  # noqa: E402


# Test utilities
def create_test_private_key():
    """Create a test RSA private key for JWT testing"""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=1024,  # Small key for testing
        )

        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return pem.decode("utf-8")
    except ImportError:
        return "test-private-key-placeholder"


def verify_hmac_signature(
    headers: Dict[str, str], secret: str, url: str, method: str, payload: str = ""
) -> bool:
    """Verify HMAC signature manually"""
    signature = headers.get("X-Signature")
    timestamp = headers.get("X-Timestamp")
    nonce = headers.get("X-Nonce")

    if not all([signature, timestamp, nonce]):
        return False

    # Create payload hash
    payload_hash = hashlib.sha256(payload.encode()).hexdigest() if payload else ""

    # Create signature string
    signature_string = f"{method.upper()}\n{url}\n{timestamp}\n{nonce}\n{payload_hash}"

    # Calculate expected signature
    expected_signature = hmac.new(
        secret.encode(), signature_string.encode(), hashlib.sha256
    ).hexdigest()

    return signature == expected_signature


@pytest.mark.asyncio
class TestHMACAuthentication:
    """Test HMAC signature authentication"""

    def setup_method(self):
        """Setup test environment"""
        self.auth_manager = A2AAuthManager()
        self.test_secret = "test-hmac-secret-123"
        self.agent_id = "test-hmac-agent"
        self.url = "http://localhost:8080/agents/target-agent/message"
        self.method = "POST"
        self.payload = json.dumps({"message": "test", "type": "request"})

    async def test_hmac_credentials_validation(self):
        """Test HMAC credentials validation"""
        # Valid credentials
        valid_creds = AuthCredentials(
            auth_type=AuthType.HMAC, credentials={"secret": self.test_secret}
        )
        assert valid_creds.auth_type == AuthType.HMAC

        # Missing secret
        with pytest.raises(ValueError, match="HMAC authentication requires 'secret' credential"):
            AuthCredentials(auth_type=AuthType.HMAC, credentials={})

    async def test_hmac_signature_generation(self):
        """Test HMAC signature generation"""
        # Add credentials
        self.auth_manager.add_credentials(
            self.agent_id, AuthType.HMAC, {"secret": self.test_secret}
        )

        # Apply authentication
        headers = {"Content-Type": "application/json"}
        success, auth_headers = await self.auth_manager.apply_authentication_with_context(
            self.agent_id,
            AuthType.HMAC,
            headers,
            self.url,
            self.method,
            self.payload,
            required=True,
        )

        assert success, "HMAC authentication should succeed"
        assert "X-Signature" in auth_headers
        assert "X-Timestamp" in auth_headers
        assert "X-Nonce" in auth_headers

        # Verify signature is correct
        assert verify_hmac_signature(
            auth_headers, self.test_secret, self.url, self.method, self.payload
        )

    async def test_hmac_with_empty_payload(self):
        """Test HMAC signature with empty payload"""
        self.auth_manager.add_credentials(
            self.agent_id, AuthType.HMAC, {"secret": self.test_secret}
        )

        headers = {"Content-Type": "application/json"}
        success, auth_headers = await self.auth_manager.apply_authentication_with_context(
            self.agent_id, AuthType.HMAC, headers, self.url, self.method, "", required=True
        )

        assert success
        assert verify_hmac_signature(auth_headers, self.test_secret, self.url, self.method, "")

    async def test_hmac_different_methods(self):
        """Test HMAC signature with different HTTP methods"""
        self.auth_manager.add_credentials(
            self.agent_id, AuthType.HMAC, {"secret": self.test_secret}
        )

        for method in ["GET", "POST", "PUT", "DELETE"]:
            headers = {"Content-Type": "application/json"}
            success, auth_headers = await self.auth_manager.apply_authentication_with_context(
                self.agent_id, AuthType.HMAC, headers, self.url, method, self.payload, required=True
            )

            assert success, f"HMAC should work with {method}"
            assert verify_hmac_signature(
                auth_headers, self.test_secret, self.url, method, self.payload
            )


@pytest.mark.asyncio
class TestJWTAuthentication:
    """Test JWT authentication"""

    def setup_method(self):
        """Setup test environment"""
        self.auth_manager = A2AAuthManager()
        self.test_private_key = create_test_private_key()
        self.agent_id = "test-jwt-agent"

        # Skip tests if JWT dependencies are not available
        try:
            import jwt  # noqa: F401

            self.jwt_available = True
        except ImportError:
            self.jwt_available = False

    @pytest.mark.skipif(
        not hasattr(pytest, "jwt_available") or not pytest.jwt_available,
        reason="JWT dependencies not available",
    )
    async def test_jwt_credentials_validation(self):
        """Test JWT credentials validation"""
        if not self.jwt_available:
            pytest.skip("JWT dependencies not available")

        # Valid credentials
        valid_creds = AuthCredentials(
            auth_type=AuthType.JWT,
            credentials={"private_key": self.test_private_key, "algorithm": "RS256"},
        )
        assert valid_creds.auth_type == AuthType.JWT

        # Missing private key
        with pytest.raises(
            ValueError, match="JWT authentication requires 'private_key' credential"
        ):
            AuthCredentials(auth_type=AuthType.JWT, credentials={})

    async def test_jwt_token_generation(self):
        """Test JWT token generation"""
        if not self.jwt_available:
            pytest.skip("JWT dependencies not available")

        # Add credentials
        self.auth_manager.add_credentials(
            self.agent_id,
            AuthType.JWT,
            {
                "private_key": self.test_private_key,
                "algorithm": "RS256",
                "issuer": "test-issuer",
                "audience": "test-audience",
            },
        )

        # Apply authentication
        headers = {"Content-Type": "application/json"}
        success, auth_headers = await self.auth_manager.apply_authentication_with_context(
            self.agent_id, AuthType.JWT, headers, "http://test.com", "POST", required=True
        )

        assert success, "JWT authentication should succeed"
        assert "Authorization" in auth_headers

        auth_header = auth_headers["Authorization"]
        assert auth_header.startswith("Bearer "), "Should have Bearer token"

        # Extract and verify token structure
        token = auth_header.replace("Bearer ", "")
        assert len(token.split(".")) == 3, "JWT should have 3 parts"

    async def test_jwt_with_custom_claims(self):
        """Test JWT with custom claims"""
        if not self.jwt_available:
            pytest.skip("JWT dependencies not available")

        custom_claims = {"scope": "a2a:message", "role": "agent"}

        self.auth_manager.add_credentials(
            self.agent_id,
            AuthType.JWT,
            {"private_key": self.test_private_key, "custom_claims": custom_claims},
        )

        headers = {"Content-Type": "application/json"}
        success, auth_headers = await self.auth_manager.apply_authentication_with_context(
            self.agent_id, AuthType.JWT, headers, "http://test.com", "POST", required=True
        )

        assert success
        assert "Authorization" in auth_headers


@pytest.mark.asyncio
class TestAuthenticationIntegration:
    """Test integration of authentication methods"""

    def setup_method(self):
        """Setup test environment"""
        self.auth_manager = A2AAuthManager()

    async def test_multiple_auth_types(self):
        """Test managing multiple authentication types"""
        # Add different auth types for different agents
        self.auth_manager.add_credentials("api-agent", AuthType.API_KEY, {"api_key": "test-key"})
        self.auth_manager.add_credentials("hmac-agent", AuthType.HMAC, {"secret": "test-secret"})
        self.auth_manager.add_credentials(
            "jwt-agent", AuthType.JWT, {"private_key": create_test_private_key()}
        )

        # Check credentials are stored correctly
        agents_with_creds = self.auth_manager.list_agents_with_credentials()
        assert "api-agent" in agents_with_creds
        assert "hmac-agent" in agents_with_creds
        assert "jwt-agent" in agents_with_creds

        assert agents_with_creds["api-agent"] == AuthType.API_KEY
        assert agents_with_creds["hmac-agent"] == AuthType.HMAC
        assert agents_with_creds["jwt-agent"] == AuthType.JWT

    async def test_auth_fallback_behavior(self):
        """Test authentication fallback when not required"""
        # Test with agent that has no credentials
        headers = {"Content-Type": "application/json"}

        # Not required - should succeed without auth
        success, result_headers = await self.auth_manager.apply_authentication_with_context(
            "unknown-agent", AuthType.HMAC, headers, "http://test.com", "POST", required=False
        )
        assert success
        assert result_headers == headers  # Should be unchanged

        # Required - should fail
        success, result_headers = await self.auth_manager.apply_authentication_with_context(
            "unknown-agent", AuthType.HMAC, headers, "http://test.com", "POST", required=True
        )
        assert not success

    async def test_auth_type_mismatch(self):
        """Test behavior when credential type doesn't match requirement"""
        # Add API key credentials
        self.auth_manager.add_credentials("test-agent", AuthType.API_KEY, {"api_key": "test-key"})

        headers = {"Content-Type": "application/json"}

        # Try to use HMAC auth but agent only has API key
        success, result_headers = await self.auth_manager.apply_authentication_with_context(
            "test-agent", AuthType.HMAC, headers, "http://test.com", "POST", required=True
        )
        assert not success, "Should fail when auth types don't match"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
