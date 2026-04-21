"""Unit tests for ModelsAdapter: MUXI <-> A2A SDK type conversion.

These tests assert on MUXI-level public contracts so they remain green across
the a2a-sdk 0.3.x -> 1.0.x upgrade. Internal SDK representation changes
(pydantic -> protobuf, flattened Part, AgentCard.url -> supported_interfaces)
are hidden behind the adapter.
"""

import pytest

from muxi.runtime.services.a2a.models import (
    A2AAuthentication,
    A2ACapability,
    AgentCard as MUXIAgentCard,
    AuthType,
)
from muxi.runtime.services.a2a.models_adapter import ModelsAdapter

# ---------------------------------------------------------------------------
# Message round-trips
# ---------------------------------------------------------------------------


def _text_of(sdk_message):
    """Extract text parts from an SDK Message across 0.3 (RootModel wrapped
    TextPart) and 1.0 (flattened protobuf Part) shapes.
    """
    out = []
    for part in sdk_message.parts:
        text = getattr(part, "text", None)
        if text:
            out.append(text)
            continue
        dump = getattr(part, "model_dump", None)
        if callable(dump):
            d = dump()
            if d.get("text"):
                out.append(d["text"])
    return out


def _has_data_part(sdk_message):
    for part in sdk_message.parts:
        if getattr(part, "data", None):
            return True
        dump = getattr(part, "model_dump", None)
        if callable(dump):
            d = dump()
            if d.get("data"):
                return True
    return False


def test_string_message_produces_single_text_part():
    sdk = ModelsAdapter.muxi_to_sdk_message("hello", message_id="m-1")
    assert sdk.message_id == "m-1"
    assert _text_of(sdk) == ["hello"]


def test_parts_dict_produces_matching_sdk_parts():
    muxi_in = {
        "parts": [
            {"type": "TextPart", "text": "alpha"},
            {"type": "DataPart", "data": {"k": "v"}},
        ]
    }
    sdk = ModelsAdapter.muxi_to_sdk_message(muxi_in, message_id="m-2")
    assert _text_of(sdk) == ["alpha"]
    assert _has_data_part(sdk)


def test_generic_dict_becomes_data_part():
    sdk = ModelsAdapter.muxi_to_sdk_message({"any": "payload"}, message_id="m-3")
    assert _has_data_part(sdk)


def test_empty_message_yields_empty_text_part():
    # The adapter should never produce a Message with zero parts; an empty
    # string input yields a single empty text part.
    sdk = ModelsAdapter.muxi_to_sdk_message("", message_id="m-4")
    assert len(sdk.parts) >= 1


def test_message_round_trip_preserves_text_and_data():
    muxi_in = {
        "parts": [
            {"type": "TextPart", "text": "hello"},
            {"type": "DataPart", "data": {"foo": 1}},
        ]
    }
    sdk = ModelsAdapter.muxi_to_sdk_message(muxi_in, message_id="m-5")
    muxi_out = ModelsAdapter.sdk_to_muxi_message(sdk)

    assert "parts" in muxi_out
    types_seen = [p.get("type") for p in muxi_out["parts"]]
    assert "TextPart" in types_seen
    assert "DataPart" in types_seen
    texts = [p.get("text") for p in muxi_out["parts"] if p.get("type") == "TextPart"]
    assert "hello" in texts
    datas = [p.get("data") for p in muxi_out["parts"] if p.get("type") == "DataPart"]
    assert any(isinstance(d, dict) and d.get("foo") == 1 for d in datas)


# ---------------------------------------------------------------------------
# AgentCard round-trips
# ---------------------------------------------------------------------------


@pytest.fixture
def muxi_card():
    return MUXIAgentCard(
        name="Test Agent",
        description="Description here",
        version="1.0.0",
        url="http://localhost:8000/agent",
        capabilities={
            "search": A2ACapability(name="search", description="Search things", enabled=True),
            "summarize": A2ACapability(name="summarize", enabled=False),
        },
        metadata={"tenant": "muxi-test"},
    )


def test_muxi_card_converts_to_sdk_card(muxi_card):
    sdk = ModelsAdapter.muxi_to_sdk_agent_card(muxi_card)
    assert sdk.name == "Test Agent"
    assert sdk.description == "Description here"
    assert sdk.version == "1.0.0"


def test_sdk_card_round_trips_scalar_fields(muxi_card):
    sdk = ModelsAdapter.muxi_to_sdk_agent_card(muxi_card)
    back = ModelsAdapter.sdk_to_muxi_agent_card(sdk)

    assert back.name == muxi_card.name
    assert back.description == muxi_card.description
    assert back.version == muxi_card.version


def test_sdk_card_round_trips_preserves_capabilities(muxi_card):
    sdk = ModelsAdapter.muxi_to_sdk_agent_card(muxi_card)
    back = ModelsAdapter.sdk_to_muxi_agent_card(sdk)

    assert set(back.capabilities.keys()) == set(muxi_card.capabilities.keys())


# ---------------------------------------------------------------------------
# Authentication conversions
# ---------------------------------------------------------------------------


def test_muxi_auth_to_sdk_dict_has_required_fields():
    auth = A2AAuthentication(type=AuthType.BEARER, description="Use a token", required=True)
    out = ModelsAdapter.muxi_auth_to_sdk(auth)

    assert out["type"] == "bearer"
    assert out["description"] == "Use a token"
    assert out["required"] is True


def test_sdk_auth_round_trips_back_to_muxi():
    original = A2AAuthentication(type=AuthType.API_KEY, description="d", required=False)
    sdk_dict = ModelsAdapter.muxi_auth_to_sdk(original)
    back = ModelsAdapter.sdk_auth_to_muxi(sdk_dict)

    assert back.type == original.type
    assert back.description == original.description
    assert back.required == original.required


# ---------------------------------------------------------------------------
# Capability conversions
# ---------------------------------------------------------------------------


def test_capabilities_round_trip_preserves_description_and_metadata():
    muxi_caps = {
        "search": A2ACapability(
            name="search", description="d", enabled=True, metadata={"weight": 1.0}
        ),
    }
    sdk_caps = ModelsAdapter.muxi_capabilities_to_sdk(muxi_caps)
    back = ModelsAdapter.sdk_capabilities_to_muxi(sdk_caps)

    assert back["search"].name == "search"
    assert back["search"].enabled is True
    assert back["search"].description == "d"
    assert back["search"].metadata == {"weight": 1.0}
