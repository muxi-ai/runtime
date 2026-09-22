"""Contracts for the typed JSON decisions (structured incumbent).

Phase 0 measurement (engineering notes, system-one-structured-partb):
strict json_schema contracts on the three pre-request LLM decisions took
routing from 71.4% to 95.3% agent accuracy with 9/53 -> 0/53 parse
failures, credential detection to 96.7% kind accuracy, and kept
complexity at parity. These tests pin the contract shapes and the
tolerant parser that backs the prompt-enforced provider path.
"""

import pytest

from muxi.runtime.formation.credentials.handler import _credential_json_schema
from muxi.runtime.formation.overlord.agent_router import AgentRouter
from muxi.runtime.formation.workflow.analyzer import ANALYSIS_JSON_SCHEMA
from muxi.runtime.services.llm.llm import LLM, LLMError, LLMErrorType


def _parsing_llm() -> LLM:
    """LLM instance carrying only what _loads_json_object reads."""
    llm = LLM.__new__(LLM)
    llm._provider = "openai"
    llm.model_name = "openai/gpt-4o-mini"
    return llm


class TestRoutingSchema:
    def test_enum_is_live_agents_plus_null(self):
        schema = AgentRouter._routing_json_schema(["alpha", "beta"])
        agent = schema["schema"]["properties"]["agent"]
        assert agent["enum"] == ["alpha", "beta", None]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == {"security_block", "agent"}


class TestCredentialSchema:
    def test_service_enum_is_configured_services_plus_null(self):
        schema = _credential_json_schema(["github", "jira"])
        service = schema["schema"]["properties"]["service"]
        assert service["enum"] == ["github", "jira", None]
        assert schema["schema"]["properties"]["type"]["enum"] == [
            "CREDENTIAL_REQUEST",
            "SERVICE_USE",
            "NONE",
        ]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == {
            "type",
            "service",
            "confidence",
        }


class TestAnalysisSchema:
    def test_every_property_is_required(self):
        inner = ANALYSIS_JSON_SCHEMA["schema"]
        assert set(inner["required"]) == set(inner["properties"])
        assert ANALYSIS_JSON_SCHEMA["strict"] is True
        assert inner["additionalProperties"] is False

    def test_threat_type_enum_mirrors_the_prompt_categories(self):
        inner = ANALYSIS_JSON_SCHEMA["schema"]
        assert inner["properties"]["threat_type"]["enum"] == [
            "prompt_injection",
            "credential_fishing",
            "information_extraction",
            "jailbreak",
            None,
        ]


class TestLoadsJsonObject:
    def test_plain_json(self):
        assert _parsing_llm()._loads_json_object('{"a": 1}') == {"a": 1}

    def test_markdown_fenced(self):
        assert _parsing_llm()._loads_json_object('```json\n{"a": 1}\n```') == {"a": 1}

    def test_prose_wrapped(self):
        reply = "Sure! Here is the decision: {'a': 1} as requested.".replace("'", '"')
        assert _parsing_llm()._loads_json_object(reply) == {"a": 1}

    def test_non_object_json_raises(self):
        with pytest.raises(LLMError) as excinfo:
            _parsing_llm()._loads_json_object("[1, 2, 3]")
        assert excinfo.value.error_type is LLMErrorType.RESPONSE_PARSING

    def test_garbage_raises(self):
        with pytest.raises(LLMError):
            _parsing_llm()._loads_json_object("This is not JSON at all!")


class TestAppendSystemNote:
    def test_appends_to_first_system_message_without_mutation(self):
        messages = [
            {"role": "system", "content": "base"},
            {"role": "user", "content": "hi"},
        ]
        result = LLM._append_system_note(messages, "\n\nnote")
        assert result[0]["content"] == "base\n\nnote"
        assert messages[0]["content"] == "base"  # caller's dict untouched
        assert result[1] == messages[1]

    def test_inserts_system_message_when_none_exists(self):
        messages = [{"role": "user", "content": "hi"}]
        result = LLM._append_system_note(messages, "  note  ")
        assert result[0] == {"role": "system", "content": "note"}
        assert result[1] == messages[0]
