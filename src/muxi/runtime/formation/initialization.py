"""
Formation initialization utilities.

This module contains all the initialization logic for the Formation class,
handling all infrastructure and service setup. This ensures proper separation
of concerns where Formation handles operations and Overlord handles intelligence.

The initialization order is critical:
1. Observability MUST be initialized first
2. Then other services can be initialized
"""

import io
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..datatypes.clarification import ClarificationConfig, QuestionStyle
from ..datatypes.exceptions import ConfigurationValidationError
from ..datatypes.memory import BufferMemoryConfig, WorkingMemoryConfig
from ..datatypes.observability import EventLevel, InitEventFormatter
from ..services import observability
from ..services.memory.working import WorkingMemory
from ..services.observability.context import set_event_logger
from ..services.observability.logger import EventLogger
from .config.document_processing import DocumentProcessingConfig
from .documents.storage.chunk_manager import DocumentChunkManager

# Configuration limits
MAX_CLARIFICATION_ROUNDS = 32  # Maximum rounds allowed for any clarification mode


def _resolve_embedding_model_name(
    explicit_model: Optional[str] = None, formation: Any = None
) -> Optional[str]:
    """
    Resolve the embedding model name from configuration.

    Args:
        explicit_model: Explicitly configured embedding model name
        formation: Formation instance to check for capability models

    Returns:
        The resolved embedding model name or None if not configured
    """
    # First check if an explicit model is provided
    if explicit_model:
        return explicit_model

    # Otherwise, check formation capability models
    if formation and hasattr(formation, "_capability_models"):
        embedding_config = formation._capability_models.get("embedding", {})
        if isinstance(embedding_config, dict):
            model_name = embedding_config.get("model")
            return model_name if isinstance(model_name, str) else None

    return None


def initialize_observability(formation) -> None:
    """
    Initialize observability/logging configuration FIRST.

    This MUST be the first initialization to ensure all subsequent
    events go to the configured destination instead of stdout.

    Two-tier logging architecture:
    - system: Infrastructure events (SystemEvents, ErrorEvents, ServerEvents, APIEvents)
    - conversation: User-facing events (ConversationEvents) - enabled AFTER server starts

    Note: Conversation logging (JSONL) is deferred until after the server starts
    to avoid issues with file logging during initialization.
    """
    # Use the pre-configured logging config
    logging_config = formation._logging_config if hasattr(formation, "_logging_config") else {}

    # Parse system logging config (defaults: level=debug, destination=stdout)
    system_config = logging_config.get("system", {})
    system_level_str = system_config.get("level", "debug").lower()
    system_destination = system_config.get("destination", "stdout")

    # Store conversation config for later enablement (after server starts)
    conversation_config = logging_config.get("conversation", {})
    formation._conversation_logging_config = conversation_config
    formation._system_logging_config = {
        "level": system_level_str,
        "destination": system_destination,
    }

    # Initially, only set up system logging (conversation logging enabled after server starts)
    default_logger = EventLogger(
        system_level=system_level_str,
        system_destination=system_destination,
    )
    formation._observability_manager = observability.ObservabilityManager(
        {"event_logger": default_logger}
    )
    set_event_logger(default_logger)


def enable_conversation_logging(formation) -> None:
    """
    Enable conversation logging after server has started.

    This is called by the server after successful startup to:
    1. Enable JSONL conversation logging to configured destinations
    2. Mark the server as ready (enables system event JSONL to stdout)

    Logging is deferred to avoid cluttering console during initialization
    and to ensure the server is healthy before starting observability.
    """
    # First, mark server as ready so system events start flowing
    from ..services.observability.context import get_current_event_logger

    current_logger = get_current_event_logger()
    if current_logger and hasattr(current_logger, "set_server_ready"):
        current_logger.set_server_ready(True)

    conversation_config = getattr(formation, "_conversation_logging_config", {})
    system_config = getattr(formation, "_system_logging_config", {})

    conversation_enabled = conversation_config.get("enabled", False)
    conversation_streams = conversation_config.get("streams", [])

    if not conversation_enabled:
        return

    system_level_str = system_config.get("level", "debug")
    system_destination = system_config.get("destination", "stdout")

    # Find file stream configuration for conversation events
    for stream in conversation_streams:
        if stream.get("transport") == "file" and stream.get("destination"):
            # Parse level
            level_str = stream.get("level", "info").lower()
            valid_levels = [level.value for level in EventLevel]
            level = EventLevel(level_str) if level_str in valid_levels else EventLevel.INFO

            # Create EventLogger with file output and system config
            event_logger = EventLogger(
                level=level,
                output="file",
                output_config={"path": stream.get("destination")},
                events=(stream.get("events", ["*"]) if stream.get("events") != ["*"] else None),
                system_level=system_level_str,
                system_destination=system_destination,
            )
            # Mark as server ready since we're enabling after server start
            event_logger.set_server_ready(True)

            # Update ObservabilityManager with new logger
            formation._observability_manager = observability.ObservabilityManager(
                {"enabled": True, "event_logger": event_logger}
            )
            # CRITICAL: Set the logger in context so observe() uses it
            set_event_logger(event_logger)

            print(
                observability.InitEventFormatter.format_info(
                    f"Conversation logging enabled: {event_logger.output_config.get('path')}"
                )
            )
            break


def initialize_llm_config(formation) -> None:
    """
    Initialize LLM configuration from formation config.

    This processes the capability-based LLM schema and sets up model
    resolution for different capabilities like text, vision, transcription, etc.

    Requirements:
    - The 'text' capability MUST be configured (no fallback)
    - Other capabilities default to the text model if not configured

    Raises:
        ConfigurationValidationError: If the 'text' capability is not configured
    """
    llm_config = formation._llm_config if hasattr(formation, "_llm_config") else {}

    # Initialize OneLLM cache if configured
    # Import here to avoid circular dependency
    from ..services.llm.llm import initialize_onellm_cache

    settings = llm_config.get("settings", {})
    cache_config = settings.get("caching", {})
    initialize_onellm_cache(cache_config)

    # Initialize model cache for capability-based resolution
    formation._model_cache = {}
    formation._capability_models = {}

    # Process models by capability
    models_config = llm_config.get("models", [])
    for model_config in models_config:
        for capability, model_name in model_config.items():
            if capability in ["api_key", "settings"]:
                continue  # Skip metadata

            formation._capability_models[capability] = {
                "model": model_name,
                "api_key": model_config.get("api_key"),
                "settings": model_config.get("settings", {}),
            }

    # Store global settings and api_keys for later use
    formation._global_llm_settings = llm_config.get("settings", {})
    formation._global_api_keys = llm_config.get("api_keys", {})

    # Register API keys globally with OneLLM so all providers (embeddings, chat, etc.)
    # can authenticate without needing explicit api_key on every LLM() instantiation
    if formation._global_api_keys:
        from onellm.config import set_api_key as _onellm_set_api_key

        for provider, api_key in formation._global_api_keys.items():
            if api_key and "${{ secrets." not in str(api_key):
                _onellm_set_api_key(api_key, provider)

    # CRITICAL: Ensure text model is configured
    if "text" not in formation._capability_models:
        raise ConfigurationValidationError(
            ["Missing required LLM capability 'text' in formation.llm.models"],
            details={
                "required_capability": "text",
                "configured_capabilities": list(formation._capability_models.keys()),
                "help": "You must configure at least: llm.models[0].text = 'provider/model-name'",
            },
        )

    # Get text model configuration for fallback
    text_model_config = formation._capability_models["text"]

    # Define common capabilities that should default to text model if not configured.
    # Note: "embedding" is intentionally excluded -- buffer/working memory always
    # uses local sentence-transformer embeddings.  The formation-level embedding
    # capability is only used for document/knowledge uploads and must be explicitly
    # configured if an external embedding model is desired.
    common_capabilities = ["vision", "audio", "documents", "streaming"]
    capabilities_using_text_fallback = []

    # Apply text model as default for unconfigured common capabilities.
    # The ``_fallback_from_text`` flag is read by the model-init probe
    # (:func:`_build_unique_probes`) so it can skip probing a fallback
    # capability through its own transport. Without this flag, an audio
    # capability falling back to a text/chat slug like ``openai/gpt-4o-mini``
    # would be probed via ``AudioTranscription``, which 404s because the
    # chat model has no audio endpoint - bricking every formation that
    # doesn't explicitly declare an audio model.
    for capability in common_capabilities:
        if capability not in formation._capability_models:
            formation._capability_models[capability] = {
                "model": text_model_config["model"],
                "api_key": text_model_config.get("api_key"),
                "settings": text_model_config.get("settings", {}),
                "_fallback_from_text": True,
            }
            capabilities_using_text_fallback.append(capability)

    # Configure streaming service with LLM configuration
    from ..services.streaming import set_streaming_llm_config

    streaming_config = formation._capability_models.get("streaming", text_model_config)

    # Check if streaming model was explicitly configured
    # If yes, enable rephrasing by default
    streaming_explicitly_configured = "streaming" not in capabilities_using_text_fallback
    enable_rephrasing = streaming_explicitly_configured

    # Allow override from streaming settings
    if streaming_config.get("settings", {}).get("enable_rephrasing") is not None:
        enable_rephrasing = streaming_config["settings"]["enable_rephrasing"]

    # Get overlord response configuration for progress setting
    overlord_config = formation.config.get("overlord", {})
    response_config = overlord_config.get("response", {})
    enable_progress = response_config.get("progress", True)  # Default to True

    set_streaming_llm_config(
        {
            "model": streaming_config["model"],
            "api_key": streaming_config.get("api_key"),
            "settings": streaming_config.get("settings", {}),
            "enabled": enable_rephrasing,
            "progress": enable_progress,  # Pass progress setting to streaming service
        }
    )

    capabilities = list(formation._capability_models.keys())

    # Log initialization with details about fallbacks
    log_data = {
        "service": "llm",
        "capabilities": capabilities,
        "capability_count": len(capabilities),
        "text_model": text_model_config["model"],
    }

    if capabilities_using_text_fallback:
        log_data["capabilities_using_text_fallback"] = capabilities_using_text_fallback

    # Note: description variable removed as observability call was removed


# ---------------------------------------------------------------------------
# Model init probe
#
# Verifies every formation-declared model resolves through OneLLM at
# formation init time. Catches the otherwise-silent failure mode where
# a misspelled or shape-invalid slug (e.g. ``local/all-MiniLM-L6-v2``
# instead of ``local/sentence-transformers/all-MiniLM-L6-v2``) only
# manifests as ``InvalidConfigurationError`` on first user request and
# silently degrades the relevant capability (semantic memory, vision,
# etc.) for the lifetime of the formation.
#
# Failure classification:
#   - ResourceNotFoundError, InvalidRequestError       -> FATAL (raise)
#   - AuthenticationError, RateLimitError,             -> WARN (continue)
#     ServiceUnavailableError, RequestTimeoutError,
#     other OneLLMError subclasses
#   - non-OneLLMError exceptions                       -> WARN (continue)
#                                                          + ERROR-level log
#                                                         (probe-machinery
#                                                          bug, not user
#                                                          error)
#
# Probes run **synchronously, serially**: load-order semantics are
# preserved and the first fatal failure aborts before subsequent probes.
# ---------------------------------------------------------------------------


def _classify_probe_failure(exc: Exception) -> str:
    """Return ``"fatal"`` or ``"warn"`` for a probe exception.

    Pure function, no side effects, kept module-level so unit tests can
    exercise the classification without spinning up a formation.

    The two fatal classes are deterministic "this slug will never
    resolve" failures:

    - :class:`onellm.errors.ResourceNotFoundError` - HF 404 or provider
      model-not-found.
    - :class:`onellm.errors.InvalidRequestError` - HF validation error,
      which is what bare-name local slugs (the dev's case) surface as.

    Everything else (auth, rate limit, network, unknown) is classified
    ``"warn"`` so a transient or environmental issue at init does not
    brick a formation that would otherwise come up healthy.
    """
    from onellm.errors import (
        InvalidRequestError,
        ResourceNotFoundError,
    )

    if isinstance(exc, (ResourceNotFoundError, InvalidRequestError)):
        return "fatal"
    return "warn"


def _event_level_for_failure(severity: str, is_onellm: bool) -> "EventLevel":
    """Pure mapper: failure classification + origin -> emitted event level.

    Two cases produce ``ERROR``:

    - ``severity == "fatal"`` - formation is about to abort init; the
      event is the operator's primary signal, must surface above
      ``WARNING`` filtering thresholds.
    - ``not is_onellm`` - a probe-machinery bug (``RuntimeError``,
      ``ValueError``, etc.). The control-flow severity is ``"warn"``
      (we continue formation init to avoid bricking on a probe defect),
      but the event level is ``ERROR`` so an operator filtering on
      ERROR alerts does not silently miss a defect in the probe layer
      itself. The block-comment contract on this module promises
      ``ERROR`` for non-``OneLLMError`` cases; this helper makes that
      promise enforceable in tests.

    All other cases (``severity == "warn"`` from a real ``OneLLMError`` -
    auth, rate limit, transient network) emit at ``WARNING``.
    """
    if severity == "fatal" or not is_onellm:
        return EventLevel.ERROR
    return EventLevel.WARNING


def _format_probe_fatal_message(model_slug: str, exc: Exception) -> str:
    """Build the operator-facing message for a fatal probe failure.

    The hint section is dynamic:

    - For ``local/<bare-name>`` slugs (the dev's exact case) we surface
      the bare-name -> owner/repo correction prominently.
    - For other ``local/...`` slugs we still mention the
      ``local/<owner>/<repo>`` shape requirement.
    - For non-local slugs (cloud providers) the typo hint is emphasized
      and the local hint is omitted entirely so the message stays
      relevant.
    """
    base = (
        f"Formation init failed: model '{model_slug}' could not be "
        f"resolved by OneLLM.\n\n"
        f"OneLLM reported:\n  {type(exc).__name__}: {exc}\n\n"
    )

    if model_slug.startswith("local/"):
        post = model_slug[len("local/") :]
        bare_name_likely = "/" not in post
        if bare_name_likely:
            return base + (
                "Cause: the local slug is missing the owner/organization "
                "segment. The runtime requires the full HuggingFace repo "
                "id:\n"
                "    local/<owner>/<repo>   "
                "(e.g. local/sentence-transformers/all-MiniLM-L6-v2)\n"
                f"NOT local/<repo>          "
                f"(e.g. {model_slug})\n\n"
                "Fix the formation's model declaration and restart.\n"
            )
        return base + (
            "Common causes for local/* slugs:\n"
            "  - Model genuinely missing from HuggingFace (typo in owner/repo).\n"
            "  - Gated repo without a read token configured.\n\n"
            "Fix the formation's model declaration and restart.\n"
        )

    return base + (
        "Common causes for cloud slugs:\n"
        "  - Typo in the model name (e.g. 'openai/gpt-4o-min' vs "
        "'openai/gpt-4o-mini').\n"
        "  - Model deprecated or genuinely missing from the provider.\n\n"
        "Fix the formation's model declaration and restart.\n"
    )


# Capability -> probe-kind mapping. Each kind selects a different OneLLM
# transport in ``_execute_single_probe``. Keep this aligned with how the
# runtime actually uses each capability at request time:
#
# - ``embedding``  -> ``onellm.Embedding`` (services/memory/embedding.py)
# - ``audio``      -> ``onellm.AudioTranscription`` (services/llm/llm.py)
# - everything     -> ``onellm.ChatCompletion`` (the default text/chat
#   else              transport that text/streaming/vision/video/
#                    documents all flow through)
#
# Probing audio via ``ChatCompletion`` (the previous behavior) sends a
# chat round-trip to a non-chat slug like ``openai/whisper-1`` and gets
# back a 404 ``"This is not a chat model"``, which then misclassifies as
# a fatal slug error and aborts every formation that declares an audio
# capability. The kind table below routes each capability to the
# transport it would actually use at runtime.
_CAPABILITY_PROBE_KIND: Dict[str, str] = {
    "embedding": "embedding",
    "audio": "audio",
}


def _capability_probe_kind(capability: str) -> str:
    """Return the probe ``kind`` for a given capability name.

    Defaults to ``"chat"`` so any capability not explicitly mapped
    (text, streaming, vision, video, documents, future additions) gets
    the ``ChatCompletion`` transport - matching how those capabilities
    are invoked at runtime.
    """
    return _CAPABILITY_PROBE_KIND.get(capability, "chat")


def _build_audio_probe_payload() -> bytes:
    """Build a minimal valid WAV payload for the audio probe.

    OpenAI's Whisper endpoint rejects audio shorter than 0.1s with an
    ``InvalidRequestError`` (which the probe classifies as fatal), so we
    generate ~0.2s of mono 16-bit PCM silence at 8 kHz - the smallest
    payload that round-trips reliably. Format details:

    - ``8000 Hz`` sample rate (lowest standard rate)
    - ``1`` channel (mono)
    - ``16-bit`` signed PCM samples (required by WAV PCM)
    - ``0.2 s`` duration (2x the documented minimum, well within the
      provider's tolerance for clock-skew at the lower bound)

    Total size: ``44`` byte WAV header + ``8000 * 0.2 * 2`` =
    ``3244`` bytes. Computed once at import time.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * 0.2))
    return buf.getvalue()


# Computed once at import time so every probe reuses the same bytes -
# trivially cheap (~3 KB constant) and avoids per-probe encoding cost.
_PROBE_AUDIO_WAV: bytes = _build_audio_probe_payload()


def _build_unique_probes(
    capability_models: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Deduplicate ``capability_models`` into a list of unique probes.

    Two capabilities pointing at the same ``(model_slug, probe_kind)``
    pair are collapsed into a single probe; the ``capabilities`` field
    on the resulting probe lists every capability that mapped to it so
    observability events stay informative.

    ``probe_kind`` is selected by :func:`_capability_probe_kind`, which
    routes each capability to the OneLLM transport it actually uses at
    runtime (``embedding`` -> ``Embedding``, ``audio`` ->
    ``AudioTranscription``, everything else -> ``ChatCompletion``). The
    same slug declared as both an embedding model and a chat model
    (rare, but possible) is therefore probed twice with the correct
    transport for each role.

    Returns the probes in a stable order keyed on the first capability
    that introduced each unique probe, so error messages and tests are
    deterministic.
    """
    seen: Dict[tuple, Dict[str, Any]] = {}
    order: List[tuple] = []

    for capability, cfg in capability_models.items():
        model = cfg.get("model")
        if not isinstance(model, str) or not model:
            continue
        # Skip capabilities filled in by the text-fallback cascade. The
        # ``text`` probe already validates the underlying slug, and
        # probing a chat slug through a non-chat transport (audio's
        # ``AudioTranscription``, etc.) would 404 even though the
        # formation is healthy at runtime via the fallback chain.
        if cfg.get("_fallback_from_text"):
            continue
        kind = _capability_probe_kind(capability)
        key = (model, kind)
        if key not in seen:
            seen[key] = {
                "model": model,
                "kind": kind,
                "capabilities": [capability],
            }
            order.append(key)
        else:
            seen[key]["capabilities"].append(capability)

    return [seen[key] for key in order]


async def _execute_single_probe(model: str, kind: str) -> None:
    """Issue the actual OneLLM call for a single probe.

    Encapsulates the per-``kind`` transport split (Embedding vs
    AudioTranscription vs ChatCompletion) so :func:`probe_declared_models`
    stays focused on the per-probe lifecycle (event emission, error
    classification, serial fail-fast) and adding a new probe kind in
    the future is a one-function change confined to this helper.

    Behavior contract:

    - Returns ``None`` on success (the response payload is irrelevant
      to the probe; only the round-trip succeeded).
    - Raises the underlying ``OneLLMError`` (or any other exception)
      untouched so the caller can classify and emit the appropriate
      event. Wrapping or swallowing here would defeat the
      classification helper.
    """
    if kind == "embedding":
        from onellm import Embedding

        # Honor ``local/<repo>:<revision>`` slug notation by splitting
        # the revision off and forwarding it as a separate ``revision=``
        # kwarg, matching the runtime's actual embedding entry point
        # (services/memory/embedding.py::embed). Without this, a slug
        # like ``local/nomic-ai/nomic-embed-text-v1.5:main`` is sent to
        # OneLLM verbatim and rejected as an invalid HF repo id.
        from ..services.memory.embedding import _parse_model_slug

        parsed_model, revision = _parse_model_slug(model)
        kwargs: Dict[str, Any] = {"input": "probe", "model": parsed_model}
        if revision is not None:
            kwargs["revision"] = revision
        await Embedding.acreate(**kwargs)
    elif kind == "audio":
        # Audio capability slugs (e.g. ``openai/whisper-1``) are
        # transcription models, not chat models. Probe them through the
        # same OneLLM transport the runtime uses at request time
        # (services/llm/llm.py -> AudioTranscription.create) so we
        # surface real slug-resolution failures and don't false-positive
        # on "this is not a chat model" 404s.
        from onellm.audio import AudioTranscription

        await AudioTranscription.create(file=_PROBE_AUDIO_WAV, model=model)
    else:
        from onellm import ChatCompletion

        await ChatCompletion.acreate(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )


async def probe_declared_models(formation) -> None:
    """Probe every formation-declared model and fail-fast on 404.

    Iterates ``formation._capability_models`` after the text-fallback
    cascade has run, issues a minimal OneLLM call per unique
    ``(model_slug, probe_kind)`` pair, and converts deterministic
    "this slug will never resolve" failures into a
    :class:`ConfigurationValidationError` that aborts formation init.

    Probes are serial: the first fatal failure aborts before later
    probes run. Non-fatal failures (auth / network / rate-limit /
    other ``OneLLMError`` subclasses / probe-machinery bugs) emit a
    ``MODEL_INIT_PROBE_FAILED`` warning event and continue, so a
    transient init blip does not brick an otherwise-healthy formation.

    Raises:
        ConfigurationValidationError: when any probe surfaces a fatal
            error (``ResourceNotFoundError`` or ``InvalidRequestError``).
            The message names the offending slug, embeds the underlying
            OneLLM error verbatim, and surfaces operator-actionable
            guidance for the most common causes.
    """
    import time

    from onellm.errors import OneLLMError

    capability_models = getattr(formation, "_capability_models", {}) or {}
    probes = _build_unique_probes(capability_models)

    if not probes:
        return

    for probe in probes:
        model = probe["model"]
        kind = probe["kind"]
        capabilities = probe["capabilities"]

        observability.observe(
            event_type=observability.SystemEvents.MODEL_INIT_PROBE_STARTED,
            level=EventLevel.INFO,
            data={
                "model": model,
                "probe_kind": kind,
                "capabilities": capabilities,
            },
            description=(f"Probing model '{model}' ({kind}) for capabilities " f"{capabilities}"),
        )

        start = time.perf_counter()
        try:
            await _execute_single_probe(model, kind)
        except Exception as exc:  # noqa: BLE001 - intentional broad catch
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            is_onellm = isinstance(exc, OneLLMError)
            severity = _classify_probe_failure(exc) if is_onellm else "warn"

            observability.observe(
                event_type=observability.SystemEvents.MODEL_INIT_PROBE_FAILED,
                level=_event_level_for_failure(severity, is_onellm),
                data={
                    "model": model,
                    "probe_kind": kind,
                    "capabilities": capabilities,
                    "severity": severity,
                    "exception_type": type(exc).__name__,
                    "is_onellm_error": is_onellm,
                    "duration_ms": elapsed_ms,
                    "error": str(exc),
                },
                description=(
                    f"Model probe failed: {model} ({kind}) -> " f"{type(exc).__name__}: {exc}"
                ),
            )

            if severity == "fatal":
                raise ConfigurationValidationError(
                    [_format_probe_fatal_message(model, exc)],
                    details={
                        "model": model,
                        "probe_kind": kind,
                        "capabilities": capabilities,
                        "exception_type": type(exc).__name__,
                        "underlying_error": str(exc),
                    },
                ) from exc
            # Non-fatal: continue to next probe.
            continue

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        observability.observe(
            event_type=observability.SystemEvents.MODEL_INIT_PROBE_COMPLETED,
            level=EventLevel.INFO,
            data={
                "model": model,
                "probe_kind": kind,
                "capabilities": capabilities,
                "duration_ms": elapsed_ms,
            },
            description=(f"Model probe OK: {model} ({kind}) in {elapsed_ms}ms"),
        )


def initialize_memory_systems(formation) -> None:
    """
    Initialize all memory systems including buffer, working, and persistent memory.
    Creates all database tables after persistent memory is initialized.
    """
    memory_config = formation._memory_config if hasattr(formation, "_memory_config") else {}

    # Initialize working memory configuration
    working_config = memory_config.get("working", {})
    _initialize_working_memory(formation, working_config)

    # Initialize buffer memory
    buffer_config = memory_config.get("buffer", {})
    _initialize_buffer_memory(formation, buffer_config)

    # Initialize persistent memory
    # Default behavior: SQLite db file next to formation file
    # Disable with: persistent: false OR persistent: { enabled: false }
    persistent_config = memory_config.get("persistent")

    # Handle persistent: false (shorthand disable)
    if persistent_config is False:
        pass  # Explicitly disabled
    # Handle persistent: { enabled: false } (disabled but config preserved)
    elif isinstance(persistent_config, dict) and persistent_config.get("enabled") is False:
        pass  # Disabled via enabled flag
    else:
        # Ensure we have a dict to work with
        if not persistent_config or not isinstance(persistent_config, dict):
            persistent_config = {}

        # Default to SQLite in formation directory if no connection_string
        if not persistent_config.get("connection_string"):
            formation_path = formation.get_formation_path()
            if formation_path:
                from pathlib import Path

                fp = Path(formation_path)
                formation_dir = fp.parent if fp.is_file() else fp
                db_path = formation_dir / "memory.db"
                persistent_config["connection_string"] = str(db_path)

        # Initialize if we have a connection string
        if persistent_config.get("connection_string"):
            _initialize_persistent_memory(formation, persistent_config)

            # Create all database tables after persistent memory is initialized
            # This ensures all models are imported and registered with Base.metadata
            if hasattr(formation, "_db_manager") and formation._db_manager:
                # Pass embedding dimension so the correct memories_{dim} table is created
                ltm = getattr(formation, "_long_term_memory", None)
                embedding_dim = getattr(ltm, "dimension", 1536) if ltm else 1536
                _create_all_database_tables(formation._db_manager, embedding_dim)

                # Initialize the memory event substrate first: the knowledge
                # graph and captain's log dual-write through it, so it must
                # exist before they are constructed.
                _initialize_memory_events(formation, memory_config.get("events", {}) or {})

                # Initialize the knowledge graph service (Memory Revamp Phase 1).
                # Placed after table creation (kg_entities/kg_relationships must
                # exist) and after LLM configuration in the formation load order
                # so extraction can resolve the capability model at runtime.
                _initialize_knowledge_graph(formation, memory_config.get("graph", {}))

                # Initialize the captain's log service (Memory Revamp Phase 2).
                # Placed after the knowledge graph so the digest job can feed
                # extracted entities/relationships into it and register the
                # captains_log_sources DAG on the shared algorithms layer.
                _initialize_captains_log(formation, memory_config)

                # Register the projection builders with the substrate now
                # that every projection service exists. The registry is the
                # extension point for later projections (Knowledge Index).
                _register_memory_projectors(formation)


def _initialize_memory_events(formation, events_config: Dict[str, Any]) -> None:
    """Initialize the memory event substrate on top of persistent memory."""
    if events_config.get("enabled", True) is False:
        formation._memory_events = None
        return

    try:
        from ..services.memory.events import MemoryEventService

        formation_id = getattr(formation, "formation_id", "default-formation")
        formation._memory_events = MemoryEventService(
            db_manager=formation._db_manager,
            formation_id=formation_id,
            config=events_config,
        )
        print(
            InitEventFormatter.format_ok(
                "Initializing memory event substrate",
                f"grace period {formation._memory_events.grace_period_days}d",
            )
        )
    except Exception as e:
        formation._memory_events = None
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "memory_events"},
            description=f"Failed to initialize memory event substrate: {str(e)}",
        )
        # Don't raise - the event substrate is additive to persistent memory


def _register_memory_projectors(formation) -> None:
    """Register the built-in projection builders with the event substrate."""
    memory_events = getattr(formation, "_memory_events", None)
    if memory_events is None:
        return

    try:
        from ..services.memory.events import (
            CaptainsLogProjector,
            FlatFactProjector,
            KnowledgeGraphProjector,
        )

        if getattr(formation, "_knowledge_graph", None) is not None:
            memory_events.register_projector(KnowledgeGraphProjector(formation._knowledge_graph))
        if getattr(formation, "_captains_log", None) is not None:
            memory_events.register_projector(CaptainsLogProjector(formation._captains_log))
        if getattr(formation, "_long_term_memory", None) is not None:
            memory_events.register_projector(FlatFactProjector(formation._long_term_memory))
    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "memory_events"},
            description=f"Failed to register memory projectors: {str(e)}",
        )


def _initialize_knowledge_graph(formation, graph_config: Dict[str, Any]) -> None:
    """Initialize the knowledge graph service on top of persistent memory."""
    if graph_config.get("enabled", True) is False:
        formation._knowledge_graph = None
        return

    try:
        from ..services.memory.graph import KnowledgeGraphService

        formation_id = getattr(formation, "formation_id", "default-formation")
        formation._knowledge_graph = KnowledgeGraphService(
            db_manager=formation._db_manager,
            formation_id=formation_id,
            config=graph_config,
            event_log=getattr(formation, "_memory_events", None),
        )
        backend = "pgRouting" if formation._knowledge_graph.pgrouting_available else "NetworkX"
        print(InitEventFormatter.format_ok("Initializing knowledge graph", f"{backend} backend"))
    except Exception as e:
        formation._knowledge_graph = None
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "knowledge_graph"},
            description=f"Failed to initialize knowledge graph service: {str(e)}",
        )
        # Don't raise - the knowledge graph is additive to persistent memory


def _initialize_captains_log(formation, memory_config: Dict[str, Any]) -> None:
    """Initialize the captain's log service on top of persistent memory."""
    captains_log_config = memory_config.get("captains_log", {}) or {}
    if captains_log_config.get("enabled", True) is False:
        formation._captains_log = None
        return

    try:
        from ..services.memory.log import CaptainsLogService

        formation_id = getattr(formation, "formation_id", "default-formation")
        embedding_model = (memory_config.get("embedding", {}) or {}).get("model")
        formation._captains_log = CaptainsLogService(
            db_manager=formation._db_manager,
            formation_id=formation_id,
            config=captains_log_config,
            lessons_config=memory_config.get("lessons", {}) or {},
            knowledge_graph=getattr(formation, "_knowledge_graph", None),
            embedding_model=embedding_model,
            event_log=getattr(formation, "_memory_events", None),
        )
        lessons_status = "lessons on" if formation._captains_log.lessons_enabled else "lessons off"
        print(InitEventFormatter.format_ok("Initializing captain's log", lessons_status))
    except Exception as e:
        formation._captains_log = None
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "captains_log"},
            description=f"Failed to initialize captain's log service: {str(e)}",
        )
        # Don't raise - the captain's log is additive to persistent memory


def _initialize_working_memory(formation, working_config: Dict[str, Any]) -> None:
    """Initialize working memory configuration with defaults."""
    try:
        # Create WorkingMemoryConfig with provided config
        config = WorkingMemoryConfig(**working_config)

        # Store the working memory configuration
        formation._working_memory_config = config

        # Convert to InitEventFormatter
        print(observability.InitEventFormatter.format_ok(f"Working memory ({config.mode} mode)"))

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "working_memory"},
            description=f"Failed to initialize working memory: {str(e)}",
        )
        raise


def _initialize_buffer_memory(formation, buffer_config: Dict[str, Any]) -> None:
    """Initialize buffer memory from configuration with defaults."""
    try:
        # Create BufferMemoryConfig with provided config
        config = BufferMemoryConfig(**buffer_config)

        # Extract configuration values
        size = config.size
        multiplier = config.multiplier
        vector_search = config.vector_search
        mode = config.mode
        remote_config = config.remote

        # Buffer / working memory always uses local sentence-transformer
        # embeddings (all-MiniLM-L6-v2, 384 dims).  They are free, fast,
        # and require no API key.  The formation-level embedding model
        # (llm.models.embedding) is reserved for document/knowledge uploads
        # where higher quality matters.

        # Get formation_id from formation instance
        formation_id = getattr(formation, "formation_id", "default-formation")

        # Create buffer memory instance. Passing ``embedding_model=None``
        # defers to ``WorkingMemory``'s DEFAULT_EMBEDDING_MODEL — the
        # post-migration contract is a string slug, never an LLM-like
        # provider object. The legacy ``model=`` kwarg was removed in
        # the embedding-platform migration; ``embedding_model=`` is the
        # only accepted name and ``None`` is its default.
        formation._buffer_memory = WorkingMemory(
            formation_id=formation_id,
            max_size=size,
            buffer_multiplier=multiplier,
            embedding_model=None,
            mode=mode,
            remote=remote_config.model_dump() if remote_config and mode == "remote" else None,
        )

        # REMOVE - line 339 (redundant with InitEventFormatter)

        # Print clean formatted line
        search_status = "enabled" if vector_search else "disabled"
        details = f"{mode}, {size} messages, contextual search {search_status}"
        print(InitEventFormatter.format_ok("Initializing buffer memory", details))

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "buffer_memory"},
            description=f"Failed to initialize buffer memory: {str(e)}",
        )
        raise


def _validate_query_timeout(persistent_config: Dict[str, Any]) -> int:
    """
    Validate and extract query_timeout_seconds from persistent memory config.

    Args:
        persistent_config: Persistent memory configuration dict

    Returns:
        Validated positive integer timeout value

    Raises:
        ValueError: If timeout is invalid (non-integer, zero, or negative)
    """
    raw_timeout = persistent_config.get("query_timeout_seconds", 30)

    try:
        timeout = int(raw_timeout)
    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid query_timeout_seconds: {raw_timeout!r}. Must be a positive integer."
        )

    if timeout <= 0:
        raise ValueError(
            f"Invalid query_timeout_seconds: {timeout}. Must be a positive integer (got {timeout})."
        )

    return timeout


def _initialize_persistent_memory(formation, persistent_config: Dict[str, Any]) -> None:
    """
    Initializes the persistent memory system for the formation based on the provided configuration.

    Determines the memory backend (PostgreSQL, SQLite, or Memobase) from the
    connection string, checks for uninterpolated secrets, and passes the
    formation ID and embedding model name to the memory constructor.
    Stores the resulting memory instance and database manager (if available)
    on the formation. Emits observability events for both success and failure.
    Persistent memory initialization errors are logged but do not interrupt execution.
    """
    try:
        raw_connection_string = persistent_config.get("connection_string")
        if not isinstance(raw_connection_string, str) or not raw_connection_string:
            raise ValueError("Persistent memory connection_string must be a non-empty string")

        connection_string = raw_connection_string
        formation_id = getattr(formation, "formation_id", "default-formation")

        # Check if connection string still contains uninterpolated secrets
        # This should not happen as secrets are interpolated during formation loading
        if "${{ secrets." in connection_string:
            raise ValueError(
                f"Connection string contains uninterpolated secrets: {connection_string}. "
                "Secrets should be interpolated during formation loading."
            )

        # Get embedding model configuration
        explicit_embedding_model = persistent_config.get("embedding_model")
        embedding_model_name = _resolve_embedding_model_name(
            explicit_model=(
                explicit_embedding_model if isinstance(explicit_embedding_model, str) else None
            ),
            formation=formation,
        )

        # For now, we'll pass the model name and let the memory systems handle model creation
        # This avoids the async initialization issue

        # Extract and validate statement timeout once for reuse across all database manager branches
        statement_timeout = _validate_query_timeout(persistent_config)

        # Determine the type of persistent memory based on connection string
        if connection_string.startswith("postgresql://"):
            # PostgreSQL memory
            from ..services.db import get_database_manager
            from ..services.memory.long_term import LongTermMemory

            # Create database manager with configured timeout
            db_manager = get_database_manager(connection_string, statement_timeout)
            formation._db_manager = db_manager

            formation._long_term_memory = LongTermMemory(
                db_manager=db_manager,
                formation_id=formation_id,
                embedding_model=embedding_model_name,
            )
            formation._is_multi_user = True
            memory_type = "PostgreSQL"

        elif connection_string.endswith(".db") or "sqlite" in connection_string:
            # SQLite memory with database manager for credentials
            from ..services.db import get_database_manager
            from ..services.memory.sqlite import SQLiteMemory

            # Create database manager for SQLite (needed for credentials table)
            # Check if connection string already has sqlite:// prefix
            if connection_string.startswith("sqlite://"):
                db_connection_string = connection_string
            else:
                db_connection_string = f"sqlite:///{connection_string}"

            db_manager = get_database_manager(db_connection_string, statement_timeout)
            formation._db_manager = db_manager

            # Strip sqlite:/// prefix to get a raw file path for SQLiteMemory.
            # Users may write "sqlite:///./memory.db" (SQLAlchemy style) but
            # SQLiteMemory needs a plain file path like "./memory.db".
            db_file_path = connection_string
            if db_file_path.startswith("sqlite:///"):
                db_file_path = db_file_path[len("sqlite:///") :]
            elif db_file_path.startswith("sqlite://"):
                db_file_path = db_file_path[len("sqlite://") :]

            formation._long_term_memory = SQLiteMemory(
                db_path=db_file_path,
                formation_id=formation_id,
                embedding_model=embedding_model_name,
            )
            formation._is_multi_user = False  # SQLite is single-user mode
            memory_type = "SQLite"

        else:
            # Default to Memobase (wraps LongTermMemory for multi-user isolation)
            from ..services.db import get_database_manager
            from ..services.memory.long_term import LongTermMemory
            from ..services.memory.memobase import Memobase

            # Create database manager with configured timeout
            db_manager = get_database_manager(connection_string, statement_timeout)
            formation._db_manager = db_manager

            ltm = LongTermMemory(
                db_manager=db_manager,
                formation_id=formation_id,
                embedding_model=embedding_model_name,
            )
            formation._long_term_memory = Memobase(long_term_memory=ltm)
            formation._is_multi_user = True  # Memobase is multi-user mode
            memory_type = "Memobase"

        # REMOVE - line 456 (redundant with InitEventFormatter)

        # Print clean formatted line
        mode = "multi-user" if getattr(formation, "_is_multi_user", False) else "single-user"
        print(
            InitEventFormatter.format_ok(
                "Initializing persistent memory", f"{memory_type} / {mode} mode"
            )
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "persistent_memory"},
            description=f"Failed to initialize persistent memory: {str(e)}",
        )
        print(InitEventFormatter.format_fail("Persistent memory", f"{type(e).__name__}: {e}"))
        # Don't raise - persistent memory is optional


def _migrate_add_meta_data_column(db_manager, table_name: str) -> None:
    """Add meta_data column to memories table if it was created by an older schema version."""
    from sqlalchemy import text

    try:
        with db_manager.engine.connect() as conn:
            if db_manager.database_type == "postgresql":
                conn.execute(
                    text(
                        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS "
                        f"meta_data JSON NOT NULL DEFAULT '{{}}'"
                    )
                )
            else:
                # SQLite: check if column exists via PRAGMA, add if missing
                result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [row[1] for row in result]
                if "meta_data" not in columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN " f"meta_data TEXT DEFAULT '{{}}'"
                        )
                    )
            conn.commit()
    except Exception:
        pass  # Table may not exist yet on first run; create_tables handles it


def _migrate_add_derived_from_event_ids_column(db_manager, table_name: str) -> None:
    """Add the provenance column to projection tables from older schema versions."""
    from sqlalchemy import text

    try:
        with db_manager.engine.connect() as conn:
            if db_manager.database_type == "postgresql":
                conn.execute(
                    text(
                        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS "
                        f"derived_from_event_ids JSON NOT NULL DEFAULT '[]'"
                    )
                )
            else:
                # SQLite: check if column exists via PRAGMA, add if missing
                result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [row[1] for row in result]
                if "derived_from_event_ids" not in columns:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN "
                            f"derived_from_event_ids TEXT DEFAULT '[]'"
                        )
                    )
            conn.commit()
    except Exception:
        pass  # Table may not exist yet on first run; create_tables handles it


def _create_all_database_tables(db_manager, embedding_dimension: int = 1536) -> None:
    """
    Create all database tables for the MUXI runtime.

    This function imports all SQLAlchemy models to ensure they are registered
    with Base.metadata, then creates all tables in a single operation.

    Args:
        db_manager: The database manager instance with connection to database
        embedding_dimension: Vector dimension for the memories table (e.g. 384, 768, 1536)
    """
    try:
        # Import all models to ensure they are registered with Base.metadata
        # Memory models (users, memories_{dimension})
        # Credential models (credentials table) - Note: User is already imported above
        from ..formation.credentials.resolver import Credential  # noqa: F401

        # Get Base from db module
        from ..services.db import Base
        from ..services.memory.events.models import (  # noqa: F401
            MemoryEvent,
            ProjectionCheckpoint,
        )
        from ..services.memory.graph.models import KGEntity, KGRelationship  # noqa: F401
        from ..services.memory.log.models import (  # noqa: F401
            CaptainsLogEntry,
            CaptainsLogSource,
            Lesson,
        )
        from ..services.memory.long_term import (  # noqa: F401
            Group,
            User,
            UserGroup,
            ensure_memory_table_indexes,
            get_memory_model,
        )

        # Ensure the correct dimension-specific memory model is registered
        get_memory_model(embedding_dimension)

        # Scheduler models (scheduled_jobs, scheduled_job_audit)
        from ..services.scheduler.models import ScheduledJob, ScheduledJobAudit  # noqa: F401

        # On SQLite the dim-specific memories table is owned by SQLiteMemory,
        # which creates it lazily with its own raw-SQL schema (``metadata``
        # column, FTS mirror tables). Creating the SQLAlchemy variant here
        # first would win the CREATE TABLE IF NOT EXISTS race with a column
        # set (``meta_data``) that SQLiteMemory's queries don't use, breaking
        # flat-fact storage on fresh databases.
        tables = None
        if db_manager.database_type == "sqlite":
            tables = [
                table
                for name, table in Base.metadata.tables.items()
                if not name.startswith("memories_")
            ]

        # Create all tables using the database manager
        db_manager.create_tables(Base.metadata, tables=tables)

        # Migrate: ensure meta_data column exists on memories tables created by older versions
        # (CREATE TABLE IF NOT EXISTS won't add columns to existing tables)
        memories_table = f"memories_{embedding_dimension}"
        _migrate_add_meta_data_column(db_manager, memories_table)
        # Migrate: ensure the provenance column exists on projection tables
        # created before the memory event substrate shipped
        for projection_table in ("kg_entities", "kg_relationships", "captains_log", "lessons"):
            _migrate_add_derived_from_event_ids_column(db_manager, projection_table)
        ensure_memory_table_indexes(db_manager, embedding_dimension)
        table_names = [
            "users",
            "user_identifiers",
            "groups",
            "user_groups",  # Group-based access control tables
            memories_table,  # Memory system tables (dimension-specific)
            "memory_events",
            "projection_checkpoints",  # Memory event substrate tables
            "kg_entities",
            "kg_relationships",  # Knowledge graph tables
            "captains_log",
            "captains_log_sources",
            "lessons",  # Captain's log tables
            "credentials",  # Credential storage
            "scheduled_jobs",
            "scheduled_job_audit",  # Scheduler tables
        ]

        # Print clean formatted line
        print(
            InitEventFormatter.format_ok(
                "Database schema ready", f"{len(table_names)} tables initialized ({memories_table})"
            )
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.DATABASE_TABLE_CREATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "database"},
            description=f"Failed to create database tables: {str(e)}",
        )
        # Don't raise - allow system to continue with warning


def initialize_document_processing(formation) -> None:
    """
    Initializes the document processing configuration and chunk manager for the formation.

    Creates a `DocumentProcessingConfig` from the formation's LLM configuration and uses it
    to initialize a `DocumentChunkManager`, which is stored on the formation. Emits an
    observability event on success or a warning event if initialization fails.
    """
    try:
        # Create document processing configuration
        # Pass the llm_config instead of document_processing_config
        llm_config = formation._llm_config if hasattr(formation, "_llm_config") else {}
        config = DocumentProcessingConfig(llm_config)

        # Initialize document chunk manager
        formation._document_chunk_manager = DocumentChunkManager(document_config=config)

        # REMOVE - line 553 (user: feels pointless)

    except Exception as e:
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "document_processing"},
            description=f"Failed to initialize document processing: {str(e)}",
        )


async def initialize_mcp_services(formation) -> None:
    """
    Initialize MCP service and register configured MCP servers.

    This function:
    1. Gets the singleton MCP service instance
    2. Stores the MCP servers for later registration by overlord
    3. Registers MCP servers immediately so agents can see which use user credentials
    4. Emits observability events for tracking
    """
    try:
        from ..services.mcp import MCPService

        # Get the singleton MCP service
        mcp_service = MCPService.get_instance()
        formation._mcp_service = mcp_service

        # Get MCP configuration
        # The servers are in formation._mcp_config which comes from config["mcp"]
        mcp_config = formation._mcp_config if hasattr(formation, "_mcp_config") else {}
        servers = mcp_config.get("servers", [])

        # Store the servers in formation for later access by overlord
        formation._mcp_servers = servers

        # Enable error suppression early if we have MCP servers to avoid async generator cleanup errors
        if servers:
            formation.suppress_mcp_errors_on_exit()

        # Log MCP server configuration
        # REMOVE - line 604 (redundant with InitEventFormatter per-server lines)

        # Register MCP servers immediately so agents can see which use user credentials
        try:
            await formation._register_mcp_servers()
        except Exception as mcp_error:
            # Handle any unhandled MCP registration errors gracefully
            print("⚠️  MCP server registration encountered errors")
            print("   Some servers may be unavailable due to connectivity or authentication issues")
            print("   🚀 Formation will continue with available servers")

            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(mcp_error),
                    "error_type": type(mcp_error).__name__,
                    "handled_gracefully": True,
                },
                description=f"MCP registration partially failed but formation continues: {str(mcp_error)}",
            )

    except Exception as e:
        # MCP catastrophic failure - fail fast with init print
        failure_info = observability.InitFailureInfo(
            component="MCP initialization",
            problem=f"Failed to initialize MCP service: {str(e)}",
            context="MCP service initialization",
            causes=[
                "MCP service wrapper encountered an unexpected error",
                "This is different from individual server failures",
                "Could indicate a system-level issue",
            ],
            fixes=[
                "Check the full error trace below",
                "Verify MCP configuration in formation.afs",
                "Check system dependencies are installed",
            ],
            technical=str(e),
        )
        print("\n" + observability.InitEventFormatter.format_fail(failure_info))
        raise  # Fail fast - re-raise exception


async def initialize_artifact_service(formation, overlord) -> None:
    """Initialize the artifact generation service."""
    try:
        # REMOVE - line 651 (user: feels pointless)

        # Import and initialize the artifact service
        from .artifacts.artifact_service import get_artifact_service

        artifact_service = get_artifact_service()

        # Store the service in formation and overlord
        formation._artifact_service = artifact_service
        overlord.artifact_service = artifact_service

        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,
            level=observability.EventLevel.INFO,
            data={"service": "artifact"},
            description="Artifact generation service initialized successfully",
        )

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "service": "artifact"},
            description=f"Failed to initialize artifact service: {str(e)}",
        )
        raise


def initialize_background_services(formation) -> None:
    """
    Initializes background services for the formation, including cache management,
    request tracking, and webhook handling.

    On failure, emits a warning-level observability event with error details.
    """
    try:
        # Cache manager removed - was never actually used

        # Initialize request tracker
        from .background import RequestTracker

        formation._request_tracker = RequestTracker()

        # Initialize webhook manager
        from .background import WebhookManager

        webhook_config = formation.config.get("async", {})
        signing_secret = (
            formation._api_keys.get("admin", "") if hasattr(formation, "_api_keys") else ""
        )
        formation._webhook_manager = WebhookManager(
            default_retries=webhook_config.get("webhook_retries", 3),
            default_timeout=webhook_config.get("webhook_timeout", 30),
            signing_secret=signing_secret,
        )

        # REMOVE - line 708 (redundant with InitEventFormatter Scheduler)

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "background_services"},
            description=f"Failed to initialize background services: {str(e)}",
        )


def initialize_clarification_config(formation) -> None:
    """Initialize clarification configuration."""
    clarification_config = (
        formation._clarification_config if hasattr(formation, "_clarification_config") else {}
    )

    if not clarification_config:
        # Use default clarification config
        formation._clarification_config_obj = ClarificationConfig()
        return

    try:
        # Parse max_rounds configuration (new structure)
        max_rounds = clarification_config.get("max_rounds")
        if max_rounds and isinstance(max_rounds, dict):
            # Validate max_rounds values
            for mode, rounds in max_rounds.items():
                if not isinstance(rounds, int) or rounds < 1 or rounds > MAX_CLARIFICATION_ROUNDS:
                    raise ValueError(
                        f"max_rounds.{mode} must be integer 1-{MAX_CLARIFICATION_ROUNDS}, got {rounds}"
                    )

        # Create ClarificationConfig from formation config
        # Only set max_questions if explicitly provided for better hierarchy logic
        max_questions = (
            clarification_config.get("max_questions")
            if "max_questions" in clarification_config
            else None
        )

        formation._clarification_config_obj = ClarificationConfig(
            enabled=clarification_config.get("enabled", True),
            max_questions=max_questions,  # Backward compatibility - only if explicitly set
            max_rounds=max_rounds,  # New mode-specific configuration
            style=QuestionStyle(clarification_config.get("style", "conversational")),
            timeout_seconds=clarification_config.get("timeout_seconds", 300),
            auto_fill_from_context=clarification_config.get("auto_fill_from_context", True),
            reasoning_requirements=clarification_config.get("reasoning_requirements", True),
        )

        # REMOVE - line 765 (user: feels pointless)

    except ValueError:
        # Re-raise ValueError for configuration validation errors
        raise
    except Exception as e:
        # Use default on error (but not for validation errors)
        formation._clarification_config_obj = ClarificationConfig()
        observability.observe(
            event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "clarification"},
            description=f"Failed to initialize clarification config, using defaults: {str(e)}",
        )


def initialize_document_processing_config(formation) -> None:
    """
    Initializes the document processing configuration and chunk manager for the formation.

    Creates a `DocumentProcessingConfig` from the formation's LLM configuration
    and assigns it to the formation. Initializes a `DocumentChunkManager`
    with this configuration and assigns it to both `_document_chunker` and
    `_document_chunk_manager` for compatibility. Emits an observability event
    if document processing is enabled. On failure, logs a warning and falls
    back to a default configuration.
    """
    try:
        # Use the pre-configured LLM config
        llm_config = formation._llm_config if hasattr(formation, "_llm_config") else {}

        # Create document processing configuration instance using unified schema
        formation._document_processing_config = DocumentProcessingConfig(llm_config)

        # Log the configuration details
        # enabled = formation._document_processing_config.is_enabled()

        # Initialize DocumentChunkManager with the configuration
        formation._document_chunker = DocumentChunkManager(formation._document_processing_config)
        # Also set as _document_chunk_manager for backwards compatibility
        formation._document_chunk_manager = formation._document_chunker

    except Exception as e:
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
            level=observability.EventLevel.WARNING,
            data={"error": str(e), "service": "document_processing"},
            description=f"Failed to initialize document processing config: {str(e)}",
        )

        # Fall back to default configuration
        formation._document_processing_config = DocumentProcessingConfig({})


def load_agents_from_configuration(formation) -> None:
    """
    Load agents from formation configuration.

    This method reads the agents_config and creates pre-configured
    agent definitions that the Overlord will instantiate when needed.
    """
    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.DEBUG,
        data={"agents_count": len(formation._agents_config)},
        description=f"Processing {len(formation._agents_config)} agents from configuration",
    )

    if not formation._agents_config:
        # No agents configured - this is valid for some formations
        observability.observe(
            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
            level=observability.EventLevel.INFO,
            data={"agent_count": 0},
            description="No agents configured in formation",
        )
        return

    # Process each agent configuration
    processed_count = 0
    for agent_config in formation._agents_config:
        try:
            agent_id = agent_config.get("id")
            if not agent_id:
                pass  # REMOVED: init-phase observe() call
                continue

            # Validate agent configuration has required fields
            if not agent_config.get("name"):
                agent_config["name"] = agent_id

            processed_count += 1

            pass  # REMOVED: init-phase observe() call

        except (KeyError, ValueError, TypeError, AttributeError) as e:
            # Configuration errors that we can tolerate - log and continue to next agent
            agent_id = (
                agent_config.get("id", "unknown") if isinstance(agent_config, dict) else "unknown"
            )
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": agent_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Skipping agent '{agent_id}' due to configuration error: {type(e).__name__}: {e}",
            )
            continue
        except Exception:
            # Unexpected error - re-raise to prevent hiding real bugs
            raise

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={"agent_count": processed_count},
        description=f"Processed {processed_count} agent configurations",
    )

    # Print one line per agent for traceability
    if processed_count > 0:
        for agent_config in formation._agents_config:
            if agent_config.get("id"):
                agent_name = agent_config.get("name", agent_config.get("id"))
                agent_role = agent_config.get("role", "general")
                print(
                    InitEventFormatter.format_ok(
                        f"Loaded agent '{agent_name}'", f"role: {agent_role}"
                    )
                )


async def initialize_buffer_memory(formation, overlord, buffer_config: Dict[str, Any]) -> None:
    """Initialize buffer memory from configuration with defaults."""

    try:
        # Create BufferMemoryConfig with provided config, using defaults for missing values
        config = BufferMemoryConfig(**buffer_config)

        # Extract configuration values from the validated config
        size = config.size
        multiplier = config.multiplier
        vector_search = config.vector_search
        dimension = config.vector_dimension
        mode = config.mode
        remote_config = config.remote

        # Get embedding model for vector search if enabled. The overlord
        # returns an LLM-like object here; WorkingMemory now requires a
        # provider-prefixed string slug, so we extract ``.model_name``
        # at the call site and forward the string only.
        embedding_model_slug: Optional[str] = None
        if vector_search:
            try:
                embedding_model_obj = await overlord.get_model_for_capability("embedding")
                embedding_model_slug = getattr(embedding_model_obj, "model_name", None)
                if not isinstance(embedding_model_slug, str) or not embedding_model_slug:
                    embedding_model_slug = None
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "embedding_model"},
                    description=f"Failed to initialize embedding model for buffer memory: {str(e)}",
                )
                vector_search = False

        # Create buffer memory instance. ``embedding_model`` is the
        # string slug (or ``None`` to fall back to the helper's default).
        buffer_memory = WorkingMemory(
            formation_id=overlord.formation_id,
            max_size=size,
            buffer_multiplier=multiplier,
            dimension=dimension,
            embedding_model=embedding_model_slug,
            mode=mode,
            remote=remote_config.model_dump() if remote_config and mode == "remote" else None,
        )

        # Store on both formation and overlord for now (during transition)
        formation._buffer_memory = buffer_memory
        overlord.buffer_memory = buffer_memory

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "config_type": "buffer_memory"},
            description=f"Failed to initialize buffer memory: {str(e)}",
        )
        raise


async def _get_embedding_model(
    overlord, embedding_model_name: Optional[str] = None
) -> Optional[Any]:
    """Get embedding model with fallback to default capability.

    Args:
        overlord: The overlord instance
        embedding_model_name: Optional specific model name to use

    Returns:
        The embedding model instance or None if initialization fails
    """
    embedding_model = None

    if embedding_model_name:
        try:
            # Create model from specific name override
            embedding_model = await overlord.create_model(model=embedding_model_name)
        except Exception as e:
            # Log the specific model failure
            observability.observe(
                event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "model_name": embedding_model_name,
                    "config_type": "embedding_model",
                },
                description=f"Failed to create embedding model '{embedding_model_name}': {str(e)}",
            )
            # Fall back to default embedding capability
            try:
                embedding_model = await overlord.get_model_for_capability("embedding")
            except Exception as e2:
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e2), "config_type": "embedding_model"},
                    description=f"Failed to initialize default embedding model: {str(e2)}",
                )
    else:
        # No specific model requested, use default capability
        try:
            embedding_model = await overlord.get_model_for_capability("embedding")
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"error": str(e), "config_type": "embedding_model"},
                description=f"Failed to initialize default embedding model: {str(e)}",
            )

    return embedding_model


async def initialize_persistent_memory(
    formation, overlord, persistent_config: Dict[str, Any]
) -> None:
    """Initialize persistent memory from configuration."""
    try:
        raw_connection_string = persistent_config.get("connection_string")
        if not isinstance(raw_connection_string, str) or not raw_connection_string:
            return
        connection_string = raw_connection_string

        raw_embedding_model_name = persistent_config.get("embedding_model")
        embedding_model_name = (
            raw_embedding_model_name if isinstance(raw_embedding_model_name, str) else None
        )

        # Interpolate secrets in connection string if needed
        if "${{ secrets." in connection_string:
            try:
                interpolated = await overlord.interpolate_secrets(
                    {"connection_string": connection_string}
                )
                interpolated_connection_string = interpolated.get(
                    "connection_string", connection_string
                )
                if (
                    not isinstance(interpolated_connection_string, str)
                    or not interpolated_connection_string
                ):
                    return
                connection_string = interpolated_connection_string
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "config_type": "persistent_memory_secrets"},
                    description=f"Failed to interpolate persistent memory secrets: {str(e)}",
                )
                return

        # Get embedding model. The overlord returns an LLM-like object;
        # memory backends now require a provider-prefixed string slug.
        # Prefer the explicit slug from config; fall back to the slug
        # attached to the LLM instance via ``.model_name``.
        embedding_model = await _get_embedding_model(overlord, embedding_model_name)
        embedding_model_slug: Optional[str] = embedding_model_name
        if not isinstance(embedding_model_slug, str) or not embedding_model_slug:
            embedding_model_slug = getattr(embedding_model, "model_name", None)
            if not isinstance(embedding_model_slug, str) or not embedding_model_slug:
                embedding_model_slug = None

        # Extract and validate statement timeout once for reuse across all database manager branches
        statement_timeout = _validate_query_timeout(persistent_config)

        # Determine multi-user mode - check explicit config first, then infer from database type
        explicit_multi_user = persistent_config.get("multi_user")
        if explicit_multi_user is not None:
            is_multi_user = bool(explicit_multi_user)
        else:
            # Fall back to inferring from database type
            is_multi_user = connection_string.startswith(
                "postgresql://"
            ) or connection_string.startswith("postgres://")

        # Store multi-user mode on overlord
        overlord.is_multi_user = is_multi_user

        # Determine memory type based on connection string
        if connection_string.startswith("postgresql://") or connection_string.startswith(
            "postgres://"
        ):
            # REMOVE - line 1077 (redundant with InitEventFormatter)
            from ..services.db import get_database_manager
            from ..services.memory.long_term import LongTermMemory
            from ..services.memory.memobase import Memobase

            # Create ONE DatabaseManager for the Formation
            db_manager = get_database_manager(connection_string, statement_timeout)

            # Store db_manager on both formation and overlord
            formation._db_manager = db_manager
            overlord.db_manager = db_manager

            # Create LongTermMemory using the shared DatabaseManager.
            # ``embedding_model`` is the provider-prefixed slug string;
            # ``None`` falls back to the helper's default.
            long_term_memory = LongTermMemory(
                db_manager=db_manager,
                formation_id=overlord.formation_id,
                embedding_model=embedding_model_slug,
            )

            # Create Memobase with the LongTermMemory instance
            # Note: Memobase is still needed for user context management features
            memobase = Memobase(long_term_memory=long_term_memory)

            # Store on both formation and overlord
            formation._long_term_memory = memobase
            overlord.long_term_memory = memobase

            # Initialize required collections
            await overlord._initialize_collections()

        elif connection_string.startswith("sqlite://") or connection_string.endswith(".db"):
            # REMOVE - line 1120 (redundant with InitEventFormatter)
            from ..services.db import get_database_manager
            from ..services.memory.sqlite import SQLiteMemory

            # Strip sqlite:/// prefix to get a raw file path for SQLiteMemory
            db_path = connection_string
            if db_path.startswith("sqlite:///"):
                db_path = db_path[len("sqlite:///") :]
            elif db_path.startswith("sqlite://"):
                db_path = db_path[len("sqlite://") :]
            sqlite_memory = SQLiteMemory(
                db_path=db_path,
                formation_id=overlord.formation_id,
                embedding_model=embedding_model_slug,
            )

            # Store on both formation and overlord
            formation._long_term_memory = sqlite_memory
            overlord.long_term_memory = sqlite_memory

            # Create DatabaseManager for scheduler access (SQLite)
            db_manager = get_database_manager(connection_string, statement_timeout)
            formation._db_manager = db_manager
            overlord.db_manager = db_manager

            # Initialize required collections
            await overlord._initialize_collections()

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.MEMORY_INITIALIZATION_FAILED,
            level=observability.EventLevel.ERROR,
            data={"error": str(e), "config_type": "persistent_memory"},
            description=f"Critical error during persistent memory initialization: {str(e)}",
        )
        raise


def initialize_skills(formation, config: Dict[str, Any]) -> None:
    """Initialize skill manager from formation config.

    Skills are loaded BEFORE agents so metadata is ready for specialty
    enhancement and tool registration during agent init.

    Built-in skills (shipped with the runtime) are always loaded unless
    explicitly disabled via skills.disable_builtin.
    """
    from .skills.skill_manager import SkillManager

    public_skills: List[str] = config.get("skills", [])
    # Support both list and dict formats for skills config
    disable_builtin: List[str] = []
    skills_config = config.get("skills", [])
    if isinstance(skills_config, dict):
        public_skills = skills_config.get("names", [])
        disable_builtin = skills_config.get("disable_builtin", [])
    elif isinstance(skills_config, list):
        public_skills = skills_config

    agent_skills: Dict[str, List[str]] = {}
    for agent_config in config.get("agents", []):
        if isinstance(agent_config, dict):
            agent_id = agent_config.get("id")
            skill_list = agent_config.get("skills", [])
            if agent_id and skill_list:
                agent_skills[agent_id] = skill_list

    has_formation_skills = bool(public_skills or agent_skills)

    formation_dir = Path(formation._formation_path).parent if formation._formation_path else None
    skills_dir = formation_dir / "skills" if formation_dir else None

    if has_formation_skills and (not skills_dir or not skills_dir.is_dir()):
        raise ConfigurationValidationError(
            [f"Skills declared but skills/ directory not found at {skills_dir}"]
        )

    secrets_manager = getattr(formation, "secrets_manager", None)
    manager = SkillManager(
        skills_dir if has_formation_skills else None,
        secrets_manager=secrets_manager,
    )

    # Always load built-in skills first
    builtin_loaded = manager.load_builtin_skills(disabled=disable_builtin)

    # Then load formation-declared skills
    try:
        if public_skills:
            manager.load_public_skills(public_skills)
        for agent_id, skill_names in agent_skills.items():
            manager.load_agent_skills(agent_id, skill_names)
    except ValueError as e:
        raise ConfigurationValidationError([str(e)])

    if not manager.skills:
        return

    formation._skill_manager = manager

    all_names = list(manager.skills.keys())
    detail_parts = []
    if builtin_loaded:
        detail_parts.append(f"{len(builtin_loaded)} built-in")
    formation_count = len(all_names) - len(builtin_loaded)
    if formation_count > 0:
        detail_parts.append(f"{formation_count} formation")
    detail = f"{len(all_names)} skill(s) ({', '.join(detail_parts)})"

    print(
        InitEventFormatter.format_ok(
            f"Skills loaded: {', '.join(all_names)}",
            detail,
        )
    )

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={
            "skill_count": len(all_names),
            "public_skills": public_skills,
            "agent_skills": agent_skills,
        },
        description=f"Skills loaded: {', '.join(all_names)}",
    )

    # Warn about skills that reference secrets not present in the secrets store
    if secrets_manager:
        import asyncio

        async def _warn_missing_secrets():
            for name in all_names:
                missing = await manager.validate_secrets(name)
                if missing:
                    observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"skill_name": name, "missing_secrets": missing},
                        description=(
                            f"Skill '{name}' references secret(s) not found in store: "
                            + ", ".join(missing)
                        ),
                    )

        asyncio.ensure_future(_warn_missing_secrets())


async def initialize_rce(formation, config: Dict[str, Any]) -> None:
    """Initialize the RCE client if configured.

    Connects to the Skills RCE server, fetches capabilities, and optionally
    starts background warm-up of skill caches.

    Fails fast if rce.url is configured but the server is unreachable.
    """
    rce_config = config.get("rce", {})
    if not rce_config:
        return

    rce_url = rce_config.get("url")
    if not rce_url:
        return

    from ..services.rce.client import RCEClient, RCEError

    token = rce_config.get("token")
    timeout = rce_config.get("timeout", 60)

    client = RCEClient(url=rce_url, token=token, timeout=float(timeout))

    try:
        status = await client.connect()
    except RCEError as e:
        raise ConfigurationValidationError([f"RCE server unreachable at {rce_url}: {e}"])

    formation._rce_client = client

    langs = ", ".join(status.languages)
    print(
        InitEventFormatter.format_ok(
            f"RCE connected ({rce_url})",
            f"v{status.version}, languages: {langs}",
        )
    )

    observability.observe(
        event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
        level=observability.EventLevel.INFO,
        data={
            "rce_url": rce_url,
            "rce_version": status.version,
            "languages": status.languages,
            "runtimes": [r["name"] for r in status.runtimes if r.get("version")],
        },
        description=f"RCE connected: {rce_url} v{status.version}",
    )

    # Warm up skill caches in the background (non-blocking)
    skill_manager = getattr(formation, "_skill_manager", None)
    if skill_manager and skill_manager.skills:
        import asyncio

        async def _warm_up_skills():
            for name, metadata in skill_manager.skills.items():
                try:
                    content_hash = skill_manager.get_skill_hash(name)
                    uploaded = await client.ensure_cached(name, metadata.base_dir, content_hash)
                    if uploaded:
                        observability.observe(
                            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
                            level=observability.EventLevel.DEBUG,
                            data={"skill": name, "action": "uploaded"},
                            description=f"Skill '{name}' uploaded to RCE cache",
                        )
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"skill": name, "error": str(e)},
                        description=f"Failed to warm up skill '{name}' in RCE cache: {e}",
                    )

        asyncio.create_task(_warm_up_skills())
