"""
Unit tests for the Response Envelope UI affordances (P1).

Covers:
- Widget builders (options, action_link) and the structural provenance rule
- Size clamps (per-widget and per-envelope, load-validated defaults)
- ui_response hint resolution (deterministic pinning vs ignored hints)
- Envelope additivity: responses without widgets serialize byte-identically
  to the pre-feature envelope, both directly and nested inside the API
  response (the critical zero-behavior-change pin)
- links: formation config section validation
"""

import json

import pytest

from muxi.runtime.datatypes.api import APIEventType, APIObjectType
from muxi.runtime.datatypes.response import MuxiResponse
from muxi.runtime.datatypes.ui import (
    UI_ENVELOPE_MAX_BYTES,
    UI_ENVELOPE_MAX_WIDGETS,
    UI_WIDGET_MAX_BYTES,
    UIProvenance,
    build_action_link_widget,
    build_options_widget,
    clamp_ui,
    decode_ui_callback,
    encode_ui_callback,
    resolve_ui_response,
)
from muxi.runtime.formation.server.responses import create_success_response


class TestOptionsWidget:
    def test_builds_options_widget(self):
        widget = build_options_widget(
            prompt="Which account?",
            options=[
                {"value": "acme-prod", "label": "Acme Prod"},
                {"value": "acme-dev"},
            ],
        )
        assert widget["type"] == "options"
        assert widget["id"].startswith("ui_")
        assert widget["prompt"] == "Which account?"
        assert widget["multi"] is False
        assert widget["options"] == [
            {"value": "acme-prod", "label": "Acme Prod"},
            {"value": "acme-dev", "label": "acme-dev"},  # label falls back to value
        ]

    def test_empty_options_returns_none(self):
        assert build_options_widget(prompt="?", options=[]) is None
        assert build_options_widget(prompt="?", options=[{"label": "no value"}]) is None

    def test_widget_ids_are_unique(self):
        opts = [{"value": "a", "label": "a"}]
        first = build_options_widget(prompt="?", options=opts)
        second = build_options_widget(prompt="?", options=opts)
        assert first["id"] != second["id"]


class TestActionLinkWidget:
    def test_builds_action_link(self):
        widget = build_action_link_widget(
            label="Connect Jira",
            url="https://auth.acme.com/connect/jira",
            source=UIProvenance.FORMATION_CONFIG,
            hint="Opens your company's credential portal",
        )
        assert widget["type"] == "action_link"
        assert widget["id"].startswith("ui_")
        assert widget["label"] == "Connect Jira"
        assert widget["url"] == "https://auth.acme.com/connect/jira"
        assert widget["hint"] == "Opens your company's credential portal"

    def test_provenance_is_mandatory(self):
        # The structural enforcement of the provenance rule: no
        # UIProvenance member, no widget — a producer cannot pass a
        # free-form string (e.g. one an LLM produced) as a source.
        with pytest.raises(ValueError, match="provenance"):
            build_action_link_widget(
                label="Evil", url="https://evil.example.com", source="llm_says_so"
            )
        with pytest.raises(ValueError, match="provenance"):
            build_action_link_widget(label="Evil", url="https://evil.example.com", source=None)

    def test_rejects_non_http_urls(self):
        for bad_url in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x", "", None):
            assert (
                build_action_link_widget(label="x", url=bad_url, source=UIProvenance.TOOL_RESULT)
                is None
            )

    def test_hint_omitted_when_absent(self):
        widget = build_action_link_widget(
            label="Portal", url="https://portal.acme.com", source=UIProvenance.TRIGGER_PAYLOAD
        )
        assert "hint" not in widget


class TestSizeClamps:
    def test_oversized_widget_dropped(self):
        big = build_options_widget(
            prompt="x" * UI_WIDGET_MAX_BYTES,
            options=[{"value": "a", "label": "a"}],
        )
        small = build_options_widget(prompt="?", options=[{"value": "a", "label": "a"}])
        clamped = clamp_ui([big, small])
        assert clamped == [small]

    def test_envelope_widget_count_cap(self):
        widgets = [
            build_options_widget(prompt=f"q{i}", options=[{"value": "a", "label": "a"}])
            for i in range(UI_ENVELOPE_MAX_WIDGETS + 3)
        ]
        assert len(clamp_ui(widgets)) == UI_ENVELOPE_MAX_WIDGETS

    def test_envelope_byte_cap(self):
        # Widgets individually under the per-widget cap but collectively
        # over the envelope cap
        widgets = [
            build_options_widget(
                prompt="x" * (UI_WIDGET_MAX_BYTES - 200),
                options=[{"value": "a", "label": "a"}],
            )
            for _ in range(UI_ENVELOPE_MAX_WIDGETS)
        ]
        clamped = clamp_ui(widgets)
        total = sum(len(json.dumps(w).encode("utf-8")) for w in clamped)
        assert total <= UI_ENVELOPE_MAX_BYTES
        assert 0 < len(clamped) < len(widgets)

    def test_none_entries_skipped(self):
        assert clamp_ui([None, None]) == []


class TestUIResponseResolution:
    def test_matching_hint_pins_value(self):
        assert (
            resolve_ui_response(
                {"id": "ui_abc", "value": "acme-dev"}, "ui_abc", ["acme-prod", "acme-dev"]
            )
            == "acme-dev"
        )

    def test_unknown_id_ignored(self):
        assert (
            resolve_ui_response(
                {"id": "ui_stale", "value": "acme-dev"}, "ui_abc", ["acme-prod", "acme-dev"]
            )
            is None
        )

    def test_value_not_offered_ignored(self):
        # A matching id cannot smuggle in an arbitrary value
        assert (
            resolve_ui_response({"id": "ui_abc", "value": "not-an-option"}, "ui_abc", ["acme-prod"])
            is None
        )

    def test_no_pending_widget_ignored(self):
        assert resolve_ui_response({"id": "ui_abc", "value": "a"}, None, None) is None
        assert resolve_ui_response(None, "ui_abc", ["a"]) is None

    def test_index_hint_resolves_to_offered_value(self):
        # Channel button presses carry {id, index} (decode_ui_callback
        # shape); the index resolves against the offered options in order.
        assert (
            resolve_ui_response({"id": "ui_abc", "index": 1}, "ui_abc", ["acme-prod", "acme-dev"])
            == "acme-dev"
        )

    def test_index_out_of_range_ignored(self):
        assert resolve_ui_response({"id": "ui_abc", "index": 5}, "ui_abc", ["a", "b"]) is None
        assert resolve_ui_response({"id": "ui_abc", "index": -1}, "ui_abc", ["a", "b"]) is None

    def test_index_must_be_int(self):
        assert resolve_ui_response({"id": "ui_abc", "index": "1"}, "ui_abc", ["a", "b"]) is None
        assert resolve_ui_response({"id": "ui_abc", "index": True}, "ui_abc", ["a", "b"]) is None

    def test_explicit_value_wins_over_index(self):
        assert (
            resolve_ui_response({"id": "ui_abc", "value": "a", "index": 1}, "ui_abc", ["a", "b"])
            == "a"
        )


class TestUICallbackEncoding:
    """Channel button callback round-trip (Response Envelope UI, P3)."""

    def test_encode_decode_round_trip(self):
        widget = build_options_widget(prompt="?", options=[{"value": "a"}, {"value": "b"}])
        encoded = encode_ui_callback(widget["id"], 1)
        assert decode_ui_callback(encoded) == {"id": widget["id"], "index": 1}

    def test_encoding_fits_telegram_callback_data_limit(self):
        # Telegram callback_data is capped at 64 bytes; widget ids are
        # fixed-length so index encoding always fits, regardless of how
        # long the option values are.
        widget = build_options_widget(
            prompt="?", options=[{"value": "x" * 500, "label": "y" * 500}]
        )
        encoded = encode_ui_callback(widget["id"], 24)
        assert len(encoded.encode("utf-8")) <= 64

    def test_foreign_callback_data_decodes_to_none(self):
        # Channels routinely deliver callback payloads MUXI did not
        # produce; those must not become reply hints.
        for data in ("approve", "ui_abc", "ui_abc#x", "not-ui#1", "", None, 7, {"id": "x"}):
            assert decode_ui_callback(data) is None

    def test_decoded_hint_pins_through_resolve(self):
        widget = build_options_widget(prompt="?", options=[{"value": "a"}, {"value": "b"}])
        option_values = [o["value"] for o in widget["options"]]
        hint = decode_ui_callback(encode_ui_callback(widget["id"], 0))
        assert resolve_ui_response(hint, widget["id"], option_values) == "a"


class TestEnvelopeAdditivity:
    """The zero-behavior-change discipline: no widgets, no wire change."""

    def _nested_message_json(self, response: MuxiResponse) -> dict:
        api_response = create_success_response(
            APIObjectType.MESSAGE,
            APIEventType.CHAT_COMPLETED,
            {"message": response, "user_id": "0"},
            None,
        )
        return api_response.model_dump()["data"]["message"]

    def test_no_ui_key_without_widgets_nested(self):
        # This is the exact serialization path of POST /chat
        # (stream=False): MuxiResponse nested in APIResponse.data.
        response = MuxiResponse(role="assistant", content="hello", metadata={"session_id": "s1"})
        message = self._nested_message_json(response)
        assert "ui" not in message
        # Pin the full pre-feature key set so any future envelope drift
        # fails loudly.
        assert set(message.keys()) == {"role", "content", "artifacts", "metadata"}

    def test_no_ui_key_without_widgets_direct(self):
        response = MuxiResponse(role="assistant", content="hello")
        assert "ui" not in response.model_dump()

    def test_ui_key_present_with_widgets(self):
        widget = build_options_widget(prompt="?", options=[{"value": "a", "label": "a"}])
        response = MuxiResponse(role="assistant", content="pick one", ui=[widget])
        message = self._nested_message_json(response)
        assert message["ui"] == [widget]
        assert response.model_dump()["ui"] == [widget]

    def test_empty_ui_list_omitted(self):
        response = MuxiResponse(role="assistant", content="hello", ui=[])
        message = self._nested_message_json(response)
        assert "ui" not in message
        assert "ui" not in response.model_dump()


class _StubToolResult:
    """Minimal stand-in for ToolExecutionResult (only .result/.tool_name used)."""

    def __init__(self, result, tool_name="portal_tool"):
        self.result = result
        self.tool_name = tool_name


class TestToolResultLinkExtraction:
    """Agent._extract_link_widgets: the tool-result action_link producer."""

    def _extract(self, monkeypatch, tool_results):
        """Run extraction with ui.emitted events captured."""
        from muxi.runtime.datatypes.observability import ConversationEvents
        from muxi.runtime.formation.agents import agent as agent_module
        from muxi.runtime.formation.agents.agent import Agent

        emitted = []
        real_observe = agent_module.observability.observe

        def capture(event_type=None, **kwargs):
            if event_type == ConversationEvents.UI_EMITTED:
                emitted.append(kwargs.get("data"))
                return None
            return real_observe(event_type=event_type, **kwargs)

        monkeypatch.setattr(agent_module.observability, "observe", capture)

        stub = object.__new__(Agent)  # method uses no instance state
        widgets = Agent._extract_link_widgets(stub, tool_results)
        return widgets, emitted

    def test_link_extracted_and_emitted(self, monkeypatch):
        widgets, emitted = self._extract(
            monkeypatch,
            [
                _StubToolResult(
                    {"_link": {"url": "https://portal.acme.com", "label": "Open portal"}}
                )
            ],
        )
        assert widgets and widgets[0]["type"] == "action_link"
        assert widgets[0]["url"] == "https://portal.acme.com"
        assert len(emitted) == 1
        assert emitted[0]["producer"] == "tool_result:portal_tool"
        assert emitted[0]["widget_id"] == widgets[0]["id"]

    def test_clamped_widget_not_emitted(self, monkeypatch):
        # A widget dropped by the size clamp must NOT count as emitted:
        # clamp first, then emit — same order as Overlord._attach_ui.
        oversized = _StubToolResult(
            {
                "_link": {
                    "url": "https://portal.acme.com/huge",
                    "label": "x" * (UI_WIDGET_MAX_BYTES + 1),
                }
            }
        )
        widgets, emitted = self._extract(monkeypatch, [oversized])
        assert widgets is None
        assert emitted == []

    def test_mixed_clamp_emits_survivors_only(self, monkeypatch):
        small = _StubToolResult(
            {"_link": {"url": "https://portal.acme.com/ok", "label": "OK"}},
            tool_name="small_tool",
        )
        oversized = _StubToolResult(
            {
                "_link": {
                    "url": "https://portal.acme.com/huge",
                    "label": "x" * (UI_WIDGET_MAX_BYTES + 1),
                }
            },
            tool_name="huge_tool",
        )
        widgets, emitted = self._extract(monkeypatch, [oversized, small])
        assert len(widgets) == 1
        assert widgets[0]["url"] == "https://portal.acme.com/ok"
        assert len(emitted) == 1
        assert emitted[0]["producer"] == "tool_result:small_tool"

    def test_nested_link_and_non_dict_results_ignored(self, monkeypatch):
        widgets, emitted = self._extract(
            monkeypatch,
            [
                _StubToolResult("plain string result"),
                _StubToolResult({"result": {"_link": {"url": "https://nested.acme.com"}}}),
                _StubToolResult({"_link": "not-a-dict"}),
            ],
        )
        assert len(widgets) == 1
        assert widgets[0]["url"] == "https://nested.acme.com"
        assert len(emitted) == 1


class TestLinksConfigValidation:
    def _validate(self, links):
        from muxi.runtime.formation.config.validation import FormationValidator

        validator = FormationValidator()
        validator._validate_links_config(links)
        return validator.result

    def test_valid_links_config(self):
        result = self._validate(
            {
                "github": {
                    "label": "Connect GitHub",
                    "url": "https://auth.acme.com/connect/github",
                    "hint": "Company credential portal",
                },
                "credential_portal": {"url": "https://auth.acme.com"},
            }
        )
        assert result.errors == []

    def test_missing_url_rejected(self):
        result = self._validate({"github": {"label": "No URL"}})
        assert any("links.github.url" in e for e in result.errors)

    def test_non_http_url_rejected(self):
        result = self._validate({"github": {"url": "javascript:alert(1)"}})
        assert any("links.github.url" in e for e in result.errors)

    def test_non_dict_entry_rejected(self):
        result = self._validate({"github": "https://github.com"})
        assert any("links.github" in e for e in result.errors)

    def test_non_dict_section_rejected(self):
        result = self._validate(["not", "a", "dict"])
        assert any("links must be a dictionary" in e for e in result.errors)
