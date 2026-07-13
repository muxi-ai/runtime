#!/usr/bin/env python3
"""
Test 7B6: A2A Extended Auth Types (hmac inbound/outbound interop, openid inbound)

Exercises the extended A2A auth types end to end against a running A2AServer
(FastAPI TestClient), following the test_7b2 external-messaging pattern:

  hmac (inbound + outbound interop):
    1. Headers built by the real outbound A2AAuthManager are accepted by the
       inbound authenticator sharing the same secret.
    2. A manually signed request (fresh timestamp) authenticates.
    3. A signature from the wrong secret is rejected (401).
    4. A stale timestamp outside the tolerance window is rejected (401).
    5. Replaying a previously accepted signature is rejected (401).
    6. Bearer credentials against an hmac server are rejected (strict
       type matching, 403).

  openid (inbound):
    7. A JWT signed by an in-test RSA key validates against a real local
       JWKS endpoint (no mocks).
    8. An expired JWT is rejected (401).
    9. A request without a token is rejected (401/403).
"""

import asyncio
import hashlib
import hmac as hmac_lib
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

SECRET = "e2e-hmac-shared-secret"
ISSUER = "https://idp.e2e.example.com"


@dataclass
class _EchoAgent:
    a2a_external: bool = True
    received: List[Dict[str, Any]] = field(default_factory=list)

    async def handle_a2a_message(
        self,
        source_agent_id: str,
        message,
        message_type: str,
        context: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.received.append({"source": source_agent_id, "message": message})
        return {"status": "success", "response": f"echo: {message}", "agent_id": "echo-agent"}


@dataclass
class _FakeOverlord:
    agents: Dict[str, _EchoAgent] = field(default_factory=dict)
    agent_descriptions: Dict[str, str] = field(default_factory=dict)
    secrets_manager: Optional[Any] = None


def _sign(secret: str, timestamp: int) -> Dict[str, str]:
    ts = str(timestamp)
    sig = hmac_lib.new(secret.encode("utf-8"), ts.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"X-Signature": sig, "X-Timestamp": ts}


def _post_message(client, headers: Dict[str, str]):
    return client.post(
        "/agents/echo-agent/message",
        json={"message": "auth-e2e-hello", "message_type": "request"},
        headers=headers,
    )


def _start_jwks_server(public_key) -> tuple:
    import jwt

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": "e2e-key", "use": "sig", "alg": "RS256"})
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
    return server, f"http://127.0.0.1:{server.server_port}/jwks.json"


def _make_token(private_pem, expired: bool = False) -> str:
    import jwt

    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": "e2e-svc",
        "iat": now - 10,
        "exp": now - 3600 if expired else now + 3600,
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "e2e-key"})


async def test_a2a_extended_auth():
    print("\n" + "=" * 80)
    print("Test 7B6: A2A Extended Auth Types (hmac + openid)")
    print("=" * 80)

    from fastapi.testclient import TestClient

    from muxi.runtime.services.a2a.auth.outbound import (
        A2AAuthManager,
        AuthCredentials,
        AuthType,
    )
    from muxi.runtime.services.a2a.server import A2AServer
    from muxi.runtime.services.secrets.secrets_manager import SecretsManager

    all_passed = True
    checks = []

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal all_passed
        status = "OK" if ok else "FAIL"
        print(f"   {status}: {name}{f' ({detail})' if detail else ''}")
        if ok:
            checks.append(name)
        else:
            all_passed = False

    # ------------------------------------------------------------------
    # hmac inbound server
    # ------------------------------------------------------------------
    print("\n1. Booting A2AServer with auth_mode=hmac ...")
    echo = _EchoAgent()
    overlord = _FakeOverlord(
        agents={"echo-agent": echo}, agent_descriptions={"echo-agent": "Echo agent"}
    )
    hmac_server = A2AServer(
        overlord=overlord,
        port=0,
        host="127.0.0.1",
        auth_mode="hmac",
        shared_key=SECRET,
        formation_name="e2e-hmac-formation",
        auth_config={"timestamp_tolerance": 300},
    )
    hmac_client = TestClient(hmac_server.app)
    check("hmac A2AServer boots", True)

    print("\n2. Outbound A2AAuthManager headers accepted by inbound (interop) ...")
    with tempfile.TemporaryDirectory() as tmpdir:
        auth_manager = A2AAuthManager(SecretsManager(tmpdir))
        creds = AuthCredentials(auth_type=AuthType.HMAC, credentials={"secret": SECRET})
        outbound_headers = auth_manager._build_hmac_headers(creds)
    resp = _post_message(hmac_client, outbound_headers)
    ok = resp.status_code == 200 and resp.json().get("status") == "success"
    check("outbound-signed request accepted", ok, f"status={resp.status_code}")

    print("\n3. Manually signed request (fresh timestamp) ...")
    # Distinct timestamp so the signature differs from step 2 (replay cache)
    valid_headers = _sign(SECRET, int(time.time()) - 5)
    resp = _post_message(hmac_client, valid_headers)
    ok = resp.status_code == 200 and "echo: auth-e2e-hello" in (resp.json().get("response") or "")
    check("manually signed request accepted", ok, f"status={resp.status_code}")

    print("\n4. Wrong-secret signature rejected ...")
    resp = _post_message(hmac_client, _sign("not-the-secret", int(time.time()) - 10))
    check("wrong secret rejected", resp.status_code == 401, f"status={resp.status_code}")

    print("\n5. Stale timestamp rejected ...")
    resp = _post_message(hmac_client, _sign(SECRET, int(time.time()) - 4000))
    check("stale timestamp rejected", resp.status_code == 401, f"status={resp.status_code}")

    print("\n6. Signature replay rejected ...")
    resp = _post_message(hmac_client, valid_headers)
    check("replayed signature rejected", resp.status_code == 401, f"status={resp.status_code}")

    print("\n7. Bearer credentials against hmac server rejected (strict matching) ...")
    resp = _post_message(hmac_client, {"Authorization": f"Bearer {SECRET}"})
    check(
        "bearer-vs-hmac type mismatch rejected",
        resp.status_code == 403,
        f"status={resp.status_code}",
    )
    check("agent saw only authenticated messages", len(echo.received) == 2)

    # ------------------------------------------------------------------
    # openid inbound server (real local JWKS endpoint)
    # ------------------------------------------------------------------
    print("\n8. Booting A2AServer with auth_mode=openid against a local JWKS endpoint ...")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwks_httpd, jwks_url = _start_jwks_server(key.public_key())
    try:
        openid_server = A2AServer(
            overlord=overlord,
            port=0,
            host="127.0.0.1",
            auth_mode="openid",
            formation_name="e2e-openid-formation",
            auth_config={"issuer": ISSUER, "jwks_url": jwks_url},
        )
        openid_client = TestClient(openid_server.app)
        check("openid A2AServer boots", True)

        print("\n9. Valid RSA-signed JWT accepted ...")
        token = _make_token(private_pem)
        resp = _post_message(openid_client, {"Authorization": f"Bearer {token}"})
        ok = resp.status_code == 200 and resp.json().get("status") == "success"
        check("valid JWT accepted", ok, f"status={resp.status_code}")

        print("\n10. Expired JWT rejected ...")
        resp = _post_message(
            openid_client, {"Authorization": f"Bearer {_make_token(private_pem, expired=True)}"}
        )
        check("expired JWT rejected", resp.status_code == 401, f"status={resp.status_code}")

        print("\n11. Missing token rejected ...")
        resp = _post_message(openid_client, {})
        check(
            "missing token rejected",
            resp.status_code in (401, 403),
            f"status={resp.status_code}",
        )
    finally:
        jwks_httpd.shutdown()
        jwks_httpd.server_close()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"Test Result: {'PASSED' if all_passed else 'FAILED'}")
    print(f"Checks Passed: {len(checks)}")
    for c in checks:
        print(f"  - {c}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_a2a_extended_auth())
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
