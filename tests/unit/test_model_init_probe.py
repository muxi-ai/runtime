"""Unit tests for the formation-init model probe.

The probe verifies that every model declared in ``formation._capability_models``
resolves through OneLLM at formation init time, so misspelled or
shape-invalid slugs (e.g. ``local/all-MiniLM-L6-v2`` instead of
``local/sentence-transformers/all-MiniLM-L6-v2``) abort startup
rather than degrading silently on first user request.

Failure classification under test:

- ``ResourceNotFoundError``      -> FATAL (raises ConfigurationValidationError)
- ``InvalidRequestError``        -> FATAL  (HF validation = bare-name slug)
- ``AuthenticationError``        -> WARN   (continue; can't distinguish
                                            missing vs invalid key reliably)
- ``RateLimitError``             -> WARN   (transient)
- non-OneLLMError exceptions     -> WARN   (probe-machinery bug)

Plus structural tests for capability dedup, probe-shape selection
(embedding vs chat), serial fail-fast ordering, and that the bare-name
fatal message includes the operator-actionable hint.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from onellm.errors import (
    AuthenticationError,
    InvalidRequestError,
    OneLLMError,
    RateLimitError,
    ResourceNotFoundError,
)

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation import initialization as init_mod


def _make_formation(capability_models: dict) -> SimpleNamespace:
    """Build a minimal formation stand-in with just the field the probe reads."""
    return SimpleNamespace(_capability_models=capability_models)


class TestClassification:
    """``_classify_probe_failure`` is pure - lock its contract."""

    def test_resource_not_found_is_fatal(self):
        exc = ResourceNotFoundError("missing", provider="local", status_code=404)
        assert init_mod._classify_probe_failure(exc) == "fatal"

    def test_invalid_request_is_fatal(self):
        exc = InvalidRequestError("bad slug", provider="local", status_code=400)
        assert init_mod._classify_probe_failure(exc) == "fatal"

    def test_authentication_is_warn(self):
        exc = AuthenticationError("nope", provider="openai", status_code=401)
        assert init_mod._classify_probe_failure(exc) == "warn"

    def test_rate_limit_is_warn(self):
        exc = RateLimitError("slow down", provider="anthropic", status_code=429)
        assert init_mod._classify_probe_failure(exc) == "warn"

    def test_generic_onellm_error_is_warn(self):
        exc = OneLLMError("generic")
        assert init_mod._classify_probe_failure(exc) == "warn"


class TestFatalMessageFormatting:
    """The operator-facing message picks a hint based on slug shape."""

    def test_local_bare_name_surfaces_owner_hint(self):
        # The dev's exact case.
        exc = InvalidRequestError("HFValidationError", provider="local", status_code=400)
        msg = init_mod._format_probe_fatal_message("local/all-MiniLM-L6-v2", exc)

        assert "local/all-MiniLM-L6-v2" in msg
        assert "missing the owner/organization" in msg
        assert "local/<owner>/<repo>" in msg
        assert "local/sentence-transformers/all-MiniLM-L6-v2" in msg
        assert type(exc).__name__ in msg

    def test_local_owner_repo_surfaces_typo_or_gated_hint(self):
        exc = ResourceNotFoundError("404", provider="local", status_code=404)
        msg = init_mod._format_probe_fatal_message("local/nonexistent-org/whatever", exc)

        assert "Common causes for local/* slugs" in msg
        assert "Gated repo" in msg
        # Must NOT show the bare-name hint for a slug that already has owner/repo.
        assert "missing the owner/organization" not in msg

    def test_cloud_slug_shows_cloud_hint_only(self):
        exc = ResourceNotFoundError("404", provider="openai", status_code=404)
        msg = init_mod._format_probe_fatal_message("openai/gpt-4o-min", exc)

        assert "Common causes for cloud slugs" in msg
        assert "Typo in the model name" in msg
        # Local-specific hints must not appear for cloud slugs.
        assert "local/<owner>/<repo>" not in msg
        assert "HuggingFace repo id" not in msg


class TestProbeBuilder:
    """``_build_unique_probes`` controls dedup and probe-kind selection."""

    def test_embedding_capability_uses_embedding_probe_kind(self):
        probes = init_mod._build_unique_probes(
            {"embedding": {"model": "local/sentence-transformers/all-MiniLM-L6-v2"}}
        )
        assert len(probes) == 1
        assert probes[0]["kind"] == "embedding"

    def test_text_capability_uses_chat_probe_kind(self):
        probes = init_mod._build_unique_probes({"text": {"model": "openai/gpt-4o-mini"}})
        assert len(probes) == 1
        assert probes[0]["kind"] == "chat"

    def test_two_capabilities_same_chat_slug_dedup_to_one_probe(self):
        # vision falling back to text is the canonical case.
        probes = init_mod._build_unique_probes(
            {
                "text": {"model": "openai/gpt-4o-mini"},
                "vision": {"model": "openai/gpt-4o-mini"},
            }
        )
        assert len(probes) == 1
        assert set(probes[0]["capabilities"]) == {"text", "vision"}

    def test_same_slug_used_as_chat_and_embedding_runs_two_probes(self):
        # Edge case: same slug declared as both - we want both probed
        # because the OneLLM transport differs.
        probes = init_mod._build_unique_probes(
            {
                "text": {"model": "openai/text-embedding-3-small"},
                "embedding": {"model": "openai/text-embedding-3-small"},
            }
        )
        assert len(probes) == 2
        kinds = {p["kind"] for p in probes}
        assert kinds == {"chat", "embedding"}

    def test_empty_or_missing_model_is_skipped(self):
        probes = init_mod._build_unique_probes(
            {
                "text": {"model": "openai/gpt-4o-mini"},
                "ghost": {"model": ""},
                "phantom": {"model": None},
                "weird": {},  # no "model" key
            }
        )
        assert len(probes) == 1
        assert probes[0]["model"] == "openai/gpt-4o-mini"


class TestProbeOutcomes:
    """End-to-end probe behavior with the OneLLM call mocked."""

    @pytest.mark.asyncio
    async def test_all_probes_succeed_no_raise(self):
        formation = _make_formation({"text": {"model": "openai/gpt-4o-mini"}})
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock()) as mock_exec:
            await init_mod.probe_declared_models(formation)
        mock_exec.assert_awaited_once_with("openai/gpt-4o-mini", "chat")

    @pytest.mark.asyncio
    async def test_resource_not_found_aborts_with_config_error(self):
        formation = _make_formation({"text": {"model": "openai/gpt-4o-min"}})  # typo
        exc = ResourceNotFoundError("404", provider="openai", status_code=404)
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock(side_effect=exc)):
            with pytest.raises(ConfigurationValidationError) as excinfo:
                await init_mod.probe_declared_models(formation)

        # Message names the offending slug and embeds the OneLLM error.
        msg = str(excinfo.value)
        assert "openai/gpt-4o-min" in msg
        assert "ResourceNotFoundError" in msg

    @pytest.mark.asyncio
    async def test_bare_name_local_slug_surfaces_owner_hint(self):
        # The dev's exact failure - must produce the hint that names
        # the canonical form.
        formation = _make_formation({"embedding": {"model": "local/all-MiniLM-L6-v2"}})
        exc = InvalidRequestError(
            "[local/all-MiniLM-L6-v2] Invalid HuggingFace repo id.",
            provider="local",
            status_code=400,
        )
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock(side_effect=exc)):
            with pytest.raises(ConfigurationValidationError) as excinfo:
                await init_mod.probe_declared_models(formation)

        msg = str(excinfo.value)
        assert "local/all-MiniLM-L6-v2" in msg
        assert "local/sentence-transformers/all-MiniLM-L6-v2" in msg
        assert "owner/organization" in msg

    @pytest.mark.asyncio
    async def test_authentication_error_does_not_abort(self):
        formation = _make_formation({"text": {"model": "openai/gpt-4o-mini"}})
        exc = AuthenticationError("bad key", provider="openai", status_code=401)
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock(side_effect=exc)):
            # Must not raise - auth failures are warn-and-continue.
            await init_mod.probe_declared_models(formation)

    @pytest.mark.asyncio
    async def test_rate_limit_does_not_abort(self):
        formation = _make_formation({"text": {"model": "anthropic/claude-3-5-sonnet"}})
        exc = RateLimitError("429", provider="anthropic", status_code=429)
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock(side_effect=exc)):
            await init_mod.probe_declared_models(formation)

    @pytest.mark.asyncio
    async def test_non_onellm_exception_does_not_abort(self):
        # A bug in the probe machinery (RuntimeError, ValueError, ...)
        # must NOT brick formations - log loudly, continue.
        formation = _make_formation({"text": {"model": "openai/gpt-4o-mini"}})
        with patch.object(
            init_mod,
            "_execute_single_probe",
            new=AsyncMock(side_effect=RuntimeError("probe machinery bug")),
        ):
            await init_mod.probe_declared_models(formation)

    @pytest.mark.asyncio
    async def test_first_fatal_aborts_before_subsequent_probes_run(self):
        # text raises 404; embedding (a separate probe) MUST NOT be
        # called because we fail-fast on the first fatal.
        formation = _make_formation(
            {
                "text": {"model": "openai/gpt-4o-min"},  # typo, will 404
                "embedding": {"model": "openai/text-embedding-3-small"},
            }
        )

        call_log: list[tuple] = []

        async def fake_probe(model: str, kind: str) -> None:
            call_log.append((model, kind))
            if model == "openai/gpt-4o-min":
                raise ResourceNotFoundError("404", provider="openai", status_code=404)

        with patch.object(init_mod, "_execute_single_probe", new=fake_probe):
            with pytest.raises(ConfigurationValidationError):
                await init_mod.probe_declared_models(formation)

        assert call_log == [("openai/gpt-4o-min", "chat")]

    @pytest.mark.asyncio
    async def test_empty_capability_models_is_a_noop(self):
        formation = _make_formation({})
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock()) as mock_exec:
            await init_mod.probe_declared_models(formation)
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedup_runs_one_probe_for_two_capabilities(self):
        # vision cascading from text - both point at gpt-4o-mini, only
        # one probe should fire.
        formation = _make_formation(
            {
                "text": {"model": "openai/gpt-4o-mini"},
                "vision": {"model": "openai/gpt-4o-mini"},
            }
        )
        with patch.object(init_mod, "_execute_single_probe", new=AsyncMock()) as mock_exec:
            await init_mod.probe_declared_models(formation)
        assert mock_exec.await_count == 1
