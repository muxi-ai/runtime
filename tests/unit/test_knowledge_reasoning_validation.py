"""Unit tests for fail-fast config validation of reasoning-RAG settings.

Validates the agent knowledge keys introduced by the
knowledge-reasoning-rag PRD: ``reasoning_threshold``, the ``tree`` settings
block (including the Phase 2/3 ``terminator_model`` /
``max_sufficiency_rounds`` / ``max_fetched_nodes_pct`` keys), the
per-source ``retrieval:`` field (all four modes active as of Phase 2/3),
and the Phase 4 per-source ``agent_tree:`` block. Exercises
``FormationValidator._validate_agent_knowledge_config`` directly, matching
the pattern of ``test_formation_config_validation.py``.
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
    @pytest.mark.parametrize("mode", ["vector", "tree", "tree-vector", "hybrid"])
    def test_accepts_supported_modes(self, mode):
        """Phase 2/3 activated tree-vector and hybrid - all four modes load."""
        validator = _validate({"enabled": True, "sources": [_base_source(retrieval=mode)]})
        assert not validator.result.errors

    def test_absent_retrieval_is_valid(self):
        validator = _validate({"enabled": True, "sources": [_base_source()]})
        assert not validator.result.errors

    @pytest.mark.parametrize("mode", ["faiss", "", "  ", 3, None])
    def test_rejects_unknown_modes(self, mode):
        validator = _validate({"enabled": True, "sources": [_base_source(retrieval=mode)]})
        assert any("retrieval" in e for e in validator.result.errors)


class TestHybridTreeSettings:
    """Phase 2/3 tree keys: terminator_model + hybrid loop bounds."""

    def test_accepts_full_hybrid_block(self):
        validator = _validate(
            {
                "enabled": True,
                "tree": {
                    "model": "openai/gpt-4o-mini",
                    "terminator_model": "openai/gpt-4o-mini",
                    "max_sufficiency_rounds": 3,
                    "max_fetched_nodes_pct": 50,
                },
            }
        )
        assert not validator.result.errors

    def test_accepts_null_terminator_model(self):
        validator = _validate({"enabled": True, "tree": {"terminator_model": None}})
        assert not validator.result.errors

    def test_rejects_unqualified_terminator_model(self):
        validator = _validate({"enabled": True, "tree": {"terminator_model": "cheap"}})
        assert any("neither a defined alias" in e for e in validator.result.errors)

    def test_accepts_terminator_model_matching_alias(self):
        validator = FormationValidator()
        validator._model_aliases = {"cheap": "openai/gpt-4o-mini"}
        validator._validate_agent_knowledge_config(
            {"enabled": True, "tree": {"terminator_model": "cheap"}}
        )
        assert not validator.result.errors

    @pytest.mark.parametrize("value", [0, -1, "3", 1.5, True])
    def test_rejects_non_positive_sufficiency_rounds(self, value):
        validator = _validate({"enabled": True, "tree": {"max_sufficiency_rounds": value}})
        assert any("max_sufficiency_rounds" in e for e in validator.result.errors)

    @pytest.mark.parametrize("value", [0, -1, 101, "50", 1.5, True])
    def test_rejects_out_of_range_fetched_nodes_pct(self, value):
        validator = _validate({"enabled": True, "tree": {"max_fetched_nodes_pct": value}})
        assert any("max_fetched_nodes_pct" in e for e in validator.result.errors)

    @pytest.mark.parametrize("value", [1, 50, 100])
    def test_accepts_valid_fetched_nodes_pct(self, value):
        validator = _validate({"enabled": True, "tree": {"max_fetched_nodes_pct": value}})
        assert not validator.result.errors


class TestAgentTreeBlock:
    """Phase 4 per-source ``agent_tree:`` validation."""

    @pytest.mark.parametrize("regenerate", ["manual", "on-source-change", "on-formation-load"])
    def test_accepts_valid_block(self, regenerate):
        source = _base_source(retrieval="hybrid", agent_tree={"regenerate": regenerate})
        validator = _validate({"enabled": True, "sources": [source]})
        assert not validator.result.errors

    def test_accepts_empty_block_defaults_to_manual(self):
        source = _base_source(retrieval="tree", agent_tree={})
        validator = _validate({"enabled": True, "sources": [source]})
        assert not validator.result.errors

    def test_rejects_non_dict_block(self):
        source = _base_source(retrieval="tree", agent_tree="yes")
        validator = _validate({"enabled": True, "sources": [source]})
        assert any("'agent_tree' must be a dictionary" in e for e in validator.result.errors)

    def test_rejects_unknown_key(self):
        source = _base_source(retrieval="tree", agent_tree={"rebuild": "manual"})
        validator = _validate({"enabled": True, "sources": [source]})
        assert any("not recognized" in e for e in validator.result.errors)

    def test_rejects_unknown_regenerate_trigger(self):
        source = _base_source(retrieval="tree", agent_tree={"regenerate": "hourly"})
        validator = _validate({"enabled": True, "sources": [source]})
        assert any("regenerate" in e for e in validator.result.errors)

    @pytest.mark.parametrize("retrieval", [None, "vector"])
    def test_requires_tree_serving_retrieval_mode(self, retrieval):
        source = _base_source(agent_tree={"regenerate": "manual"})
        if retrieval is not None:
            source["retrieval"] = retrieval
        validator = _validate({"enabled": True, "sources": [source]})
        assert any("requires an explicit 'retrieval' mode" in e for e in validator.result.errors)

    def test_rejects_agent_tree_on_remote_source(self):
        source = {
            "url": "https://example.com/docs.md",
            "description": "remote docs",
            "agent_tree": {"regenerate": "manual"},
        }
        validator = _validate({"enabled": True, "sources": [source]})
        assert any("not supported on remote" in e for e in validator.result.errors)
