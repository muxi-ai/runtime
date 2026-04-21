#!/usr/bin/env python3
"""
Test 7B2-A: A2A SDK External Messaging Smoke Test

Complements test_7b3_a2a_discovery.py by exercising the A2A HTTP server end to
end without requiring a second formation. Spins up an A2AServer bound to a
minimal overlord-double, drives a request through FastAPI's TestClient, and
asserts the agent receives the payload and the server returns a success.

This is the PRD Phase 1 "external messaging" e2e test called out in the
a2a-sdk 1.0 migration.

What it verifies:
  1. A2AServer constructs against the active a2a-sdk version (0.3.x or 1.0.x).
  2. /health and /agents endpoints respond with the formation topology.
  3. POST /agents/{id}/message (legacy shape) reaches the agent and echoes.
  4. The a2a-sdk version is recorded for migration audit.
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


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
        self.received.append(
            {"source": source_agent_id, "message": message, "message_id": message_id}
        )
        return {"status": "success", "response": f"echo: {message}", "agent_id": "echo-agent"}


@dataclass
class _FakeOverlord:
    agents: Dict[str, _EchoAgent] = field(default_factory=dict)
    agent_descriptions: Dict[str, str] = field(default_factory=dict)
    secrets_manager: Optional[Any] = None


async def test_a2a_external_messaging_smoke():
    print("\n" + "=" * 80)
    print("Test 7B2-A: A2A SDK External Messaging Smoke Test")
    print("=" * 80)

    all_passed = True
    checks = []

    # ------------------------------------------------------------------
    # 1. Record SDK version
    # ------------------------------------------------------------------
    try:
        from importlib.metadata import version as pkg_version

        try:
            sdk_version = pkg_version("a2a-sdk")
        except Exception:
            sdk_version = "unknown"
        print(f"\n1. Loaded a2a-sdk version: {sdk_version}")
        checks.append(f"a2a-sdk version: {sdk_version}")
    except Exception as e:
        print(f"\n1. SDK detection failed: {e}")
        return 1

    # ------------------------------------------------------------------
    # 2. Boot A2AServer + TestClient
    # ------------------------------------------------------------------
    print("\n2. Booting A2AServer...")
    try:
        from fastapi.testclient import TestClient

        from muxi.runtime.services.a2a.server import A2AServer

        echo = _EchoAgent()
        overlord = _FakeOverlord(
            agents={"echo-agent": echo},
            agent_descriptions={"echo-agent": "Echo agent"},
        )
        server = A2AServer(
            overlord=overlord,
            port=0,
            host="127.0.0.1",
            auth_mode="none",
            formation_name="smoke-formation",
        )
        client = TestClient(server.app)
        print("   OK: A2AServer instantiated and TestClient attached")
        checks.append("A2AServer boots")
    except Exception as e:
        print(f"   FAIL: {e}")
        return 1

    # ------------------------------------------------------------------
    # 3. /health
    # ------------------------------------------------------------------
    print("\n3. GET /health ...")
    try:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "healthy"
        assert "echo-agent" in body.get("agents", [])
        print("   OK: /health reports echo-agent")
        checks.append("/health")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # 4. /agents
    # ------------------------------------------------------------------
    print("\n4. GET /agents ...")
    try:
        resp = client.get("/agents")
        assert resp.status_code == 200
        body = resp.json()
        cards = body.get("agents", [])
        assert len(cards) >= 1
        print(f"   OK: {len(cards)} agent card(s) returned")
        checks.append("/agents")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # 5. POST /agents/echo-agent/message (legacy shape)
    # ------------------------------------------------------------------
    print("\n5. POST /agents/echo-agent/message (legacy) ...")
    try:
        resp = client.post(
            "/agents/echo-agent/message",
            json={
                "message": "smoke-test-hello",
                "message_type": "request",
                "context": {"trace_id": "smoke-1"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "success"
        assert "echo: smoke-test-hello" in (body.get("response") or "")
        assert len(echo.received) == 1
        assert echo.received[0]["message"] == "smoke-test-hello"
        print(f"   OK: agent received {len(echo.received)} message(s), response success")
        checks.append("POST /agents/{id}/message (legacy)")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # 6. POST to unknown agent returns structured error
    # ------------------------------------------------------------------
    print("\n6. POST unknown agent returns error-shape ...")
    try:
        resp = client.post(
            "/agents/nobody/message",
            json={"message": "hi", "message_type": "request"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("status") == "error"
        print("   OK: unknown agent returns error")
        checks.append("Unknown-agent error")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

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
    exit_code = asyncio.run(test_a2a_external_messaging_smoke())
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
