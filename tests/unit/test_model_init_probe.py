"""Unit tests for the formation-init model probe.

The probe verifies that every model declared in ``formation._capability_models``
resolves through OneLLM at formation init time, so misspelled or
shape-invalid slugs (e.g. ``local/all-MiniLM-L6-v2`` instead of
``local/sentence-transformers/all-MiniLM-L6-v2``) abort startup
rather than degrading silently on first user request.

This file holds **pure-function** unit tests only. End-to-end probe
behavior (real OneLLM calls, real HF / OpenAI errors, real fatal
abort path) lives in
``tests/integration/test_model_init_probe_integration.py`` per the
project's "no mocks" testing standard - pure functions are safe
ground for fast unit assertions; behavior tests use real services.

Coverage:

- ``TestClassification``        - failure-class -> severity mapping
- ``TestEventLevelMapping``     - severity + origin -> EventLevel
- ``TestFatalMessageFormatting``- slug-shape -> hint in fatal message
- ``TestProbeBuilder``          - capability dedup + probe-kind picking
"""

from __future__ import annotations

from onellm.errors import (
    AuthenticationError,
    InvalidRequestError,
    OneLLMError,
    RateLimitError,
    ResourceNotFoundError,
)

from muxi.runtime.datatypes.observability import EventLevel
from muxi.runtime.formation import initialization as init_mod


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

    def test_audio_capability_uses_audio_probe_kind(self):
        # Regression: pre-fix this collapsed to "chat", which sent
        # ChatCompletion at openai/whisper-1 and 404'd as
        # "not a chat model" -> false-positive fatal abort across every
        # formation declaring an audio capability.
        probes = init_mod._build_unique_probes({"audio": {"model": "openai/whisper-1"}})
        assert len(probes) == 1
        assert probes[0]["kind"] == "audio"
        assert probes[0]["model"] == "openai/whisper-1"

    def test_audio_and_text_do_not_dedup_even_if_same_slug(self):
        # Hypothetical edge case: same slug declared as both audio and
        # text. Different transports => two probes, like the
        # chat+embedding case below.
        probes = init_mod._build_unique_probes(
            {
                "text": {"model": "openai/gpt-4o-audio-preview"},
                "audio": {"model": "openai/gpt-4o-audio-preview"},
            }
        )
        assert len(probes) == 2
        kinds = {p["kind"] for p in probes}
        assert kinds == {"chat", "audio"}

    def test_vision_and_video_default_to_chat_probe_kind(self):
        # Multimodal vision/video models (gpt-4o, gemini-2.0-flash) are
        # chat-compatible: a text-only "ping" round-trips fine. Lock
        # the default-to-chat fallback so future capability additions
        # don't silently break.
        probes = init_mod._build_unique_probes(
            {
                "vision": {"model": "openai/gpt-4o"},
                "video": {"model": "google/gemini-2.0-flash"},
            }
        )
        assert {p["kind"] for p in probes} == {"chat"}
        assert len(probes) == 2  # different slugs, distinct probes

    def test_text_fallback_audio_capability_is_skipped(self):
        # Regression: when a formation does NOT declare an audio model,
        # _initialize_llm_configuration fills in audio with the text
        # slug + ``_fallback_from_text=True``. The audio probe would
        # then send a Whisper request to a chat-only slug like
        # ``openai/gpt-4o-mini`` and 404 with "Invalid URL
        # /v1/audio/transcriptions" - bricking every formation that
        # falls back. The fallback skip eliminates the redundant probe
        # (text already validates the slug).
        probes = init_mod._build_unique_probes(
            {
                "text": {"model": "openai/gpt-4o-mini"},
                "audio": {
                    "model": "openai/gpt-4o-mini",
                    "_fallback_from_text": True,
                },
                "vision": {
                    "model": "openai/gpt-4o-mini",
                    "_fallback_from_text": True,
                },
            }
        )
        # Only the text probe survives; fallback entries are skipped.
        assert len(probes) == 1
        assert probes[0]["model"] == "openai/gpt-4o-mini"
        assert probes[0]["kind"] == "chat"
        assert probes[0]["capabilities"] == ["text"]

    def test_explicit_audio_capability_is_probed_even_if_same_slug_as_text(self):
        # A formation that legitimately declares an audio model
        # (e.g. openai/whisper-1) MUST still get the audio probe -
        # explicitness signals "this slug is meant for audio".
        # Absent _fallback_from_text => probe normally.
        probes = init_mod._build_unique_probes(
            {
                "text": {"model": "openai/gpt-4o-mini"},
                "audio": {"model": "openai/whisper-1"},  # explicit
            }
        )
        assert len(probes) == 2
        kinds = {(p["model"], p["kind"]) for p in probes}
        assert kinds == {
            ("openai/gpt-4o-mini", "chat"),
            ("openai/whisper-1", "audio"),
        }

    def test_audio_probe_payload_is_valid_wav(self):
        # The probe sends real bytes to OneLLM's AudioTranscription
        # endpoint; if the WAV is malformed the probe falsely reports
        # the slug as broken. Lock the format so a future refactor
        # can't silently produce truncated or non-WAV bytes.
        import io
        import wave

        payload = init_mod._PROBE_AUDIO_WAV
        assert payload[:4] == b"RIFF"
        assert payload[8:12] == b"WAVE"

        with wave.open(io.BytesIO(payload), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2  # 16-bit
            assert w.getframerate() == 8000
            # Whisper minimum is 0.1s; we send 0.2s for clock-skew margin.
            assert w.getnframes() / w.getframerate() >= 0.15

    def test_capability_probe_kind_helper_is_pure(self):
        # Direct contract on the dispatch helper - keeps future additions
        # honest without spinning up _build_unique_probes.
        assert init_mod._capability_probe_kind("embedding") == "embedding"
        assert init_mod._capability_probe_kind("audio") == "audio"
        assert init_mod._capability_probe_kind("text") == "chat"
        assert init_mod._capability_probe_kind("streaming") == "chat"
        assert init_mod._capability_probe_kind("vision") == "chat"
        assert init_mod._capability_probe_kind("video") == "chat"
        assert init_mod._capability_probe_kind("documents") == "chat"
        # Unknown capabilities default to chat - the runtime invokes
        # them via ChatCompletion until proven otherwise.
        assert init_mod._capability_probe_kind("future-capability") == "chat"

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


class TestEventLevelMapping:
    """``_event_level_for_failure`` is pure - lock the level contract.

    The block-comment in ``initialization.py`` promises ERROR-level
    events for non-``OneLLMError`` exceptions (probe-machinery bugs).
    Without these tests an operator filtering ERROR alerts would
    silently miss a defect in the probe layer itself, since the
    control-flow severity is "warn" (continue) but the operational
    severity is ERROR (something is broken).
    """

    def test_fatal_onellm_emits_error(self):
        # 404 / shape error from OneLLM - operator's primary signal.
        assert init_mod._event_level_for_failure("fatal", is_onellm=True) == EventLevel.ERROR

    def test_warn_onellm_emits_warning(self):
        # auth / rate-limit / transient OneLLM error - non-fatal,
        # informational only.
        assert init_mod._event_level_for_failure("warn", is_onellm=True) == EventLevel.WARNING

    def test_warn_non_onellm_emits_error(self):
        # The reviewer's flagged case: a probe-machinery bug
        # (RuntimeError, ValueError, etc.) is non-fatal at the
        # control-flow level but MUST emit at ERROR so log filtering
        # doesn't hide it.
        assert init_mod._event_level_for_failure("warn", is_onellm=False) == EventLevel.ERROR

    def test_fatal_non_onellm_emits_error(self):
        # Defensive: the classifier never produces "fatal" for a
        # non-OneLLMError today, but if it ever did we still want
        # ERROR (loudest signal wins).
        assert init_mod._event_level_for_failure("fatal", is_onellm=False) == EventLevel.ERROR

    def test_unrecognized_severity_treated_as_non_fatal(self):
        # Future-proofing: an unknown severity string from a
        # classifier extension should NOT silently emit ERROR.
        # Falls into the "warn" branch via the inverted condition.
        assert (
            init_mod._event_level_for_failure("future-severity", is_onellm=True)
            == EventLevel.WARNING
        )
