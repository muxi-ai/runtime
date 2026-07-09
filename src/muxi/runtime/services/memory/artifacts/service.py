# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Artifact Memory Service - Capture and Retention Coordination
# Description:  Failure-isolated artifact capture, encryption keys, retention
# Role:         Formation-level service owning artifact memory (Phase 1)
# Usage:        Created in formation initialization, driven by the Overlord
# Author:       Muxi Framework Team
#
# Artifact Memory Phase 1 (capture everything). Coordinates:
#
# 1. Capture: ``capture_response_artifacts`` persists every MuxiArtifact a
#    response carries (generate_file outputs and anything else surfaced on
#    ``response.artifacts``). It runs as a background task after the
#    response is delivered (PRD 1.1: async and non-blocking) and never
#    raises -- a capture failure is logged and swallowed.
# 2. Encryption identity: the immutable ``formation_instance_id`` is
#    generated once at first boot into ``system_config``; per-user keys
#    are HKDF-derived from it (see blobs.py).
# 3. Versioning: same-name captures for a user extend the version chain
#    (PRD 1.4) through the storage layer.
# 4. Retention: ``expires_at`` is computed at capture from the formation's
#    retention policy; a background sweep loop (Phase 1 lifecycle pattern:
#    started by the Overlord next to the scheduler, cancelled on shutdown)
#    soft-deletes expired rows and prunes their blobs.
# 5. Audit events: each capture records an ``artifact.saved`` memory event
#    through the event substrate when it is available (metadata only --
#    blobs are not replayable from the event log, so there is no
#    projector; the artifacts table is the system of record).
#
# Default posture (PRD "Formation Schema"): artifact capture is ON for
# any formation with persistent memory. No ``artifacts`` block means
# local storage in ``./artifacts`` next to the formation, encryption
# enabled with auto-derived keys, no retention limit, and a 50MB
# ``max_size_mb`` capture cap. ``generate_file`` behavior is unchanged
# apart from this persistence side effect.
#
# Phase 2 (use the data) adds the retrieval surface on this service:
# the manifest listing the Knowledge Index renders (list_manifest /
# count_artifacts), metadata + version-chain reads backing the built-in
# get_artifact / get_artifact_content / get_artifact_history tools and
# the /v1/artifacts REST reads, and checksum dedup at capture (identical
# re-captures of a chain head are skipped, not versioned). Semantic
# search over artifact summaries stays deferred to the embedding-platform
# phase -- capture-time summaries are deterministic and unembedded.
# =============================================================================

import asyncio
import base64
import mimetypes
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ....utils.datetime_utils import utc_now_naive
from ....utils.id_generator import get_default_nanoid
from ... import observability
from ..events.models import EVENT_ARTIFACT_SAVED, SOURCE_ARTIFACT_MEMORY
from .blobs import LocalBlobStore, blob_checksum, derive_user_key, open_content, seal_content
from .models import FORMATION_INSTANCE_ID_KEY
from .storage import ArtifactMemoryStorage

# Retention policies (PRD "Formation Schema" -> artifacts.retention).
RETENTION_POLICY_LAST_UPDATED = "last_updated"
RETENTION_POLICY_LAST_ACCESSED = "last_accessed"
RETENTION_POLICIES = {RETENTION_POLICY_LAST_UPDATED, RETENTION_POLICY_LAST_ACCESSED}

# Storage backends. S3 is declared in the PRD but not shipped in Phase 1;
# ``type: s3`` fails config parsing loudly instead of silently going local.
STORAGE_TYPE_LOCAL = "local"

# Defaults (PRD: no artifacts block == these values).
DEFAULT_STORAGE_PATH = "./artifacts"
DEFAULT_RETENTION_POLICY = RETENTION_POLICY_LAST_ACCESSED
DEFAULT_RETENTION_DAYS = 0  # forever

# Maximum captured artifact size (PRD open question 1: configurable
# ``max_size_mb``, default 50MB matching the existing max_file_size_bytes).
DEFAULT_MAX_SIZE_MB = 50

# Retention sweep cadence. Expiry is day-granular (duration is in days),
# so an hourly sweep keeps deletion timely without meaningful load.
RETENTION_SWEEP_INTERVAL_SECONDS = 3600.0

# Secret interpolation guard (PRD "Security"): content carrying formation
# secret references is never captured.
_SECRET_INTERPOLATION = re.compile(r"\$\{\{\s*secrets\.")

# Fallback MIME types when the artifact carries no data-url prefix and the
# filename extension is unknown to the mimetypes registry.
_FALLBACK_TEXT_MIME = "text/plain"
_FALLBACK_BINARY_MIME = "application/octet-stream"

# Markdown is the most common generated text format but is missing from
# some platforms' mimetypes registries; register it explicitly.
mimetypes.add_type("text/markdown", ".md")


@dataclass(frozen=True)
class ArtifactMemorySettings:
    """Parsed, validated ``artifacts`` formation config block."""

    enabled: bool
    storage_type: str
    storage_path: Path
    encryption_enabled: bool
    retention_policy: str
    retention_days: int
    max_size_bytes: int


def parse_artifacts_config(
    config: Optional[Dict[str, Any]], formation_dir: Optional[str] = None
) -> ArtifactMemorySettings:
    """
    Parse and validate the ``artifacts`` formation config block.

    All fields are optional (PRD "Formation Schema"); relative local
    storage paths resolve against the formation directory the same way
    the default SQLite ``memory.db`` does.

    Raises:
        ValueError: On any invalid field value.
    """
    config = config or {}
    if not isinstance(config, dict):
        raise ValueError("artifacts config must be a dictionary")

    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("artifacts.enabled must be a boolean")

    storage = config.get("storage") or {}
    if not isinstance(storage, dict):
        raise ValueError("artifacts.storage must be a dictionary")
    storage_type = storage.get("type", STORAGE_TYPE_LOCAL)
    if storage_type != STORAGE_TYPE_LOCAL:
        raise ValueError(
            f"artifacts.storage.type {storage_type!r} is not supported yet; "
            "Phase 1 ships local storage only"
        )
    raw_path = storage.get("path", DEFAULT_STORAGE_PATH)
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("artifacts.storage.path must be a non-empty string")
    storage_path = Path(raw_path)
    if not storage_path.is_absolute() and formation_dir:
        storage_path = Path(formation_dir) / storage_path

    encryption = config.get("encryption") or {}
    if not isinstance(encryption, dict):
        raise ValueError("artifacts.encryption must be a dictionary")
    encryption_enabled = encryption.get("enabled", True)
    if not isinstance(encryption_enabled, bool):
        raise ValueError("artifacts.encryption.enabled must be a boolean")

    retention = config.get("retention") or {}
    if not isinstance(retention, dict):
        raise ValueError("artifacts.retention must be a dictionary")
    retention_policy = retention.get("policy", DEFAULT_RETENTION_POLICY)
    if retention_policy not in RETENTION_POLICIES:
        raise ValueError(
            f"artifacts.retention.policy {retention_policy!r} is invalid; "
            f"expected one of {sorted(RETENTION_POLICIES)}"
        )
    retention_days = retention.get("duration", DEFAULT_RETENTION_DAYS)
    if isinstance(retention_days, bool) or not isinstance(retention_days, int):
        raise ValueError("artifacts.retention.duration must be an integer (days)")
    if retention_days < 0:
        raise ValueError("artifacts.retention.duration must be >= 0 (0 = forever)")

    max_size_mb = config.get("max_size_mb", DEFAULT_MAX_SIZE_MB)
    if isinstance(max_size_mb, bool) or not isinstance(max_size_mb, int):
        raise ValueError("artifacts.max_size_mb must be an integer (megabytes)")
    if max_size_mb <= 0:
        raise ValueError("artifacts.max_size_mb must be > 0")

    return ArtifactMemorySettings(
        enabled=enabled,
        storage_type=storage_type,
        storage_path=storage_path,
        encryption_enabled=encryption_enabled,
        retention_policy=retention_policy,
        retention_days=retention_days,
        max_size_bytes=max_size_mb * 1024 * 1024,
    )


class ArtifactMemoryService:
    """Owns artifact capture, blob storage, and the retention sweep."""

    def __init__(
        self,
        db_manager,
        formation_id: str,
        config: Optional[Dict[str, Any]] = None,
        formation_dir: Optional[str] = None,
        memory_events=None,
    ):
        """
        Initialize the artifact memory service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all rows.
            config: The ``artifacts`` formation config block.
            formation_dir: Formation directory for relative storage paths.
            memory_events: Optional MemoryEventService for audit events.

        Raises:
            ValueError: On an invalid ``artifacts`` config block.
        """
        self.settings = parse_artifacts_config(config, formation_dir)
        self.formation_id = formation_id
        self.db_manager = db_manager
        self.memory_events = memory_events

        self.storage = ArtifactMemoryStorage(db_manager, formation_id)
        self.blob_store = LocalBlobStore(self.settings.storage_path)

        self._instance_id: Optional[str] = None
        self._sweep_task: Optional[asyncio.Task] = None

        # In-process serialization of version-chain writes (see
        # _chain_lock). Both maps are pruned when the last waiter for a
        # key releases, so they never outgrow the in-flight capture set.
        self._chain_locks: Dict[Tuple[str, str], asyncio.Lock] = {}
        self._chain_lock_waiters: Dict[Tuple[str, str], int] = {}

    @property
    def enabled(self) -> bool:
        """Whether artifact capture is active for this formation."""
        return self.settings.enabled

    # ------------------------------------------------------------------
    # Encryption identity (formation_instance_id + per-user keys)
    # ------------------------------------------------------------------

    async def _get_instance_id(self) -> str:
        """Return the immutable formation instance id, creating it once."""
        if self._instance_id is None:
            self._instance_id = await self.storage.get_or_create_system_value(
                FORMATION_INSTANCE_ID_KEY, lambda: uuid.uuid4()
            )
        return self._instance_id

    async def _get_user_key(self, user_id: str) -> Optional[bytes]:
        """Per-user AES key, or None when encryption is disabled."""
        if not self.settings.encryption_enabled:
            return None
        return derive_user_key(await self._get_instance_id(), user_id)

    # ------------------------------------------------------------------
    # Capture (async, non-blocking, failure-isolated)
    # ------------------------------------------------------------------

    async def capture_response_artifacts(
        self,
        artifacts: List[Any],
        user_id: Any,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Persist every artifact from a delivered response; never raises.

        Runs in the background after the response reaches the user. Each
        artifact is captured independently so one failure cannot drop the
        rest of the batch.
        """
        captured: List[Dict[str, Any]] = []
        if not self.enabled:
            return captured
        for artifact in artifacts or []:
            try:
                row = await self._capture_one(
                    artifact,
                    user_id=str(user_id),
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                )
                if row is not None:
                    captured.append(row)
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_ARTIFACT_CAPTURE_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "user_id": str(user_id),
                        "artifact_name": getattr(artifact, "filename", None),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Artifact capture failed: {e}",
                )
        return captured

    async def _capture_one(
        self,
        artifact: Any,
        user_id: str,
        agent_id: Optional[str],
        conversation_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Capture one MuxiArtifact; returns its row or None when skipped."""
        raw, content_type = self._decode_artifact(artifact)
        name = getattr(artifact, "filename", None) or "artifact"

        if raw is None or len(raw) == 0:
            return self._skip(user_id, name, "empty_content")

        # Size guard (PRD open question 1): oversized content is skipped,
        # not truncated -- a partial artifact would be worse than none.
        if len(raw) > self.settings.max_size_bytes:
            return self._skip(user_id, name, "exceeds_max_size")

        # Security guard (PRD): never persist content that carries secret
        # interpolation references.
        if content_type.startswith("text/") or content_type in (
            "application/json",
            "application/x-yaml",
            "application/xml",
        ):
            try:
                if _SECRET_INTERPOLATION.search(raw.decode("utf-8", errors="ignore")):
                    return self._skip(user_id, name, "secret_interpolation")
            except Exception:
                pass

        key = await self._get_user_key(user_id)

        # Same-chain captures are serialized in-process so concurrent
        # background tasks cannot both extend from the same head; the
        # partial unique chain-head index backstops other processes. The
        # dedup check and blob write sit inside the lock so a duplicate
        # decision is always made against the settled chain head.
        async with self._chain_lock(user_id, name):
            # Dedup (PRD open question 2): an identical re-capture of the
            # current head is skipped instead of minting a redundant
            # version. Compared on raw content (the encrypted blob's
            # checksum changes with every random nonce).
            if await self._duplicates_chain_head(user_id, name, raw, key):
                return self._skip(user_id, name, "duplicate_content")

            public_id = get_default_nanoid()
            blob, compressed_bytes = seal_content(raw, key)
            storage_ref = self.blob_store.ref_for(user_id, public_id)
            self.blob_store.write(storage_ref, blob)

            try:
                row = await self.storage.save_artifact(
                    user_id=user_id,
                    public_id=public_id,
                    name=name,
                    content_type=content_type,
                    category=getattr(artifact, "type", None),
                    summary=self._build_summary(name, content_type, len(raw), agent_id),
                    storage_ref=storage_ref,
                    size_bytes=len(raw),
                    compressed_bytes=compressed_bytes,
                    checksum_sha256=blob_checksum(blob),
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    expires_at=self._compute_expiry(),
                )
            except Exception:
                # Compensating cleanup: without a metadata row the blob is
                # unlocatable (random public_id) and invisible to the
                # retention sweep, so remove it before surfacing the
                # original failure. Best-effort -- a cleanup failure must
                # not mask that error.
                try:
                    self.blob_store.delete(storage_ref)
                except Exception as cleanup_error:
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_ARTIFACT_CAPTURE_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "user_id": user_id,
                            "artifact_name": name,
                            "storage_ref": storage_ref,
                            "reason": "orphaned_blob_cleanup_failed",
                            "error": str(cleanup_error),
                            "error_type": type(cleanup_error).__name__,
                        },
                        description=(
                            f"Could not remove orphaned artifact blob {storage_ref}: "
                            f"{cleanup_error}"
                        ),
                    )
                raise

        await self._record_saved_event(row)

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_ARTIFACT_CAPTURED,
            level=observability.EventLevel.INFO,
            data={
                "user_id": user_id,
                "artifact_id": row["public_id"],
                "artifact_name": name,
                "version": row["version"],
                "content_type": content_type,
                "size_bytes": row["size_bytes"],
                "compressed_bytes": row["compressed_bytes"],
                "agent_id": agent_id,
            },
            description=f"Captured artifact {name!r} v{row['version']} into artifact memory",
        )
        return row

    async def _duplicates_chain_head(
        self, user_id: str, name: str, raw: bytes, key: Optional[bytes]
    ) -> bool:
        """Whether ``raw`` is byte-identical to the current chain head.

        The stored checksum covers the *encrypted* blob (a fresh random
        nonce changes it on every capture), so identity is decided on the
        decrypted content -- gated on a size match first so the head blob
        is only opened when a duplicate is actually plausible. Fails open:
        any error (missing blob, corrupt head) means "not a duplicate" and
        the capture proceeds.
        """
        try:
            head = await self.storage.get_latest_by_name(user_id, name)
            if head is None or head["size_bytes"] != len(raw):
                return False
            head_blob = self.blob_store.read(head["storage_ref"])
            return open_content(head_blob, key) == raw
        except Exception:
            return False

    @asynccontextmanager
    async def _chain_lock(self, user_id: str, name: str):
        """
        Serialize version-chain writes for one (user, name) within this
        process.

        Two concurrent background captures of the same name would both
        read the current chain head before either commits, producing two
        live "latest" rows; this lock removes the in-process race at its
        source (the DB's chain-head unique index covers other processes).

        Keyed per (user, name) rather than per user so one response's
        multi-artifact batch and unrelated users' captures never serialize
        against each other -- the bookkeeping is a dozen lines and the
        maps are pruned when the last waiter for a key releases, so they
        never outgrow the in-flight capture set. formation_id is constant
        per service instance and is not part of the key.
        """
        key = (user_id, name)
        lock = self._chain_locks.setdefault(key, asyncio.Lock())
        self._chain_lock_waiters[key] = self._chain_lock_waiters.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            remaining = self._chain_lock_waiters[key] - 1
            if remaining:
                self._chain_lock_waiters[key] = remaining
            else:
                del self._chain_lock_waiters[key]
                self._chain_locks.pop(key, None)

    def _skip(self, user_id: str, name: str, reason: str) -> None:
        """Log one skipped artifact and return None for the capture path."""
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_ARTIFACT_CAPTURE_SKIPPED,
            level=observability.EventLevel.DEBUG,
            data={"user_id": user_id, "artifact_name": name, "reason": reason},
            description=f"Artifact capture skipped ({reason}): {name}",
        )
        return None

    @staticmethod
    def _decode_artifact(artifact: Any) -> tuple:
        """
        Extract (raw bytes, MIME type) from a MuxiArtifact.

        Text artifacts carry ``content`` (str); binary artifacts carry a
        ``data_url`` (``data:<mime>;base64,<payload>``).
        """
        content = getattr(artifact, "content", None)
        data_url = getattr(artifact, "data_url", None)
        filename = getattr(artifact, "filename", None) or ""
        guessed = mimetypes.guess_type(filename)[0]

        if content is not None:
            return content.encode("utf-8"), guessed or _FALLBACK_TEXT_MIME

        if data_url:
            header, _, payload = data_url.partition(",")
            mime = None
            if header.startswith("data:"):
                mime = header[5:].split(";", 1)[0] or None
            try:
                raw = base64.b64decode(payload)
            except Exception:
                raw = None
            return raw, mime or guessed or _FALLBACK_BINARY_MIME

        return None, guessed or _FALLBACK_BINARY_MIME

    @staticmethod
    def _build_summary(
        name: str, content_type: str, size_bytes: int, agent_id: Optional[str]
    ) -> str:
        """
        Deterministic capture-time summary. LLM summarization (and its
        embedding) lands with the retrieval phase; this keeps the NOT NULL
        summary column honest without spending a model call per capture.
        """
        producer = agent_id or "overlord"
        return f"{name} ({content_type}, {size_bytes} bytes) produced by {producer}."

    def _compute_expiry(self) -> Optional[datetime]:
        """Expiry timestamp for a new capture, or None for forever."""
        if self.settings.retention_days <= 0:
            return None
        return utc_now_naive() + timedelta(days=self.settings.retention_days)

    async def _record_saved_event(self, row: Dict[str, Any]) -> None:
        """Record the artifact.saved audit event (failure-isolated).

        The event is metadata-only audit trail; the blob and metadata row
        are already committed by the time this runs, so a recording
        failure must never make a successfully captured artifact report
        as failed. Errors are logged and swallowed.
        """
        if self.memory_events is None:
            return
        try:
            await self._record_saved_event_inner(row)
        except Exception as exc:
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "artifact_memory",
                    "operation": "record_saved_event",
                    "artifact_id": row["public_id"],
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                description="artifact.saved audit event recording failed; artifact retained",
            )

    async def _record_saved_event_inner(self, row: Dict[str, Any]) -> None:
        # v2 payload (Memory Substrate Phase 2b): carries the full
        # metadata column set so the artifact-metadata projector can
        # rebuild the row losslessly. The row is then stamped with its
        # provenance bridge, marking it event-sourced (rebuildable).
        event = await self.memory_events.record(
            user_id=row["user_id"],
            event_type=EVENT_ARTIFACT_SAVED,
            event_version=2,
            payload={
                "artifact_id": row["public_id"],
                "name": row["name"],
                "version": row["version"],
                "content_type": row["content_type"],
                "category": row["category"],
                "size_bytes": row["size_bytes"],
                "checksum_sha256": row["checksum_sha256"],
                "storage_ref": row["storage_ref"],
                "tags": row["tags"],
                "summary": row["summary"],
                "compressed_bytes": row["compressed_bytes"],
            },
            source=SOURCE_ARTIFACT_MEMORY,
            source_id=f"artifact/{row['public_id']}",
            agent_id=row["agent_id"],
            conversation_id=row["conversation_id"],
        )
        if event is not None:
            await self.storage.set_derived_event(row["id"], event["id"])

    # ------------------------------------------------------------------
    # Reads (Phase 2 retrieval surface: manifest, tools, REST)
    # ------------------------------------------------------------------

    async def list_artifacts(self, user_id: Any, **kwargs) -> List[Dict[str, Any]]:
        """List a user's artifacts (see storage.list_artifacts)."""
        return await self.storage.list_artifacts(str(user_id), **kwargs)

    async def count_artifacts(self, user_id: Any) -> int:
        """Count a user's live latest artifacts (manifest total)."""
        return await self.storage.count_artifacts(str(user_id))

    async def list_manifest(self, user_id: Any, limit: int) -> List[Dict[str, Any]]:
        """The manifest listing: latest artifacts, most recently accessed
        first, capped at ``limit`` (PRD 2.1)."""
        return await self.storage.list_artifacts(
            str(user_id), limit=limit, order_by_last_accessed=True
        )

    async def get_metadata(self, user_id: Any, public_id: str) -> Optional[Dict[str, Any]]:
        """One artifact's metadata row (user-scoped), or None. Does not
        touch ``last_accessed_at`` -- only content reads count as access."""
        return await self.storage.get_by_public_id(str(user_id), public_id)

    async def get_history(self, user_id: Any, public_id: str) -> List[Dict[str, Any]]:
        """The full version chain containing ``public_id`` (PRD 2.4),
        newest version first. Empty when the id is unknown for this user."""
        return await self.storage.get_version_chain(str(user_id), public_id)

    async def resolve_version(
        self, user_id: Any, public_id: str, version: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Resolve ``public_id`` (any version in a chain) to one row.

        ``version=None`` returns the row for the given id itself;
        a numbered version walks the chain to that version (PRD 2.3:
        ``get_artifact_content(id=..., version=2)``). None when the id or
        the requested version does not exist for this user.
        """
        if version is None:
            return await self.get_metadata(user_id, public_id)
        chain = await self.get_history(user_id, public_id)
        return next((row for row in chain if row["version"] == version), None)

    async def read_content(self, user_id: Any, public_id: str) -> bytes:
        """
        Decrypt and decompress one artifact's content.

        Verifies the stored blob against the recorded checksum, refreshes
        ``last_accessed_at``, and -- under the last_accessed retention
        policy -- extends ``expires_at``.

        Raises:
            KeyError: When the artifact does not exist for this user.
            ValueError: When the blob fails the integrity check.
        """
        user_id = str(user_id)
        row = await self.storage.get_by_public_id(user_id, public_id)
        if row is None:
            raise KeyError(f"Unknown artifact {public_id!r} for user {user_id!r}")

        blob = self.blob_store.read(row["storage_ref"])
        if blob_checksum(blob) != row["checksum_sha256"]:
            raise ValueError(f"Artifact {public_id!r} failed its integrity check")

        content = open_content(blob, await self._get_user_key(user_id))

        refreshed_expiry = None
        if (
            self.settings.retention_policy == RETENTION_POLICY_LAST_ACCESSED
            and self.settings.retention_days > 0
        ):
            refreshed_expiry = self._compute_expiry()
        await self.storage.touch_last_accessed(row["id"], refreshed_expiry)
        return content

    # ------------------------------------------------------------------
    # Retention sweep background loop (Phase 1 lifecycle pattern)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic retention sweep (no-op without a duration)."""
        if not self.enabled or self.settings.retention_days <= 0:
            return
        if self._sweep_task is not None and not self._sweep_task.done():
            return
        self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def stop(self) -> None:
        """Cancel the retention sweep loop, if running."""
        if self._sweep_task is not None:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
            self._sweep_task = None

    async def _sweep_loop(self) -> None:
        """Sleep-run loop for the retention sweep (failure-isolated)."""
        while True:
            await asyncio.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)
            try:
                await self.run_retention_sweep()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "pass": "artifact_retention_sweep",
                    },
                    description=f"Artifact retention sweep failed: {e}",
                )

    async def run_retention_sweep(self) -> int:
        """
        Soft-delete expired artifacts and prune their blobs.

        Returns the number of artifacts swept. Metadata rows are retained
        (soft delete, PRD "Security"); blobs are removed from storage.
        """
        expired = await self.storage.mark_expired()
        for row in expired:
            try:
                self.blob_store.delete(row["storage_ref"])
            except Exception:
                # The metadata row is already soft-deleted; an undeletable
                # blob must not abort the rest of the sweep.
                pass
        if expired:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_ARTIFACT_RETENTION_SWEPT,
                level=observability.EventLevel.INFO,
                data={
                    "swept": len(expired),
                    "retention_policy": self.settings.retention_policy,
                    "retention_days": self.settings.retention_days,
                },
                description=f"Retention sweep removed {len(expired)} expired artifacts",
            )
        return len(expired)
