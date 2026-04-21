"""Unit tests for UnifiedA2AMessaging MUXI <-> A2A SDK conversion helpers.

These tests exercise the public-shape contract:
  MUXI dict input  -> SDK Message (structure we can inspect)
  SDK Message      -> MUXI dict (shape our agents expect)

The tests MUST remain version-agnostic across the a2a-sdk 0.3.x -> 1.0.x upgrade.
They assert on MUXI-level shapes only; internal SDK representations (protobuf vs
pydantic, flattened vs wrapped parts) are hidden behind the conversion helpers.
"""

from types import SimpleNamespace

import pytest

from muxi.runtime.formation.overlord.a2a_messaging import UnifiedA2AMessaging


@pytest.fixture
def messaging():
    # UnifiedA2AMessaging only needs an overlord reference; the conversion
    # helpers under test do not touch overlord state.
    return UnifiedA2AMessaging(overlord=SimpleNamespace(client_factory=None))


def _text_of(sdk_message):
    """Extract all text fragments from an SDK Message regardless of SDK version.

    Works for both pydantic-shaped Parts (0.3) and protobuf-shaped Parts (1.0).
    """
    out = []
    for part in sdk_message.parts:
        text = getattr(part, "text", None)
        if text:
            out.append(text)
            continue
        # pydantic 0.3 may expose .text via model_dump
        dump = getattr(part, "model_dump", None)
        if callable(dump):
            d = dump()
            if d.get("text"):
                out.append(d["text"])
    return out


def _has_data_part(sdk_message):
    for part in sdk_message.parts:
        data = getattr(part, "data", None)
        if data:
            return True
        dump = getattr(part, "model_dump", None)
        if callable(dump):
            d = dump()
            if d.get("data"):
                return True
    return False


def test_string_message_becomes_single_text_part(messaging):
    msg = messaging._convert_to_a2a_message("hello world", source_agent_id="agent-a")
    assert msg.message_id, "message_id must be generated"
    assert len(msg.parts) == 1
    assert _text_of(msg) == ["hello world"]


def test_parts_dict_preserves_text_and_data_parts(messaging):
    muxi_in = {
        "parts": [
            {"type": "TextPart", "text": "step one"},
            {"type": "DataPart", "data": {"step": 2, "ok": True}},
            {"type": "TextPart", "text": "step three"},
        ]
    }
    msg = messaging._convert_to_a2a_message(muxi_in, source_agent_id="agent-a")
    assert len(msg.parts) == 3
    assert _text_of(msg) == ["step one", "step three"]
    assert _has_data_part(msg)


def test_generic_dict_becomes_single_data_part(messaging):
    muxi_in = {"arbitrary": "payload", "nested": {"ok": True}}
    msg = messaging._convert_to_a2a_message(muxi_in, source_agent_id="agent-a")
    assert len(msg.parts) == 1
    assert _has_data_part(msg)


def test_context_metadata_round_trips(messaging):
    msg = messaging._convert_to_a2a_message(
        "payload", source_agent_id="agent-a", context={"trace_id": "t-123"}
    )
    # Metadata survives into the SDK message. We don't assert on exact shape
    # (protobuf Struct vs python dict) — only that the trace_id is reachable.
    metadata = msg.metadata
    if hasattr(metadata, "items"):
        # protobuf Struct exposes .items() that yields (str, Value)
        keys = (
            {k for k, _ in metadata.items()}
            if callable(getattr(metadata, "items", None))
            else set(metadata)
        )
    else:
        keys = set(metadata or {})
    assert "trace_id" in keys


def test_convert_from_internal_message_yields_parts_shape(messaging):
    # Start from a MUXI dict, round-trip to SDK, then back to MUXI.
    muxi_in = {
        "parts": [
            {"type": "TextPart", "text": "alpha"},
            {"type": "DataPart", "data": {"k": "v"}},
        ]
    }
    sdk = messaging._convert_to_a2a_message(muxi_in, source_agent_id="agent-a")

    # Without _last_was_external the internal branch returns MUXI "parts" shape.
    messaging._last_was_external = False
    round_tripped = messaging._convert_from_a2a_message(sdk)

    assert "parts" in round_tripped
    types_seen = [p.get("type") for p in round_tripped["parts"]]
    assert "TextPart" in types_seen
    assert "DataPart" in types_seen
    text_values = [p.get("text") for p in round_tripped["parts"] if p.get("type") == "TextPart"]
    assert "alpha" in text_values


def test_convert_from_external_text_response_is_wrapped(messaging):
    sdk = messaging._convert_to_a2a_message("Done.", source_agent_id="agent-a")

    messaging._last_was_external = True
    out = messaging._convert_from_a2a_message(sdk)

    assert out.get("status") == "success"
    assert "Done." in out.get("response", "")
    assert out.get("execution_completed") is True


def test_convert_from_external_data_response_unwraps_expected_shape(messaging):
    # External agents sometimes return {"status": "...", "response": "..."} directly
    # inside a DataPart; the helper must pass that through unchanged.
    muxi_in = {"parts": [{"type": "DataPart", "data": {"status": "success", "response": "ok"}}]}
    sdk = messaging._convert_to_a2a_message(muxi_in, source_agent_id="agent-a")

    messaging._last_was_external = True
    out = messaging._convert_from_a2a_message(sdk)

    assert out.get("status") == "success"
    assert out.get("response") == "ok"


def test_convert_from_external_empty_response_is_error(messaging):
    # Construct an SDK Message with no parts. The 0.3 SDK's Message requires
    # at least one part; build one with a single empty-text part so we hit the
    # "no text, no data" branch of the conversion.
    muxi_in = {"parts": [{"type": "TextPart", "text": ""}]}
    sdk = messaging._convert_to_a2a_message(muxi_in, source_agent_id="agent-a")

    messaging._last_was_external = True
    out = messaging._convert_from_a2a_message(sdk)

    assert out.get("status") == "error"
