"""
Unit tests for the entity-redaction layer (utils/redaction).

These tests do not require the optional ``presidio-analyzer`` dependency: span
masking and the registry are pure logic, and the factory's regex-only fallback
is exercised directly.
"""

from muxi.runtime.utils.redaction import (
    Span,
    build_entity_detector,
    get_entity_detector,
    mask_spans,
    set_entity_detector,
)
from muxi.runtime.utils.security import redact_sensitive_content


class _FakeDetector:
    """Deterministic stand-in for an NER detector."""

    def __init__(self, spans_by_text):
        self._spans_by_text = spans_by_text

    def detect(self, text, language="en"):
        return self._spans_by_text.get(text, [])


class TestMaskSpans:
    def test_masks_with_indexed_tokens(self):
        text = "Jane Doe met Acme Corp"
        spans = [
            Span(0, 8, "PERSON", 0.9),
            Span(13, 22, "ORG", 0.85),
        ]
        result = mask_spans(text, spans)
        assert result == "[PERSON_1] met [ORG_1]"

    def test_repeated_value_reuses_token(self):
        text = "Jane and Jane again"
        spans = [Span(0, 4, "PERSON", 0.9), Span(9, 13, "PERSON", 0.9)]
        result = mask_spans(text, spans)
        assert result == "[PERSON_1] and [PERSON_1] again"

    def test_distinct_values_increment_index(self):
        text = "Jane and John"
        spans = [Span(0, 4, "PERSON", 0.9), Span(9, 13, "PERSON", 0.9)]
        result = mask_spans(text, spans)
        assert result == "[PERSON_1] and [PERSON_2]"

    def test_below_threshold_not_masked(self):
        text = "Maybe Jane"
        spans = [Span(6, 10, "PERSON", 0.2)]
        assert mask_spans(text, spans, threshold=0.5) == text

    def test_overlapping_spans_longest_wins(self):
        text = "New York City"
        spans = [Span(0, 8, "ADDRESS", 0.8), Span(0, 13, "ADDRESS", 0.7)]
        result = mask_spans(text, spans)
        assert result == "[ADDRESS_1]"

    def test_no_spans_returns_original(self):
        assert mask_spans("nothing here", []) == "nothing here"


class TestRegistry:
    def teardown_method(self):
        set_entity_detector(None)

    def test_set_and_get(self):
        detector = _FakeDetector({})
        set_entity_detector(detector)
        assert get_entity_detector() is detector
        set_entity_detector(None)
        assert get_entity_detector() is None


class TestBuildEntityDetector:
    def test_disabled_returns_none(self):
        assert build_entity_detector(enabled=False) is None

    def test_missing_dependency_falls_back_to_none(self):
        # presidio-analyzer is not installed in the test env -> regex-only.
        import importlib.util

        if importlib.util.find_spec("presidio_analyzer") is None:
            assert build_entity_detector(enabled=True) is None


class TestPresidioLabelMapping:
    """The label mapping / DOB filtering is pure logic, testable without presidio."""

    def _map(self, entity_type, text="", start=0):
        from muxi.runtime.utils.redaction.entity import PresidioDetector

        return PresidioDetector._map_label(entity_type, text, start)

    def test_person_location_org_mapping(self):
        assert self._map("PERSON") == "PERSON"
        assert self._map("LOCATION") == "ADDRESS"
        assert self._map("ORGANIZATION") == "ORG"

    def test_financial_entities_collapse_to_financial(self):
        for et in ("IBAN_CODE", "US_BANK_NUMBER", "CRYPTO", "CREDIT_CARD"):
            assert self._map(et) == "FINANCIAL"

    def test_date_with_birth_context_is_dob(self):
        text = "She was born on 1990-01-01"
        start = text.index("1990")
        assert self._map("DATE_TIME", text, start) == "DOB"

    def test_date_without_birth_context_is_ignored(self):
        text = "The meeting is on 2026-01-01"
        start = text.index("2026")
        assert self._map("DATE_TIME", text, start) is None

    def test_unmapped_entity_returns_none(self):
        assert self._map("URL") is None


class TestSecurityComposition:
    def teardown_method(self):
        set_entity_detector(None)

    def test_entity_layer_runs_after_regex(self):
        # Regex masks the email; the fake detector masks the name in the result.
        original = "Contact Jane Doe at jane@example.com"
        regex_only = redact_sensitive_content(original)
        assert "jane" not in regex_only.split("@")[0].split()[-1]  # email masked

        set_entity_detector(_FakeDetector({regex_only: [Span(8, 16, "PERSON", 0.95)]}))
        composed = redact_sensitive_content(original)
        assert "[PERSON_1]" in composed
        assert "Jane Doe" not in composed

    def test_no_detector_is_regex_only(self):
        set_entity_detector(None)
        text = "Just a normal sentence about Python"
        assert redact_sensitive_content(text) == text
