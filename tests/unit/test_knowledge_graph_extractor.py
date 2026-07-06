"""Unit tests for Memory Revamp Phase 1: knowledge graph extraction parsing.

The LLM is mocked throughout (unit-tier convention). Covers the prompt
contract, tolerant response parsing (fenced blocks, malformed JSON, wrong
shapes), per-item validation, and the real-time vs periodic confidence
thresholds.
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.memory.graph.extractor import (
    USER_ENTITY_NAME,
    KnowledgeGraphExtractor,
    _as_confidence,
)

VALID_RESPONSE = (
    "{"
    '"entities": ['
    '{"name": "Automaze", "type": "company", "attributes": {"user_role": "founder"}, '
    '"confidence": 0.95},'
    '{"name": "London", "type": "location", "confidence": 0.8}'
    "],"
    '"relationships": ['
    '{"from": "User", "from_type": "person", "to": "Automaze", "to_type": "company", '
    '"type": "founded", "confidence": 0.95},'
    '{"from": "User", "from_type": "person", "to": "London", "to_type": "location", '
    '"type": "lives_in", "confidence": 0.8}'
    "]"
    "}"
)


class FakeModel:
    """Minimal LLM stub capturing the prompt and returning a canned response."""

    def __init__(self, response):
        self.response = response
        self.prompts = []

    async def generate_text(self, prompt, caching=True):
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def extractor():
    return KnowledgeGraphExtractor(confidence_threshold=0.9)


class TestPrompt:
    def test_prompt_includes_vocabulary_and_conversation(self, extractor):
        prompt = extractor.build_prompt("User: I founded Automaze")
        assert "works_at" in prompt
        assert "company" in prompt
        assert USER_ENTITY_NAME in prompt
        assert "User: I founded Automaze" in prompt
        assert '"entities"' in prompt and '"relationships"' in prompt

    async def test_extract_disables_caching(self, extractor):
        model = FakeModel(VALID_RESPONSE)
        captured = {}

        async def generate_text(prompt, caching=True):
            captured["caching"] = caching
            return VALID_RESPONSE

        model.generate_text = generate_text
        await extractor.extract("User: hi", model)
        assert captured["caching"] is False


class TestParsing:
    def test_parses_plain_json(self, extractor):
        result = extractor.parse_response(VALID_RESPONSE, threshold=0.7)
        assert [e["name"] for e in result["entities"]] == ["Automaze", "London"]
        assert [r["type"] for r in result["relationships"]] == ["founded", "lives_in"]

    def test_parses_fenced_json(self, extractor):
        fenced = f"```json\n{VALID_RESPONSE}\n```"
        result = extractor.parse_response(fenced, threshold=0.7)
        assert len(result["entities"]) == 2

    def test_malformed_json_returns_empty(self, extractor):
        result = extractor.parse_response("not json at all {", threshold=0.7)
        assert result == {"entities": [], "relationships": []}

    def test_non_dict_payload_returns_empty(self, extractor):
        assert extractor.parse_response("[1, 2, 3]", threshold=0.7) == {
            "entities": [],
            "relationships": [],
        }

    def test_empty_response_returns_empty(self, extractor):
        assert extractor.parse_response("", threshold=0.7) == {
            "entities": [],
            "relationships": [],
        }
        assert extractor.parse_response(None, threshold=0.7) == {
            "entities": [],
            "relationships": [],
        }

    def test_missing_sections_tolerated(self, extractor):
        result = extractor.parse_response('{"entities": null}', threshold=0.7)
        assert result == {"entities": [], "relationships": []}


class TestValidation:
    def test_threshold_filters_low_confidence(self, extractor):
        result = extractor.parse_response(VALID_RESPONSE, threshold=0.9)
        assert [e["name"] for e in result["entities"]] == ["Automaze"]
        assert [r["type"] for r in result["relationships"]] == ["founded"]

    def test_entity_missing_fields_dropped(self, extractor):
        response = (
            '{"entities": [{"type": "company", "confidence": 0.95}, '
            '{"name": "", "type": "company", "confidence": 0.95}, '
            '{"name": "Acme", "confidence": 0.95}, "not-a-dict"], "relationships": []}'
        )
        assert extractor.parse_response(response, threshold=0.7)["entities"] == []

    def test_relationship_missing_endpoints_dropped(self, extractor):
        response = (
            '{"entities": [], "relationships": ['
            '{"to": "Acme", "type": "works_at", "confidence": 0.95},'
            '{"from": "User", "type": "works_at", "confidence": 0.95},'
            '{"from": "User", "to": "Acme", "confidence": 0.95}]}'
        )
        assert extractor.parse_response(response, threshold=0.7)["relationships"] == []

    def test_invalid_confidence_dropped(self, extractor):
        response = (
            '{"entities": ['
            '{"name": "A", "type": "company", "confidence": 1.5},'
            '{"name": "B", "type": "company", "confidence": -0.1},'
            '{"name": "C", "type": "company", "confidence": null},'
            '{"name": "D", "type": "company"}], "relationships": []}'
        )
        assert extractor.parse_response(response, threshold=0.0)["entities"] == []

    def test_non_dict_attributes_normalized(self, extractor):
        response = (
            '{"entities": [{"name": "A", "type": "company", "attributes": "junk", '
            '"confidence": 0.95}], "relationships": []}'
        )
        entities = extractor.parse_response(response, threshold=0.7)["entities"]
        assert entities[0]["attributes"] == {}

    def test_optional_endpoint_types(self, extractor):
        response = (
            '{"entities": [], "relationships": [{"from": "User", "to": "Acme", '
            '"type": "works_at", "confidence": 0.95}]}'
        )
        relationship = extractor.parse_response(response, threshold=0.7)["relationships"][0]
        assert relationship["from_type"] is None
        assert relationship["to_type"] is None

    def test_long_names_truncated(self, extractor):
        long_name = "x" * 300
        response = (
            '{"entities": [{"name": "' + long_name + '", "type": "company", '
            '"confidence": 0.95}], "relationships": []}'
        )
        entities = extractor.parse_response(response, threshold=0.7)["entities"]
        assert len(entities[0]["name"]) == 255


class TestExtract:
    async def test_extract_uses_instance_threshold(self):
        extractor = KnowledgeGraphExtractor(confidence_threshold=0.9)
        result = await extractor.extract("User: hi", FakeModel(VALID_RESPONSE))
        assert [e["name"] for e in result["entities"]] == ["Automaze"]

    async def test_extract_threshold_override(self):
        extractor = KnowledgeGraphExtractor(confidence_threshold=0.9)
        result = await extractor.extract(
            "User: hi", FakeModel(VALID_RESPONSE), confidence_threshold=0.7
        )
        assert len(result["entities"]) == 2

    async def test_extract_propagates_model_errors(self):
        # The service layer owns failure isolation; the extractor itself
        # surfaces model errors so callers can log them.
        extractor = KnowledgeGraphExtractor()
        with pytest.raises(RuntimeError):
            await extractor.extract("User: hi", FakeModel(RuntimeError("model down")))


class TestConfidenceCoercion:
    def test_valid_values(self):
        assert _as_confidence(0.5) == 0.5
        assert _as_confidence(1) == 1.0
        assert _as_confidence("0.7") == 0.7

    def test_invalid_values(self):
        assert _as_confidence(None) is None
        assert _as_confidence(True) is None
        assert _as_confidence("high") is None
        assert _as_confidence(1.01) is None
        assert _as_confidence(-0.01) is None
        assert _as_confidence({}) is None
