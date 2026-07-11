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
