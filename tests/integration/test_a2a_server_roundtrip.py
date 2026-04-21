"""Integration test for A2A server end-to-end request handling.

Boots an A2AServer's FastAPI app via FastAPI's TestClient (no uvicorn), attaches
a minimal overlord with a single echoing agent, then POSTs both legacy-shape and
SDK-shape request bodies to /agents/{agent_id}/message to verify:

  1. The agent receives the message text in both formats.
  2. The server returns a success response with the agent's output.
  3. Unknown agent IDs yield a success-shaped error payload (not a crash).

These assertions sit at the HTTP contract level so they stay valid across the
a2a-sdk 0.3.x -> 1.0.x upgrade; internal SDK envelope changes (JSONRPCError,
SendMessageSuccessResponse) are hidden behind the server's response shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from muxi.runtime.services.a2a.server import A2AServer


@dataclass
class _EchoAgent:
    """Minimal agent double that records calls and echoes input back."""

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
            {
                "source": source_agent_id,
                "message": message,
                "message_type": message_type,
                "context": context or {},
                "message_id": message_id,
            }
        )
        return {
            "status": "success",
            "response": f"echo: {message}",
            "agent_id": "echo-agent",
        }


@dataclass
class _FakeOverlord:
    """Minimal overlord double with just enough surface for the A2A server."""

    agents: Dict[str, _EchoAgent] = field(default_factory=dict)
    agent_descriptions: Dict[str, str] = field(default_factory=dict)
    secrets_manager: Optional[Any] = None


@pytest.fixture
def echo_agent():
    return _EchoAgent()


@pytest.fixture
def server(echo_agent):
    overlord = _FakeOverlord(
        agents={"echo-agent": echo_agent},
        agent_descriptions={"echo-agent": "Echo agent"},
    )
    return A2AServer(
        overlord=overlord,
        port=0,
        host="127.0.0.1",
        auth_mode="none",
        formation_name="test-formation",
    )


@pytest.fixture
def client(server):
    return TestClient(server.app)


# ---------------------------------------------------------------------------
# Health / discovery
# ---------------------------------------------------------------------------


def test_health_endpoint_reports_formation_and_agents(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["formation"] == "test-formation"
    assert "echo-agent" in body["agents"]


def test_agents_endpoint_lists_echo_agent(client):
    resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    cards = body.get("agents", [])
    ids = [c.get("name") or c.get("id") for c in cards]
    assert any("echo" in (n or "").lower() for n in ids)


# ---------------------------------------------------------------------------
# Legacy-format round-trip
# ---------------------------------------------------------------------------


def test_legacy_request_reaches_agent_and_returns_success(client, echo_agent):
    resp = client.post(
        "/agents/echo-agent/message",
        json={
            "message": "hello legacy",
            "message_type": "request",
            "context": {"trace_id": "t-1"},
            "message_id": "msg-legacy-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert "echo: hello legacy" in (body.get("response") or "")

    assert len(echo_agent.received) == 1
    call = echo_agent.received[0]
    assert call["message"] == "hello legacy"
    assert call["context"].get("trace_id") == "t-1"


def test_legacy_unknown_agent_returns_error_status(client):
    resp = client.post(
        "/agents/does-not-exist/message",
        json={"message": "hi", "message_type": "request"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "error"
    assert "not found" in (body.get("error") or "").lower()


# ---------------------------------------------------------------------------
# SDK-format round-trip
# ---------------------------------------------------------------------------


def test_sdk_request_reaches_agent_with_extracted_text(client, echo_agent):
    sdk_body = {
        "id": "req-1",
        "params": {
            "message": {
                "message_id": "m-sdk-1",
                "role": "user",
                "kind": "message",
                "parts": [
                    {"kind": "text", "text": "hello sdk"},
                    {"kind": "data", "data": {"trace_id": "t-2"}},
                ],
                "metadata": {"source": "test"},
            }
        },
    }
    resp = client.post("/agents/echo-agent/message", json=sdk_body)
    assert resp.status_code == 200

    assert len(echo_agent.received) == 1
    call = echo_agent.received[0]
    # The text part content must reach the agent.
    assert "hello sdk" in (call["message"] or "")
    # Context carries metadata + data parts merged.
    assert call["context"].get("trace_id") == "t-2"


def test_sdk_request_only_metadata_falls_back_to_original_request(client, echo_agent):
    sdk_body = {
        "id": "req-2",
        "params": {
            "message": {
                "message_id": "m-sdk-2",
                "role": "user",
                "kind": "message",
                "parts": [],
                "metadata": {"original_request": "fallback content"},
            }
        },
    }
    resp = client.post("/agents/echo-agent/message", json=sdk_body)
    assert resp.status_code == 200

    assert len(echo_agent.received) == 1
    call = echo_agent.received[0]
    assert "fallback content" in (call["message"] or "")
