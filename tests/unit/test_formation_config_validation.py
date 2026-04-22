"""Unit tests for formation config validation of embedding model slugs.

Covers VAL-CONFIG-001 (accept ``local/*`` slugs) and VAL-CONFIG-002
(regression: continue to accept ``openai/*``, ``ollama/*``,
``cohere/*``). Uses the lower-level ``_validate_llm_models`` method so
tests run against the slug validation path in isolation without
requiring a full formation file on disk.
"""

from __future__ import annotations

import pytest

from muxi.runtime.formation.config.validation import FormationValidator


def _llm_models_config(capability: str, model: str) -> list[dict]:
    """Build the minimal shape ``_validate_llm_models`` expects."""
    return [{capability: model}]


def _errors_mentioning(validator: FormationValidator, needle: str) -> list[str]:
    """Return validator errors matching ``needle`` (case-insensitive)."""
    return [e for e in validator.result.errors if needle.lower() in e.lower()]


class TestAcceptsLocalSlug:
    """VAL-CONFIG-001: the validator accepts ``local/*`` model slugs."""

    def test_accepts_local_slug(self):
        """The default Nomic v1.5 slug validates cleanly."""
        validator = FormationValidator()
        validator._validate_llm_models(
            _llm_models_config("embedding", "local/nomic-ai/nomic-embed-text-v1.5")
        )
        # No errors mentioning the embedding model name.
        assert not _errors_mentioning(validator, "embedding")
        assert not _errors_mentioning(validator, "local/nomic-ai")

    def test_accepts_local_slug_multilingual(self):
        """The multilingual Nomic v2 MoE slug validates cleanly."""
        validator = FormationValidator()
        validator._validate_llm_models(
            _llm_models_config("embedding", "local/nomic-ai/nomic-embed-text-v2-moe")
        )
        assert not _errors_mentioning(validator, "embedding")

    def test_accepts_local_slug_arbitrary_repo(self):
        """Any ``local/<org>/<repo>`` shape is forwarded to OneLLM.

        MUXI intentionally does not maintain a model allowlist --
        OneLLM's ``LocalProvider`` forwards the repo id to HuggingFace
        and the provider surfaces the resolution error if the repo is
        unknown. Config-time validation only checks well-formedness.
        """
        validator = FormationValidator()
        validator._validate_llm_models(
            _llm_models_config("embedding", "local/any-org/custom-embed-model")
        )
        assert not _errors_mentioning(validator, "embedding")


class TestAcceptsExistingSlugs:
    """VAL-CONFIG-002: regression -- cloud slugs continue to validate."""

    @pytest.mark.parametrize(
        "slug",
        [
            "openai/text-embedding-3-small",
            "openai/text-embedding-3-large",
            "openai/text-embedding-ada-002",
            "ollama/nomic-embed-text",
            "cohere/embed-english-v3.0",
            "cohere/embed-multilingual-v3.0",
            "voyage/voyage-3",
            "mistral/mistral-embed",
        ],
    )
    def test_accepts_existing_slug(self, slug: str):
        validator = FormationValidator()
        validator._validate_llm_models(_llm_models_config("embedding", slug))
        assert not _errors_mentioning(validator, "embedding")


class TestRejectsMalformedEmbeddingModel:
    """Empty / non-string slugs still fail loudly (regression check)."""

    def test_rejects_empty_string(self):
        validator = FormationValidator()
        validator._validate_llm_models(_llm_models_config("embedding", ""))
        errs = _errors_mentioning(validator, "embedding")
        assert errs, "Empty embedding model must surface an error"

    def test_rejects_whitespace_only(self):
        validator = FormationValidator()
        validator._validate_llm_models(_llm_models_config("embedding", "   "))
        errs = _errors_mentioning(validator, "embedding")
        assert errs, "Whitespace-only embedding model must surface an error"

    def test_rejects_non_string(self):
        validator = FormationValidator()
        validator._validate_llm_models([{"embedding": 42}])
        errs = _errors_mentioning(validator, "embedding")
        assert errs, "Non-string embedding model must surface an error"


class TestMultipleCapabilitiesCoexist:
    """An embedding slug alongside text/vision slugs validates cleanly."""

    def test_text_and_embedding_slugs_coexist(self):
        validator = FormationValidator()
        validator._validate_llm_models(
            [
                {"text": "openai/gpt-4o-mini"},
                {"embedding": "local/nomic-ai/nomic-embed-text-v1.5"},
            ]
        )
        assert not validator.result.errors
