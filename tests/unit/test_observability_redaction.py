"""
Unit tests for observability PII/secret redaction.

Covers the WS2 change: redaction is applied to every event payload by default
(regardless of event type), with an explicit per-call ``skip_redaction`` opt-out.
"""

import inspect

from muxi.runtime.services.observability import _redact_data_recursive, observe


class TestRedactDataRecursive:
    """The recursive redactor backs redaction for all event payloads."""

    def test_redacts_string_secret(self):
        result = _redact_data_recursive("key sk-abcdefghijklmnopqrstuvwxyz012345")
        assert "sk-****" in result
        assert "abcdefghijklmnop" not in result

    def test_redacts_nested_dict_and_list(self):
        data = {
            "outer": {
                "api_key": "api_key=abcdefghijklmnopqrstuvwxyz",
                "items": ["mail me at john.doe@example.com", "safe value"],
            },
            "count": 3,
        }
        result = _redact_data_recursive(data)

        assert "abcdefghijklmnop" not in result["outer"]["api_key"]
        assert "john.doe" not in result["outer"]["items"][0]
        assert result["outer"]["items"][1] == "safe value"
        # Non-string scalars pass through untouched
        assert result["count"] == 3

    def test_preserves_non_string_scalars(self):
        data = {"n": 42, "flag": True, "nothing": None, "ratio": 1.5}
        assert _redact_data_recursive(data) == data

    def test_preserves_tuple_type(self):
        result = _redact_data_recursive(("safe", "also safe"))
        assert isinstance(result, tuple)
        assert result == ("safe", "also safe")


class TestObserveRedactionContract:
    """observe() exposes a skip_redaction opt-out and redacts by default."""

    def test_observe_accepts_skip_redaction(self):
        params = inspect.signature(observe).parameters
        assert "skip_redaction" in params
        # Defaults to redaction ON (skip_redaction defaults to False)
        assert params["skip_redaction"].default is False
