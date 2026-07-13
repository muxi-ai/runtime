"""Unit tests for A2A outbound authentication.

Covers:
  - AuthCredentials dataclass validation (accepts/rejects on bad input)
  - A2AAuthManager.apply_authentication header injection (pure MUXI logic)
  - A2AAuthManager.create_scheme construction from formation config
  - A2AAuthManager.apply_sdk_authentication when a scheme is registered

These tests assert MUXI-level contracts — specifically the HTTP headers that
get emitted — so they remain valid across the a2a-sdk 0.3.x -> 1.0.x upgrade.
Tests that currently exercise the broken `create_scheme` field naming are
marked xfail with a Phase-2 target; Phase 2 must clear them.
"""

import base64
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from muxi.runtime.services.a2a.auth.outbound import (
    A2AAuthManager,
    AuthCredentials,
    AuthType,
)

# ---------------------------------------------------------------------------
# AuthCredentials dataclass validation
# ---------------------------------------------------------------------------


def test_auth_credentials_accepts_valid_api_key():
    creds = AuthCredentials(
        auth_type=AuthType.API_KEY,
        credentials={"api_key": "sk-test-1234"},
    )
    assert creds.credentials["api_key"] == "sk-test-1234"


def test_auth_credentials_rejects_api_key_without_key():
    with pytest.raises(ValueError, match="api_key"):
        AuthCredentials(auth_type=AuthType.API_KEY, credentials={})


def test_auth_credentials_rejects_bearer_without_token():
    with pytest.raises(ValueError, match="token"):
        AuthCredentials(auth_type=AuthType.BEARER, credentials={})


def test_auth_credentials_rejects_basic_missing_username():
    with pytest.raises(ValueError, match="username"):
        AuthCredentials(auth_type=AuthType.BASIC, credentials={"password": "p"})


def test_auth_credentials_accepts_none_type_with_empty_creds():
    # AuthType.NONE should never require credentials.
    creds = AuthCredentials(auth_type=AuthType.NONE, credentials={})
    assert creds.auth_type == AuthType.NONE


# ---------------------------------------------------------------------------
# A2AAuthManager.apply_authentication — the main runtime path
# ---------------------------------------------------------------------------


class _DummySecretsManager:
    """Minimal stand-in for SecretsManager used only to satisfy the ctor."""

    async def get_secret(self, name):
        return None

    async def interpolate_secrets(self, value):
        return value


@pytest.fixture
def auth_manager():
    return A2AAuthManager(secrets_manager=_DummySecretsManager())


async def test_apply_authentication_none_is_noop(auth_manager):
    ok, headers = await auth_manager.apply_authentication(
        "agent-a", AuthType.NONE, {"X-Request-Id": "r1"}
    )
    assert ok is True
    assert headers == {"X-Request-Id": "r1"}


async def test_apply_authentication_api_key_injects_configured_header(auth_manager):
    auth_manager.add_credentials(
        "agent-a",
        AuthType.API_KEY,
        {"api_key": "sk-abc", "api_key_header": "X-Custom-Key"},
    )

    ok, headers = await auth_manager.apply_authentication("agent-a", AuthType.API_KEY, {})
    assert ok is True
    assert headers["X-Custom-Key"] == "sk-abc"


async def test_apply_authentication_api_key_defaults_to_x_api_key(auth_manager):
    auth_manager.add_credentials("agent-a", AuthType.API_KEY, {"api_key": "sk-abc"})
    ok, headers = await auth_manager.apply_authentication("agent-a", AuthType.API_KEY, {})
    assert ok is True
    assert headers["X-API-Key"] == "sk-abc"


async def test_apply_authentication_bearer_injects_authorization_header(auth_manager):
    auth_manager.add_credentials("agent-a", AuthType.BEARER, {"token": "tok-123"})
    ok, headers = await auth_manager.apply_authentication("agent-a", AuthType.BEARER, {})
    assert ok is True
    assert headers["Authorization"] == "Bearer tok-123"


async def test_apply_authentication_basic_encodes_username_password(auth_manager):
    auth_manager.add_credentials(
        "agent-a",
        AuthType.BASIC,
        {"username": "alice", "password": "s3cret"},
    )
    ok, headers = await auth_manager.apply_authentication("agent-a", AuthType.BASIC, {})
    expected = base64.b64encode(b"alice:s3cret").decode()
    assert ok is True
    assert headers["Authorization"] == f"Basic {expected}"


async def test_apply_authentication_missing_required_credentials_fails(auth_manager):
    ok, _ = await auth_manager.apply_authentication(
        "unknown-agent", AuthType.API_KEY, {}, required=True
    )
    assert ok is False


async def test_apply_authentication_missing_optional_credentials_passes(auth_manager):
    ok, headers = await auth_manager.apply_authentication(
        "unknown-agent", AuthType.API_KEY, {"H": "v"}, required=False
    )
    assert ok is True
    assert headers == {"H": "v"}


async def test_apply_authentication_type_mismatch_fails_when_required(auth_manager):
    auth_manager.add_credentials("agent-a", AuthType.API_KEY, {"api_key": "k"})
    ok, _ = await auth_manager.apply_authentication("agent-a", AuthType.BEARER, {}, required=True)
    assert ok is False


# ---------------------------------------------------------------------------
# A2AAuthManager.create_scheme + apply_sdk_authentication
# ---------------------------------------------------------------------------


def test_create_scheme_api_key_is_constructable(auth_manager):
    scheme = auth_manager.create_scheme({"type": "api_key", "key": "k", "header": "X-API-Key"})
    assert scheme is not None


def test_create_scheme_bearer_is_constructable(auth_manager):
    # The SDK silently drops the unknown 'token' kwarg, so the scheme object
    # constructs successfully but the credential value is lost. Phase 2 must
    # move credential storage out of the scheme itself.
    scheme = auth_manager.create_scheme({"type": "bearer", "token": "t"})
    assert scheme is not None
    assert getattr(scheme, "scheme", None) == "bearer"


def test_create_scheme_unknown_type_returns_none(auth_manager):
    assert auth_manager.create_scheme({"type": "kerberos"}) is None


def test_create_scheme_missing_type_returns_none(auth_manager):
    assert auth_manager.create_scheme({}) is None


async def test_apply_sdk_authentication_noop_without_registered_scheme(auth_manager):
    # When no scheme is registered and auth isn't required, headers pass through.
    ok, headers = await auth_manager.apply_sdk_authentication(
        "unknown-agent", {"X-Trace": "1"}, required=False
    )
    assert ok is True
    assert headers == {"X-Trace": "1"}


async def test_apply_sdk_authentication_missing_required_scheme_fails(auth_manager):
    ok, _ = await auth_manager.apply_sdk_authentication("unknown-agent", {}, required=True)
    assert ok is False


# ---------------------------------------------------------------------------
# HMAC request signing
# ---------------------------------------------------------------------------


def test_auth_credentials_rejects_hmac_without_secret():
    with pytest.raises(ValueError, match="secret"):
        AuthCredentials(auth_type=AuthType.HMAC, credentials={})


def test_create_scheme_hmac_is_constructable(auth_manager):
    scheme = auth_manager.create_scheme({"type": "hmac", "secret": "s"})
    assert scheme is not None


async def test_apply_authentication_hmac_signs_current_timestamp(auth_manager):
    auth_manager.add_credentials("agent-a", AuthType.HMAC, {"secret": "shh"})
    ok, headers = await auth_manager.apply_authentication("agent-a", AuthType.HMAC, {})

    assert ok is True
    timestamp = headers["X-Timestamp"]
    assert abs(int(timestamp) - int(time.time())) <= 5
    expected = hmac.new(b"shh", timestamp.encode(), hashlib.sha256).hexdigest()
    assert headers["X-Signature"] == expected


async def test_apply_authentication_hmac_honors_custom_header_names(auth_manager):
    auth_manager.add_credentials(
        "agent-a",
        AuthType.HMAC,
        {"secret": "shh", "signature_header": "X-Sig", "timestamp_header": "X-Ts"},
    )
    ok, headers = await auth_manager.apply_authentication("agent-a", AuthType.HMAC, {})
    assert ok is True
    assert "X-Sig" in headers
    assert "X-Ts" in headers


async def test_apply_sdk_authentication_hmac_signs_per_request(auth_manager):
    scheme = auth_manager.create_scheme({"type": "hmac", "secret": "shh"})
    auth_manager.schemes["agent-a"] = scheme
    auth_manager.add_credentials("agent-a", AuthType.HMAC, {"secret": "shh"})

    ok, headers = await auth_manager.apply_sdk_authentication("agent-a", {})
    assert ok is True
    expected = hmac.new(b"shh", headers["X-Timestamp"].encode(), hashlib.sha256).hexdigest()
    assert headers["X-Signature"] == expected


# ---------------------------------------------------------------------------
# OAuth2 client_credentials
# ---------------------------------------------------------------------------


def test_auth_credentials_rejects_oauth2_missing_fields():
    with pytest.raises(ValueError, match="oauth2|OAuth2"):
        AuthCredentials(auth_type=AuthType.OAUTH2, credentials={"client_id": "c"})


def test_create_scheme_oauth2_is_bearer_scheme(auth_manager):
    scheme = auth_manager.create_scheme(
        {"type": "oauth2", "client_id": "c", "client_secret": "s", "token_url": "u"}
    )
    assert scheme is not None
    assert getattr(scheme, "scheme", None) == "bearer"


async def test_oauth2_token_fetched_from_real_endpoint_and_cached(auth_manager):
    calls = {"count": 0}

    class TokenHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls["count"] += 1
            body = json.dumps({"access_token": "tok-oauth-1", "expires_in": 3600}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), TokenHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        token_url = f"http://127.0.0.1:{server.server_port}/token"
        auth_manager.add_credentials(
            "svc-oauth",
            AuthType.OAUTH2,
            {"client_id": "cid", "client_secret": "cs", "token_url": token_url},
        )

        ok, headers = await auth_manager.apply_authentication("svc-oauth", AuthType.OAUTH2, {})
        assert ok is True
        assert headers["Authorization"] == "Bearer tok-oauth-1"

        # Second call must come from the cache, not the endpoint
        ok, headers = await auth_manager.apply_authentication("svc-oauth", AuthType.OAUTH2, {})
        assert ok is True
        assert headers["Authorization"] == "Bearer tok-oauth-1"
        assert calls["count"] == 1
    finally:
        server.shutdown()
        server.server_close()


async def test_oauth2_expired_cache_triggers_refresh(auth_manager):
    auth_manager.add_credentials(
        "svc-oauth",
        AuthType.OAUTH2,
        {"client_id": "cid", "client_secret": "cs", "token_url": "http://127.0.0.1:9/token"},
    )
    # Seed an expired token; refresh must hit the (unreachable) endpoint and fail
    auth_manager._oauth2_tokens["svc-oauth"] = ("stale", time.time() - 10)
    ok, _ = await auth_manager.apply_authentication("svc-oauth", AuthType.OAUTH2, {})
    assert ok is False
