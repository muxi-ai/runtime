# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Distillery Service - Signed Distilled-Batch Intake
# Description:  Accept path behind POST /v1/memories/distilled (Phase 3b)
# Role:         Validates, scopes, and appends pre-distilled memory events
# Usage:        Constructed by the Overlord; driven by the distilled routes
# Author:       Muxi Framework Team
#
# Memory Distillery (Memory Platform Phase 3b). The on-prem-friendly
# sibling of the /v1/memories ingestion endpoint: an organization's local
# distillation server ships SIGNED batches of already-extracted memory
# events; MUXI verifies, validates, embeds, and appends. No LLM extraction,
# no classification, no filtering -- just verify, embed, append.
#
# Semantics, exactly:
#
# - Authentication is registration + Ed25519 (verification.py): the
#   distillery is a SYSTEM-LEVEL principal whose authority is its
#   registration scope, not per-user GBAC grants. Every accepted event
#   still lands USER-SCOPED under its own user_id, so cross-user
#   visibility stays governed by groups at retrieval time.
# - Accept is event-first and idempotent, riding the substrate's
#   (source="distillery", source_id) partial unique index: retried
#   batches never duplicate; already-seen events are silently skipped
#   (reported in the `duplicates` count).
# - Partial acceptance is the default: invalid/out-of-scope events are
#   rejected individually with an indexed reason; the rest of the batch
#   proceeds.
# - Projections run in a background job (shared RequestTracker, pollable
#   via GET /v1/memories/distilled/{processing_id}): fact.extracted rows
#   land in the flat-fact/vector projection through the same
#   apply_fact_event helper the ingestion pipeline and replay use;
#   log.entry rows land through the captain's log service;
#   interaction.turn events are recorded in the log only.
# - Embeddings: mode "none" re-embeds on receipt (long_term_memory.add's
#   normal path). Mode "pre_computed" stores shipped vectors ONLY when
#   the declared model name matches the formation's embedding model (and
#   the vector length matches); otherwise graceful degradation -- the
#   stale vectors are discarded, the text is re-embedded, and a
#   high-signal observability warning fires. Never a rejection.
# =============================================================================

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ....formation.background.request_tracker import RequestState, RequestStatus
from ....utils.datetime_utils import utc_now_iso
from ....utils.id_generator import get_default_nanoid
from ... import observability
from ..events.models import (
    DECAY_RATES,
    DECAY_STATIC,
    EVENT_FACT_EXTRACTED,
    EVENT_INTERACTION_TURN,
    EVENT_LOG_ENTRY,
    validate_event_payload,
)
from ..events.projectors import apply_fact_event
from .models import PROVISIONAL_CONFIDENCE_CAP, STATUS_ACTIVE, TRUST_PROVISIONAL, TRUST_VERIFIED
from .registry import DistilleryRegistry
from .verification import (
    DEFAULT_SIGNATURE_MAX_AGE_SECONDS,
    SignatureVerificationError,
    check_timestamp,
    verify_signature,
)

# The substrate source every distilled event carries (PRD "Event Format").
SOURCE_DISTILLERY = "distillery"

# Event types a distillery may ship: the intersection of the PRD's batch
# vocabulary and the event types the substrate supports today. The PRD also
# names entity.resolved (doesn't exist in the substrate yet) and
# artifact.saved (exists as an internal metadata-only audit event since
# Artifact Memory Phase 1, but distilled batches cannot ship it -- there
# is no blob transport, so a distilled artifact.saved would reference
# content the runtime never received). Both stay rejected per-event until
# their phases land.
DISTILLERY_EVENT_TYPES = (EVENT_FACT_EXTRACTED, EVENT_LOG_ENTRY, EVENT_INTERACTION_TURN)

# Batch-level embedding modes (PRD "Embeddings").
EMBEDDING_MODE_NONE = "none"
EMBEDDING_MODE_PRE_COMPUTED = "pre_computed"
EMBEDDING_MODES = {EMBEDDING_MODE_NONE, EMBEDDING_MODE_PRE_COMPUTED}

# The one embeddable payload field per event type. fact.extracted's
# ``memory`` text is what the flat-fact projection embeds; log.entry and
# interaction.turn projections don't store vectors, so shipped vectors for
# them are ignored (PRD: vectors for fields MUXI doesn't embed are ignored).
EMBEDDABLE_FIELDS = {EVENT_FACT_EXTRACTED: "memory"}

# Hard ceilings (PRD "Batch Size Limits"). Registration scopes can lower
# these but never raise them.
HARD_MAX_BATCH_SIZE = 10_000
DEFAULT_MAX_EVENTS_PER_DAY = 1_000_000

# Envelope keys accepted on each event (the substrate payload registry
# handles payload-level strictness; unknown envelope keys are rejected so
# typos fail loudly instead of being silently dropped).
_EVENT_KEYS = {
    "event_type",
    "event_version",
    "user_id",
    "occurred_at",
    "source",
    "source_id",
    "source_confidence",
    "decay_rate",
    "expires_at",
    "payload",
    "conversation_id",
    "agent_id",
    "embedding_vectors",
}

# Per-event projection dispositions reported by the status endpoint.
DISPOSITION_PROJECTED = "projected"  # landed in a projection (facts, log)
DISPOSITION_RECORDED = "recorded"  # event-log only (interaction.turn)
DISPOSITION_FAILED = "failed"


class DistilleryUnavailableError(Exception):
    """Distillery intake requires the memory event substrate + enabled config."""


class DistilleryAuthError(Exception):
    """Batch authentication failed (401 semantics)."""


class DistilleryRevokedError(Exception):
    """The distillery registration was revoked (410 semantics)."""


class DistilleryRateLimitError(Exception):
    """The distillery's daily event quota would be exceeded (429 semantics)."""

    def __init__(self, max_events_per_day: int):
        super().__init__(
            f"Daily event quota reached for this distillery "
            f"(max {max_events_per_day} events/day); retry after the UTC day rolls over. "
            f"Idempotent (source_id) retries are always safe."
        )
        self.max_events_per_day = max_events_per_day


@dataclass
class DistilledEvent:
    """One validated distilled event, normalized for the substrate."""

    event_type: str
    payload: Dict[str, Any]
    user_id: str
    source_id: str
    event_version: int = 1
    occurred_at: Optional[datetime] = None
    source_confidence: float = 1.0
    decay_rate: str = DECAY_STATIC
    expires_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    embedding_vectors: Dict[str, List[float]] = field(default_factory=dict)


def _parse_iso_timestamp(value: str, key: str) -> datetime:
    """Parse an ISO 8601 string into the substrate's naive-UTC shape."""
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{key}' is not valid ISO 8601: {value!r}")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def user_id_in_scope(user_id: str, user_ids_scope: Any) -> bool:
    """Match one event's user_id against a registration's user_ids scope.

    Scope shapes (PRD "Distillery Registration"): the string "all", an
    explicit list of ids, or "pattern:<glob>" matched with fnmatch
    semantics (e.g. ``pattern:*@acme.com``). Anything else fails closed.
    """
    import fnmatch

    if user_ids_scope in (None, "all"):
        return True
    if isinstance(user_ids_scope, str):
        if user_ids_scope.startswith("pattern:"):
            return fnmatch.fnmatchcase(user_id, user_ids_scope[len("pattern:") :])
        return user_id == user_ids_scope
    if isinstance(user_ids_scope, (list, tuple)):
        return user_id in {str(entry) for entry in user_ids_scope}
    return False


def validate_distilled_event(
    entry: Any,
    scope: Dict[str, Any],
    trust_level: str,
    is_multi_user: bool,
) -> Tuple[Optional[DistilledEvent], Optional[str]]:
    """Validate one event against the contract + the distillery's scope.

    Returns (event, None) on success, (None, precise reason) on rejection.
    Scope violations are rejections, not batch failures (PRD "Scope
    Enforcement").
    """
    if not isinstance(entry, dict):
        return None, f"event must be an object, got {type(entry).__name__}"

    unknown = sorted(set(entry) - _EVENT_KEYS)
    if unknown:
        return None, f"unknown event keys: {unknown}"

    event_type = entry.get("event_type")
    if event_type not in DISTILLERY_EVENT_TYPES:
        return None, (
            f"unsupported event_type {event_type!r}; "
            f"expected one of {sorted(DISTILLERY_EVENT_TYPES)}"
        )
    allowed_types = scope.get("event_types")
    if allowed_types is not None and event_type not in allowed_types:
        return None, f"event_type {event_type!r} outside distillery scope"

    event_version = entry.get("event_version", 1)
    if not isinstance(event_version, int) or isinstance(event_version, bool):
        return None, "'event_version' must be an integer"

    user_id = entry.get("user_id")
    if user_id is None:
        if is_multi_user:
            return None, "'user_id' is required for multi-user formations"
        user_id = "0"  # single-user convention
    if not isinstance(user_id, str) or not user_id.strip():
        return None, "'user_id' must be a non-empty string"
    user_id = user_id.strip()
    if not user_id_in_scope(user_id, scope.get("user_ids")):
        return None, f"user_id {user_id!r} outside distillery scope"

    source = entry.get("source")
    if source is not None and source != SOURCE_DISTILLERY:
        return None, f"'source' must be \"{SOURCE_DISTILLERY}\" when provided, got {source!r}"

    source_id = entry.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        return None, "'source_id' is required (the event's origin in the raw source)"
    source_id = source_id.strip()
    if len(source_id) > 255:
        return None, f"'source_id' must be at most 255 characters, got {len(source_id)}"

    occurred_at = None
    if entry.get("occurred_at") is not None:
        try:
            occurred_at = _parse_iso_timestamp(entry["occurred_at"], "occurred_at")
        except ValueError as exc:
            return None, str(exc)

    source_confidence = entry.get("source_confidence", 1.0)
    if not isinstance(source_confidence, (int, float)) or isinstance(source_confidence, bool):
        return None, "'source_confidence' must be a number between 0 and 1"
    source_confidence = float(source_confidence)
    if not 0.0 <= source_confidence <= 1.0:
        return None, f"'source_confidence' must be between 0 and 1, got {source_confidence}"
    if trust_level == TRUST_PROVISIONAL:
        # Provisional distilleries never assert more confidence than the
        # cap, regardless of what the payload declares (PRD trust model).
        source_confidence = min(source_confidence, PROVISIONAL_CONFIDENCE_CAP)

    decay_rate = entry.get("decay_rate", DECAY_STATIC)
    if decay_rate not in DECAY_RATES:
        return None, f"invalid decay_rate {decay_rate!r}; expected one of {sorted(DECAY_RATES)}"

    expires_at = None
    if entry.get("expires_at") is not None:
        try:
            expires_at = _parse_iso_timestamp(entry["expires_at"], "expires_at")
        except ValueError as exc:
            return None, str(exc)

    payload = entry.get("payload")
    try:
        validate_event_payload(event_type, payload, event_version)
    except ValueError as exc:
        return None, f"invalid event schema: {exc}"

    conversation_id = entry.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, str):
        return None, "'conversation_id' must be a string when provided"

    embedding_vectors: Dict[str, List[float]] = {}
    raw_vectors = entry.get("embedding_vectors")
    if raw_vectors is not None:
        if not isinstance(raw_vectors, dict):
            return None, "'embedding_vectors' must be an object mapping fields to float arrays"
        for field_name, vector in raw_vectors.items():
            if not isinstance(vector, list) or not vector:
                return None, f"embedding vector for {field_name!r} must be a non-empty array"
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vector):
                return None, f"embedding vector for {field_name!r} must contain only numbers"
            embedding_vectors[str(field_name)] = [float(v) for v in vector]

    return (
        DistilledEvent(
            event_type=event_type,
            event_version=event_version,
            payload=dict(payload),
            user_id=user_id,
            source_id=source_id,
            occurred_at=occurred_at,
            source_confidence=source_confidence,
            decay_rate=decay_rate,
            expires_at=expires_at,
            conversation_id=conversation_id,
            embedding_vectors=embedding_vectors,
        ),
        None,
    )


class MemoryDistilleryService:
    """Owns distilled-batch authentication, accept path, and projections."""

    def __init__(self, overlord):
        self.overlord = overlord
        formation_config = getattr(overlord, "formation_config", None) or {}
        memory_config = formation_config.get("memory") or {}
        config = memory_config.get("distillery") or {}

        # Inert without explicit opt-in: formations that never configure
        # memory.distillery get no endpoint behavior beyond a formed 503.
        self.enabled = bool(config.get("enabled", False))
        self.default_trust_level = str(config.get("default_trust_level", TRUST_PROVISIONAL))
        if self.default_trust_level not in (TRUST_PROVISIONAL, TRUST_VERIFIED):
            self.default_trust_level = TRUST_PROVISIONAL
        self.default_max_batch_size = self._int_config(
            config, "default_max_batch_size", HARD_MAX_BATCH_SIZE
        )
        self.default_max_events_per_day = self._int_config(
            config, "default_max_events_per_day", DEFAULT_MAX_EVENTS_PER_DAY
        )
        self.signature_max_age_seconds = self._int_config(
            config, "signature_max_age_seconds", DEFAULT_SIGNATURE_MAX_AGE_SECONDS
        )

        self._registry: Optional[DistilleryRegistry] = None
        # Per-(distillery, UTC day) accepted-event counters. Process-local
        # by design (matches the ingestion in-flight cap posture): the
        # smallest viable quota guard, documented as per-node.
        self._daily_counts: Dict[Tuple[str, str], int] = {}
        self._daily_lock = asyncio.Lock()

    @staticmethod
    def _int_config(config: Dict[str, Any], key: str, default: int) -> int:
        try:
            return int(config.get(key, default))
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # Dependencies (resolved lazily, mirroring the ingestion service)
    # ------------------------------------------------------------------

    @property
    def memory_events(self):
        return getattr(self.overlord, "memory_events", None)

    def _require_substrate(self):
        if not self.enabled:
            raise DistilleryUnavailableError(
                "Memory distillery is not enabled for this formation " "(memory.distillery.enabled)"
            )
        memory_events = self.memory_events
        if memory_events is None or not getattr(memory_events, "enabled", False):
            raise DistilleryUnavailableError(
                "Memory distillery requires persistent memory with the memory "
                "event substrate enabled (memory.events.enabled)"
            )
        return memory_events

    @property
    def registry(self) -> DistilleryRegistry:
        """The distillery trust registry (requires the substrate's DB)."""
        if self._registry is None:
            memory_events = self._require_substrate()
            self._registry = DistilleryRegistry(
                memory_events.db_manager, memory_events.formation_id
            )
        return self._registry

    def scope_defaults(self, scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Fill a registration scope with the formation-level defaults."""
        scope = dict(scope or {})
        scope.setdefault("user_ids", "all")
        scope.setdefault("event_types", list(DISTILLERY_EVENT_TYPES))
        scope.setdefault("max_events_per_day", self.default_max_events_per_day)
        scope.setdefault("max_batch_size", self.default_max_batch_size)
        return scope

    # ------------------------------------------------------------------
    # Authentication (fail-closed; see verification.py)
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        distillery_id: Optional[str],
        signature: Optional[str],
        timestamp: Optional[str],
        body: bytes,
    ) -> Dict[str, Any]:
        """Authenticate one batch; returns the distillery record.

        Raises:
            DistilleryUnavailableError: Feature disabled / substrate missing.
            DistilleryAuthError: Missing headers, unknown distillery,
                replay-window violation, or an invalid signature.
            DistilleryRevokedError: The registration was revoked.
        """
        self._require_substrate()
        if not distillery_id or not str(distillery_id).strip():
            raise DistilleryAuthError("X-Distillery-ID header is required")
        distillery_id = str(distillery_id).strip()

        try:
            check_timestamp(timestamp, time.time(), self.signature_max_age_seconds)
        except SignatureVerificationError as exc:
            self._observe_auth_failure(distillery_id, str(exc))
            raise DistilleryAuthError(str(exc))

        distillery = await self.registry.get(distillery_id)
        if distillery is None:
            self._observe_auth_failure(distillery_id, "unknown distillery id")
            raise DistilleryAuthError("Unknown distillery or invalid signature")
        if distillery["status"] != STATUS_ACTIVE:
            self._observe_auth_failure(distillery_id, "distillery revoked")
            raise DistilleryRevokedError("This distillery registration has been revoked")

        try:
            verify_signature(
                distillery["public_key"],
                signature,
                str(timestamp),
                distillery_id,
                body,
            )
        except SignatureVerificationError as exc:
            self._observe_auth_failure(distillery_id, str(exc))
            raise DistilleryAuthError("Unknown distillery or invalid signature")
        return distillery

    def _observe_auth_failure(self, distillery_id: str, reason: str) -> None:
        """Failed batch auth triggers an observability alert (PRD)."""
        observability.observe(
            event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "service": "memory_distillery",
                "distillery_id": distillery_id,
                "reason": reason,
                "channel": "api",
            },
            description=f"Distilled batch authentication failed: {reason}",
        )

    # ------------------------------------------------------------------
    # Batch validation
    # ------------------------------------------------------------------

    def validate_batch(
        self, batch: Any, distillery: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Validate the batch envelope; returns (meta, None) or (None, error)."""
        if not isinstance(batch, dict):
            return None, "request body must be a JSON object"

        batch_id = batch.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id.strip():
            return None, "'batch_id' is required and must be a non-empty string"

        events = batch.get("events")
        if not isinstance(events, list) or not events:
            return None, "'events' must be a non-empty array"
        scope = distillery.get("scope") or {}
        max_batch = min(
            int(scope.get("max_batch_size", self.default_max_batch_size)),
            HARD_MAX_BATCH_SIZE,
        )
        if len(events) > max_batch:
            return None, f"batch exceeds max_batch_size ({len(events)} > {max_batch})"

        embedding_mode = batch.get("embedding_mode", EMBEDDING_MODE_NONE)
        if embedding_mode not in EMBEDDING_MODES:
            return None, (
                f"invalid embedding_mode {embedding_mode!r}; "
                f"expected one of {sorted(EMBEDDING_MODES)}"
            )
        embedding_model = batch.get("embedding_model")
        if embedding_mode == EMBEDDING_MODE_PRE_COMPUTED:
            # Model names follow MUXI's provider-prefixed convention
            # (local/..., openai/...); reject shapes that can never match.
            if not isinstance(embedding_model, str) or "/" not in embedding_model:
                return None, (
                    "'embedding_model' is required when embedding_mode is "
                    '"pre_computed" and must be a provider-prefixed model name '
                    '(e.g. "local/all-MiniLM-L6-v2")'
                )

        return (
            {
                "batch_id": batch_id.strip(),
                "events": events,
                "embedding_mode": embedding_mode,
                "embedding_model": embedding_model,
                "distillery_version": batch.get("distillery_version"),
                "distiller_config_hash": batch.get("distiller_config_hash"),
            },
            None,
        )

    # ------------------------------------------------------------------
    # Daily quota (process-local, per UTC day)
    # ------------------------------------------------------------------

    async def _check_quota(self, distillery: Dict[str, Any], incoming: int) -> None:
        scope = distillery.get("scope") or {}
        max_per_day = int(scope.get("max_events_per_day", self.default_max_events_per_day))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = (distillery["distillery_id"], today)
        async with self._daily_lock:
            # Prune counters from previous days so the map stays tiny.
            stale = [k for k in self._daily_counts if k[1] != today]
            for k in stale:
                del self._daily_counts[k]
            if self._daily_counts.get(key, 0) + incoming > max_per_day:
                raise DistilleryRateLimitError(max_per_day)

    async def _consume_quota(self, distillery: Dict[str, Any], count: int) -> None:
        if count <= 0:
            return
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = (distillery["distillery_id"], today)
        async with self._daily_lock:
            self._daily_counts[key] = self._daily_counts.get(key, 0) + count

    # ------------------------------------------------------------------
    # Accept path (event-first, partial acceptance)
    # ------------------------------------------------------------------

    async def submit(self, distillery: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Accept one authenticated, envelope-validated batch.

        Appends valid events to the substrate immediately (idempotent),
        rejects invalid ones with indexed reasons, and enqueues the
        projection job for newly created events.

        Returns the response body for POST /v1/memories/distilled.

        Raises:
            DistilleryUnavailableError: Substrate missing or disabled.
            DistilleryRateLimitError: Daily quota would be exceeded.
        """
        memory_events = self._require_substrate()
        scope = self.scope_defaults(distillery.get("scope"))
        trust_level = distillery.get("trust_level", TRUST_PROVISIONAL)
        is_multi_user = bool(getattr(self.overlord, "is_multi_user", False))
        events: List[Any] = meta["events"]

        # Pass 1 (read-only): validate every event and resolve duplicates
        # against the substrate's idempotency key, WITHOUT appending or
        # consuming anything.
        rejections: List[Dict[str, Any]] = []
        duplicates = 0
        net_new: List[Tuple[int, DistilledEvent]] = []
        for index, entry in enumerate(events):
            event, reason = validate_distilled_event(entry, scope, trust_level, is_multi_user)
            if event is None:
                rejections.append({"index": index, "reason": reason})
                continue
            existing = await memory_events.storage.find_by_source_id(
                event.user_id, SOURCE_DISTILLERY, event.source_id
            )
            if existing is not None:
                duplicates += 1
            else:
                net_new.append((index, event))

        # Quota gates the NET-NEW event count only: a full-duplicate retry
        # must always succeed regardless of quota state (the idempotent
        # retry guarantee), and mixed batches only need headroom for the
        # events they would actually create. Raising here appends nothing
        # and consumes nothing, so the whole batch stays safely retryable.
        await self._check_quota(distillery, len(net_new))

        # Pass 2: append the net-new events. An append can still resolve
        # to an existing event (a concurrent writer, or the same source_id
        # appearing twice within this batch) -- those count as duplicates.
        to_process: List[Tuple[int, DistilledEvent, Dict[str, Any]]] = []
        for index, event in net_new:
            try:
                stored, created = await memory_events.storage.append(
                    user_id=event.user_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    source=SOURCE_DISTILLERY,
                    source_id=event.source_id,
                    source_confidence=event.source_confidence,
                    event_version=event.event_version,
                    occurred_at=event.occurred_at,
                    decay_rate=event.decay_rate,
                    expires_at=event.expires_at,
                    conversation_id=event.conversation_id,
                )
            except ValueError as exc:
                # Defensive: validate_distilled_event mirrors the substrate
                # checks, so this only fires on drift between the two.
                rejections.append({"index": index, "reason": str(exc)})
                continue
            if created:
                to_process.append((index, event, stored))
            else:
                duplicates += 1

        await self._consume_quota(distillery, len(to_process))

        processing_id = None
        if to_process:
            processing_id = f"dst_{get_default_nanoid()}"
            tracker = self.overlord.request_tracker
            state = RequestState(
                id=processing_id,
                status=RequestStatus.PENDING,
                start_time=time.time(),
                # Ownership marker for status polling: distilled jobs span
                # many memory user_ids, so the job belongs to the
                # distillery principal, not any one user.
                user_id=f"distillery:{distillery['distillery_id']}",
            )
            await tracker.track_request(processing_id, state)
            try:
                task = asyncio.create_task(
                    self._process_job(processing_id, distillery, meta, to_process)
                )
            except BaseException:
                await tracker.remove_request(processing_id)
                raise
            state.task_ref = task

        rejections.sort(key=lambda r: r["index"])
        response = {
            "batch_id": meta["batch_id"],
            "accepted": len(to_process),
            "duplicates": duplicates,
            "rejected": len(rejections),
            "rejections": rejections,
            "processing_id": processing_id,
        }
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_DISTILLED_ACCEPTED,
            level=observability.EventLevel.INFO,
            data={
                "distillery_id": distillery["distillery_id"],
                "batch_id": meta["batch_id"],
                "processing_id": processing_id,
                "accepted": len(to_process),
                "duplicates": duplicates,
                "rejected": len(rejections),
                "embedding_mode": meta["embedding_mode"],
            },
            description=(
                f"Distilled batch {meta['batch_id']} accepted: "
                f"{len(to_process)} event(s), {duplicates} duplicate(s), "
                f"{len(rejections)} rejection(s)"
            ),
        )
        return response

    # ------------------------------------------------------------------
    # Background projection job
    # ------------------------------------------------------------------

    def _formation_embedding_model(self) -> Optional[str]:
        """The formation's configured embedding model slug.

        overlord.long_term_memory is either the storage layer itself or
        the Memobase multi-user wrapper around it; the model name lives on
        the storage layer.
        """
        long_term_memory = getattr(self.overlord, "long_term_memory", None)
        configured = getattr(long_term_memory, "_embedding_model_name", None)
        if configured is None:
            inner = getattr(long_term_memory, "long_term_memory", None)
            configured = getattr(inner, "_embedding_model_name", None)
        return configured

    def _embedding_matches(self, declared_model: Optional[str]) -> bool:
        """Model-name match against the formation's embedding model.

        Names, not dimensions (PRD "Model matching"): two different
        same-dim models live in incompatible semantic spaces.
        """
        configured = self._formation_embedding_model()
        return bool(declared_model) and declared_model == configured

    def _vector_for(self, event: DistilledEvent, use_vectors: bool) -> Optional[List[float]]:
        """The shipped vector to store for one event, if usable."""
        if not use_vectors:
            return None
        field_name = EMBEDDABLE_FIELDS.get(event.event_type)
        if field_name is None:
            return None
        vector = event.embedding_vectors.get(field_name)
        if vector is None:
            # Hybrid mode: events without vectors are embedded on receipt.
            return None
        long_term_memory = getattr(self.overlord, "long_term_memory", None)
        expected_dim = getattr(long_term_memory, "dimension", None)
        if expected_dim and len(vector) != int(expected_dim):
            # Dimension backstop: model names matched but the vector shape
            # is wrong -- discard and re-embed rather than store garbage.
            return None
        return vector

    async def _process_job(
        self,
        processing_id: str,
        distillery: Dict[str, Any],
        meta: Dict[str, Any],
        entries: List[Tuple[int, DistilledEvent, Dict[str, Any]]],
    ) -> None:
        """Project one accepted batch's events; never raises."""
        tracker = self.overlord.request_tracker
        use_vectors = False
        if meta["embedding_mode"] == EMBEDDING_MODE_PRE_COMPUTED:
            use_vectors = self._embedding_matches(meta["embedding_model"])
            if not use_vectors:
                # Graceful degradation (PRD Option B): accept, discard the
                # stale vectors, re-embed with the formation's model, and
                # surface a high-signal warning for dashboards.
                observability.observe(
                    event_type=(
                        observability.ConversationEvents.MEMORY_DISTILLED_EMBEDDING_MISMATCH
                    ),
                    level=observability.EventLevel.WARNING,
                    data={
                        "distillery_id": distillery["distillery_id"],
                        "batch_id": meta["batch_id"],
                        "declared_model": meta["embedding_model"],
                        "formation_model": self._formation_embedding_model(),
                    },
                    description=(
                        "Distillery embedding model mismatch: shipped vectors "
                        "discarded, re-embedding with the formation's model"
                    ),
                )

        try:
            await tracker.update_request(processing_id, RequestStatus.PROCESSING)
            reports: List[Dict[str, Any]] = []
            for index, event, stored in entries:
                report: Dict[str, Any] = {
                    "index": index,
                    "event_id": stored["public_id"],
                    "event_type": event.event_type,
                    "user_id": event.user_id,
                }
                try:
                    report["disposition"] = await self._project_event(event, stored, use_vectors)
                except Exception as exc:
                    report["disposition"] = DISPOSITION_FAILED
                    report["error"] = str(exc)
                reports.append(report)

            counts = {
                DISPOSITION_PROJECTED: sum(
                    1 for r in reports if r["disposition"] == DISPOSITION_PROJECTED
                ),
                DISPOSITION_RECORDED: sum(
                    1 for r in reports if r["disposition"] == DISPOSITION_RECORDED
                ),
                DISPOSITION_FAILED: sum(
                    1 for r in reports if r["disposition"] == DISPOSITION_FAILED
                ),
            }
            result = {
                "batch_id": meta["batch_id"],
                "items": reports,
                "counts": counts,
                "pre_computed_vectors_used": use_vectors,
                "completed_at": utc_now_iso(),
            }
            await tracker.update_request(processing_id, RequestStatus.COMPLETED, result=result)
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_DISTILLED_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "distillery_id": distillery["distillery_id"],
                    "batch_id": meta["batch_id"],
                    "processing_id": processing_id,
                    "counts": counts,
                    "pre_computed_vectors_used": use_vectors,
                },
                description=f"Distilled batch {meta['batch_id']} projected: {counts}",
            )
        except Exception as exc:
            await tracker.update_request(processing_id, RequestStatus.FAILED, error=str(exc))
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_DISTILLED_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "distillery_id": distillery["distillery_id"],
                    "batch_id": meta["batch_id"],
                    "processing_id": processing_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                description=f"Distilled batch processing failed: {exc}",
            )

    async def _project_event(
        self, event: DistilledEvent, stored: Dict[str, Any], use_vectors: bool
    ) -> str:
        """Apply one appended event to its projection; returns disposition."""
        if event.event_type == EVENT_FACT_EXTRACTED:
            long_term_memory = getattr(self.overlord, "long_term_memory", None)
            if long_term_memory is None:
                raise DistilleryUnavailableError("long-term memory is not available")
            await apply_fact_event(
                long_term_memory,
                event.user_id,
                event.payload,
                event_id=stored["id"],
                embedding=self._vector_for(event, use_vectors),
            )
            return DISPOSITION_PROJECTED

        if event.event_type == EVENT_LOG_ENTRY:
            captains_log = getattr(self.overlord, "captains_log", None)
            if captains_log is None:
                # No captain's log projection configured: the event stays
                # in the log and replays once the projection exists.
                return DISPOSITION_RECORDED
            await captains_log.apply_log_entry_event(
                event.user_id, event.payload, event_id=stored["id"]
            )
            return DISPOSITION_PROJECTED

        # interaction.turn: recorded in the substrate only (same posture as
        # chat-path interaction events -- no projector consumes them yet).
        return DISPOSITION_RECORDED
