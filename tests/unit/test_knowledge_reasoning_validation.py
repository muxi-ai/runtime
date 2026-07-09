"""Unit tests for fail-fast config validation of reasoning-RAG settings.

Validates the new agent knowledge keys introduced by the
knowledge-reasoning-rag PRD (Phase 1): ``reasoning_threshold``, the
``tree`` settings block, and the per-source ``retrieval:`` field.
Exercises ``FormationValidator._validate_agent_knowledge_config`` directly,
matching the pattern of ``test_formation_config_validation.py``.
"""

from __future__ import annotations

import pytest

from muxi.runtime.formation.config.validation import FormationValidator


def _validate(knowledge_config: dict) -> FormationValidator:
    validator = FormationValidator()
    validator._validate_agent_knowledge_config(knowledge_config)
    return validator


def _base_source(**extra) -> dict:
    return {"path": "knowledge/manual.md", "description": "manual", **extra}


class TestReasoningThreshold:
    @pytest.mark.parametrize("value", [0, 1, 40000, 500000])
    def test_accepts_non_negative_integers(self, value):
        validator = _validate({"enabled": True, "reasoning_threshold": value})
        assert not validator.result.errors

    @pytest.mark.parametrize("value", [-1, 1.5, "40000", None, True, [40000]])
    def test_rejects_invalid_values(self, value):
        validator = _validate({"enabled": True, "reasoning_threshold": value})
        assert any("reasoning_threshold" in e for e in validator.result.errors)

    def test_absent_key_is_valid(self):
        validator = _validate({"enabled": True, "sources": [_base_source()]})
        assert not validator.result.errors


class TestTreeSettings:
    def test_accepts_full_valid_block(self):
        validator = _validate(
            {
                "enabled": True,
                "tree": {
                    "model": "openai/gpt-4o-mini",
                    "max_depth": 3,
                    "max_pages_per_node": 10,
                    "max_tokens_per_node": 20000,
                    "max_document_tokens": 500000,
                },
            }
        )
        assert not validator.result.errors

    def test_accepts_null_model(self):
        validator = _validate({"enabled": True, "tree": {"model": None}})
        assert not validator.result.errors

    def test_rejects_non_dict_tree(self):
        validator = _validate({"enabled": True, "tree": "yes"})
        assert any("'tree' must be a dictionary" in e for e in validator.result.errors)

    def test_rejects_unknown_tree_key(self):
        validator = _validate({"enabled": True, "tree": {"max_dpeth": 3}})
        assert any("not recognized" in e for e in validator.result.errors)

    @pytest.mark.parametrize(
        "key", ["max_depth", "max_pages_per_node", "max_tokens_per_node", "max_document_tokens"]
    )
    @pytest.mark.parametrize("value", [0, -1, "3", 1.5, True])
    def test_rejects_non_positive_int_limits(self, key, value):
        validator = _validate({"enabled": True, "tree": {key: value}})
        assert any(key in e for e in validator.result.errors)

    def test_rejects_model_that_is_neither_alias_nor_qualified(self):
        validator = _validate({"enabled": True, "tree": {"model": "fast"}})
        assert any("neither a defined alias" in e for e in validator.result.errors)

    def test_accepts_model_matching_defined_alias(self):
        validator = FormationValidator()
        validator._model_aliases = {"fast": "openai/gpt-4o-mini"}
        validator._validate_agent_knowledge_config({"enabled": True, "tree": {"model": "fast"}})
        assert not validator.result.errors


class TestSourceRetrievalMode:
    @pytest.mark.parametrize("mode", ["vector", "tree"])
    def test_accepts_supported_modes(self, mode):
        validator = _validate({"enabled": True, "sources": [_base_source(retrieval=mode)]})
        assert not validator.result.errors

    def test_absent_retrieval_is_valid(self):
        validator = _validate({"enabled": True, "sources": [_base_source()]})
        assert not validator.result.errors

    @pytest.mark.parametrize("mode", ["tree-vector", "hybrid"])
    def test_rejects_reserved_modes_with_phase_note(self, mode):
        validator = _validate({"enabled": True, "sources": [_base_source(retrieval=mode)]})
        assert any("not yet supported" in e for e in validator.result.errors)

    @pytest.mark.parametrize("mode", ["faiss", "", "  ", 3, None])
    def test_rejects_unknown_modes(self, mode):
        validator = _validate({"enabled": True, "sources": [_base_source(retrieval=mode)]})
        assert any("retrieval" in e for e in validator.result.errors)
