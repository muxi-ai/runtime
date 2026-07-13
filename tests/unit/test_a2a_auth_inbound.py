"""Unit tests for A2A inbound authentication (hmac and openid modes).

Covers:
  - HMAC signature validation: valid signature, wrong secret, timestamp
    tolerance, replay rejection, malformed timestamp
  - Strict mode enforcement: hmac/openid servers reject other auth types
  - OpenID JWT validation against a real JWKS endpoint (local HTTP server,
    RSA keypair generated in-test, token signed with PyJWT)
"""

import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from muxi.runtime.services.a2a.auth.inbound import (
    A2AInboundAuthenticator,
    InboundAuthType,
)


def _sign(secret: str, timestamp: str) -> str:
    return hmac.new(secret.encode(), timestamp.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# HMAC mode
# ---------------------------------------------------------------------------


@pytest.fixture
def hmac_auth():
    authenticator = A2AInboundAuthenticator("hmac")
    authenticator.hmac_secrets["shh"] = "client-1"
    return authenticator


async def test_hmac_valid_signature_authenticates(hmac_auth):
    timestamp = str(int(time.time()))
    ok, client_id, error = await hmac_auth._authenticate_hmac(_sign("shh", timestamp), timestamp)
    assert ok is True
    assert client_id == "client-1"
    assert error is None


async def test_hmac_wrong_secret_rejected(hmac_auth):
    timestamp = str(int(time.time()))
    ok, client_id, error = await hmac_auth._authenticate_hmac(_sign("wrong", timestamp), timestamp)
    assert ok is False
    assert client_id is None
    assert "signature" in error.lower()


async def test_hmac_stale_timestamp_rejected(hmac_auth):
    timestamp = str(int(time.time()) - 3600)
    ok, _, error = await hmac_auth._authenticate_hmac(_sign("shh", timestamp), timestamp)
    assert ok is False
    assert "tolerance" in error.lower()


async def test_hmac_malformed_timestamp_rejected(hmac_auth):
    ok, _, error = await hmac_auth._authenticate_hmac("sig", "not-a-number")
    assert ok is False
    assert "timestamp" in error.lower()


async def test_hmac_replayed_signature_rejected(hmac_auth):
    timestamp = str(int(time.time()))
    signature = _sign("shh", timestamp)

    ok, _, _ = await hmac_auth._authenticate_hmac(signature, timestamp)
    assert ok is True

    ok, _, error = await hmac_auth._authenticate_hmac(signature, timestamp)
    assert ok is False
    assert "replay" in error.lower()


async def test_hmac_custom_tolerance_from_auth_config():
    authenticator = A2AInboundAuthenticator("hmac", auth_config={"timestamp_tolerance": 10})
    authenticator.hmac_secrets["shh"] = "client-1"
    timestamp = str(int(time.time()) - 60)
    ok, _, error = await authenticator._authenticate_hmac(_sign("shh", timestamp), timestamp)
    assert ok is False
    assert "tolerance" in error.lower()


async def test_hmac_mode_rejects_bearer_and_api_key_headers(hmac_auth):
    ok, _, error = await hmac_auth.authenticate_request(
        request=None, authorization="Bearer tok", x_api_key=None
    )
    assert ok is False
    assert "HMAC" in error

    ok, _, error = await hmac_auth.authenticate_request(
        request=None, authorization=None, x_api_key="key"
    )
    assert ok is False
    assert "HMAC" in error


async def test_hmac_mode_requires_both_signature_and_timestamp(hmac_auth):
    ok, _, error = await hmac_auth.authenticate_request(
        request=None, authorization=None, x_api_key=None, x_signature="sig", x_timestamp=None
    )
    assert ok is False
    assert "X-Timestamp" in error


async def test_hmac_full_request_dispatch_authenticates(hmac_auth):
    timestamp = str(int(time.time()))
    ok, client_id, _ = await hmac_auth.authenticate_request(
        request=None,
        authorization=None,
        x_api_key=None,
        x_signature=_sign("shh", timestamp),
        x_timestamp=timestamp,
    )
    assert ok is True
    assert client_id == "client-1"


def test_add_client_credential_hmac_requires_secret():
    authenticator = A2AInboundAuthenticator("hmac")
    with pytest.raises(ValueError, match="secret"):
        authenticator.add_client_credential("client-2", InboundAuthType.HMAC, {})

    authenticator.add_client_credential("client-2", InboundAuthType.HMAC, {"secret": "s2"})
    assert authenticator.hmac_secrets["s2"] == "client-2"


def test_hmac_auth_requirements_list_signature_headers():
    authenticator = A2AInboundAuthenticator("hmac")
    requirements = authenticator.get_auth_requirements()
    assert requirements["required_headers"] == ["X-Signature", "X-Timestamp"]


# ---------------------------------------------------------------------------
# OpenID mode (real JWKS endpoint + RSA-signed JWT)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key, private_pem


@pytest.fixture
def jwks_server(rsa_keypair):
    key, _ = rsa_keypair
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    jwks_body = json.dumps({"keys": [jwk]}).encode()

    class JWKSHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(jwks_body)))
            self.end_headers()
            self.wfile.write(jwks_body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), JWKSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/jwks.json"
    server.shutdown()
    server.server_close()


def _make_token(private_pem, issuer, audience=None, sub="svc-42", expired=False):
    now = int(time.time())
    claims = {
        "iss": issuer,
        "sub": sub,
        "iat": now - 10,
        "exp": now - 3600 if expired else now + 3600,
    }
    if audience:
        claims["aud"] = audience
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-key"})


ISSUER = "https://idp.example.com"


@pytest.fixture
def openid_auth(jwks_server):
    return A2AInboundAuthenticator(
        "openid", auth_config={"issuer": ISSUER, "jwks_url": jwks_server}
    )


async def test_openid_valid_jwt_authenticates(openid_auth, rsa_keypair):
    _, private_pem = rsa_keypair
    token = _make_token(private_pem, ISSUER)
    ok, client_id, error = await openid_auth._authenticate_openid(f"Bearer {token}")
    assert ok is True, error
    assert client_id == "openid:svc-42"


async def test_openid_expired_jwt_rejected(openid_auth, rsa_keypair):
    _, private_pem = rsa_keypair
    token = _make_token(private_pem, ISSUER, expired=True)
    ok, _, error = await openid_auth._authenticate_openid(f"Bearer {token}")
    assert ok is False
    assert "expired" in error.lower()


async def test_openid_wrong_issuer_rejected(openid_auth, rsa_keypair):
    _, private_pem = rsa_keypair
    token = _make_token(private_pem, "https://evil.example.com")
    ok, _, error = await openid_auth._authenticate_openid(f"Bearer {token}")
    assert ok is False
    assert "issuer" in error.lower()


async def test_openid_audience_enforced_when_configured(jwks_server, rsa_keypair):
    _, private_pem = rsa_keypair
    authenticator = A2AInboundAuthenticator(
        "openid",
        auth_config={"issuer": ISSUER, "jwks_url": jwks_server, "audience": "muxi-formation"},
    )

    token = _make_token(private_pem, ISSUER, audience="muxi-formation")
    ok, client_id, error = await authenticator._authenticate_openid(f"Bearer {token}")
    assert ok is True, error
    assert client_id == "openid:svc-42"

    token = _make_token(private_pem, ISSUER, audience="someone-else")
    ok, _, error = await authenticator._authenticate_openid(f"Bearer {token}")
    assert ok is False
    assert "audience" in error.lower()


async def test_openid_token_with_aud_accepted_when_no_audience_configured(openid_auth, rsa_keypair):
    _, private_pem = rsa_keypair
    token = _make_token(private_pem, ISSUER, audience="anything")
    ok, client_id, error = await openid_auth._authenticate_openid(f"Bearer {token}")
    assert ok is True, error
    assert client_id == "openid:svc-42"


async def test_openid_missing_issuer_config_rejected():
    authenticator = A2AInboundAuthenticator("openid", auth_config={})
    ok, _, error = await authenticator._authenticate_openid("Bearer whatever")
    assert ok is False
    assert "issuer" in error.lower()


async def test_openid_mode_rejects_api_key_and_non_bearer(openid_auth):
    ok, _, error = await openid_auth.authenticate_request(
        request=None, authorization=None, x_api_key="key"
    )
    assert ok is False
    assert "OpenID" in error

    ok, _, error = await openid_auth.authenticate_request(
        request=None, authorization="Basic abc", x_api_key=None
    )
    assert ok is False
    assert "Bearer" in error
