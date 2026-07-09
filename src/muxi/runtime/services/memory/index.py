# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Index - Navigable Memory Catalog
# Description:  Generates and caches the per-user memory index blob
# Role:         Formation-level service injected at retrieval start
# Usage:        Created in formation initialization, read by the Overlord
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 4 (Knowledge Index).
#
# Vector search answers "what's similar to X?" -- the index answers "what do
# I actually know about this user?". A lightweight text blob cataloging the
# memory store (entities, captain's log span, artifacts, knowledge gaps
# flagged by the last lint) is injected at the start of every retrieval
# pass, before any semantic search, so agents can navigate by intent.
#
# Generation and caching:
# - The blob is cached in memory per user and write-through persisted to the
#   system_config table (key ``memory_index:{user_id}``, PRD format).
# - Regeneration triggers (config ``regenerate_on``) are implemented as a
#   cheap fingerprint check on read -- log entry count/updated stamp
#   ("log_entry"), artifact count ("artifact_save"), entity count moving by
#   entity_count_threshold ("entity_count_threshold") -- plus an explicit
#   ``invalidate()`` hook the lint job calls after each run ("lint"). The
#   fingerprint costs three indexed COUNT-class queries, no LLM work.
# - A blob older than STALE_AFTER_SECONDS (24h) always regenerates, which is
#   also the staleness bound the lint job enforces.
#
# Size cap: the rendered blob never exceeds max_tokens (default 300,
# estimated at CHARS_PER_TOKEN chars/token); each section truncates with an
# explicit count of omitted items.
#
# Failure isolation: get_index_block returns "" on any error; regeneration
# and persistence failures never affect the chat turn.
#
# Cross-PRD seam (artifact-memory Phase 2): the artifacts section reads from
# the artifact memory service's ``list_artifacts`` -- the artifact manifest
# rides this index without further wiring.
# =============================================================================

import json
import time
from datetime import date as date_type
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from ...utils.datetime_utils import utc_now_naive
from .. import observability
from .artifacts.models import SystemConfig
from .graph.models import STATUS_ACTIVE, KGEntity
from .log.models import CaptainsLogEntry

# PRD defaults (Configuration Reference -> memory.index).
DEFAULT_MAX_TOKENS = 300
DEFAULT_ENTITY_COUNT_THRESHOLD = 10
REGENERATE_ON_LINT = "lint"
REGENERATE_ON_LOG_ENTRY = "log_entry"
REGENERATE_ON_ARTIFACT_SAVE = "artifact_save"
REGENERATE_ON_ENTITY_THRESHOLD = "entity_count_threshold"
REGENERATE_TRIGGERS = {
    REGENERATE_ON_LINT,
    REGENERATE_ON_LOG_ENTRY,
    REGENERATE_ON_ARTIFACT_SAVE,
    REGENERATE_ON_ENTITY_THRESHOLD,
}
DEFAULT_REGENERATE_ON = sorted(REGENERATE_TRIGGERS)

# Rough chars-per-token estimate used for the size cap.
CHARS_PER_TOKEN = 4

# A cached blob older than this always regenerates (PRD lint check:
# "Knowledge index stale (not regenerated in > 24h) -> force regeneration").
STALE_AFTER_SECONDS = 86400

# system_config key formats (PRD "stored as a single row in system_config").
INDEX_KEY_FORMAT = "memory_index:{user_id}"
LINT_FINDINGS_KEY_FORMAT = "memory_lint:{user_id}"

# How many rows each section may fetch before rendering/truncation.
MAX_ENTITIES_FETCHED = 50
MAX_GAPS_RENDERED = 5


class KnowledgeIndexService:
    """Generates, caches, and serves the per-user memory index blob."""

    def __init__(
        self,
        db_manager,
        formation_id: str,
        config: Optional[Dict[str, Any]] = None,
        knowledge_graph=None,
        captains_log=None,
        artifact_memory=None,
    ):
        """
        Initialize the knowledge index service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all rows.
            config: The ``memory.index`` formation config section.
            knowledge_graph: Phase 1 KnowledgeGraphService (or None).
            captains_log: Phase 2 CaptainsLogService (or None).
            artifact_memory: ArtifactMemoryService (or None) -- the clean
                seam the artifact manifest rides.
        """
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.max_tokens = int(config.get("max_tokens", DEFAULT_MAX_TOKENS))
        self.entity_count_threshold = int(
            config.get("entity_count_threshold", DEFAULT_ENTITY_COUNT_THRESHOLD)
        )
        regenerate_on = config.get("regenerate_on", DEFAULT_REGENERATE_ON)
        self.regenerate_on = {str(trigger).strip().lower() for trigger in regenerate_on}

        self.db_manager = db_manager
        self.formation_id = formation_id
        self.knowledge_graph = knowledge_graph
        self.captains_log = captains_log
        self.artifact_memory = artifact_memory

        # user_id -> {"block", "fingerprint", "generated_at"}
        self._cache: Dict[str, Dict[str, Any]] = {}
        # user_id -> cached lint findings (backed by system_config).
        self._lint_findings: Dict[str, List[str]] = {}
        # Bumped by set_lint_findings/invalidate so the fingerprint check
        # picks up lint runs without a database read.
        self._lint_version: Dict[str, int] = {}

    @property
    def max_chars(self) -> int:
        """The rendered blob's hard character budget."""
        return self.max_tokens * CHARS_PER_TOKEN

    # ------------------------------------------------------------------
    # Read path (retrieval start)
    # ------------------------------------------------------------------

    async def get_index_block(self, user_id: Any) -> str:
        """
        Return the user's memory index blob for prompt injection.

        Serves the cached blob when the fingerprint says nothing indexed
        has changed; regenerates otherwise. Returns "" when disabled, when
        there is nothing to index, or on any error (failure-isolated).
        """
        if not self.enabled:
            return ""
        try:
            user_id = str(user_id)
            fingerprint = await self._fingerprint(user_id)
            cached = self._cache.get(user_id)
            if cached is not None and not self._needs_regeneration(cached, fingerprint):
                return cached["block"]
            return await self.regenerate(user_id, fingerprint=fingerprint)
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_INDEX_FAILED,
                level=observability.EventLevel.WARNING,
                data={"user_id": str(user_id), "error": str(e), "error_type": type(e).__name__},
                description=f"Knowledge index lookup failed: {e}",
            )
            return ""

    def invalidate(self, user_id: Any, reason: str = "manual") -> None:
        """Drop the cached blob so the next read regenerates."""
        user_id = str(user_id)
        self._cache.pop(user_id, None)
        self._lint_version[user_id] = self._lint_version.get(user_id, 0) + 1
        _ = reason  # recorded by callers' own events

    # ------------------------------------------------------------------
    # Regeneration
    # ------------------------------------------------------------------

    async def regenerate(self, user_id: Any, fingerprint: Optional[Dict[str, Any]] = None) -> str:
        """
        Rebuild the user's index blob, cache it, and persist it.

        Returns the rendered blob ("" when there is nothing to index).
        """
        user_id = str(user_id)
        if fingerprint is None:
            fingerprint = await self._fingerprint(user_id)

        entities: List[Dict[str, Any]] = []
        if self.knowledge_graph is not None and getattr(self.knowledge_graph, "enabled", False):
            entities = await self.knowledge_graph.storage.list_entities(
                user_id, limit=MAX_ENTITIES_FETCHED
            )

        log_stats = await self._log_stats(user_id)

        artifacts: List[Dict[str, Any]] = []
        if self.artifact_memory is not None and getattr(self.artifact_memory, "enabled", False):
            artifacts = await self.artifact_memory.list_artifacts(user_id)

        gaps = await self.get_lint_findings(user_id)

        block = self._render(
            entity_count=fingerprint["entities"],
            entities=entities,
            log_stats=log_stats,
            artifacts=artifacts,
            gaps=gaps,
        )

        self._cache[user_id] = {
            "block": block,
            "fingerprint": fingerprint,
            "generated_at": time.time(),
        }
        await self._persist_block(user_id, block)

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_INDEX_REGENERATED,
            level=observability.EventLevel.DEBUG,
            data={
                "user_id": user_id,
                "entities": fingerprint["entities"],
                "log_entries": fingerprint["log_entries"],
                "artifacts": fingerprint["artifacts"],
                "gaps": len(gaps),
                "chars": len(block),
            },
            description=f"Knowledge index regenerated ({len(block)} chars)",
        )
        return block

    def _needs_regeneration(self, cached: Dict[str, Any], fingerprint: Dict[str, Any]) -> bool:
        """Apply the configured regeneration triggers to the fingerprint."""
        if time.time() - cached["generated_at"] > STALE_AFTER_SECONDS:
            return True
        old = cached["fingerprint"]
        if REGENERATE_ON_LOG_ENTRY in self.regenerate_on and (
            old["log_entries"] != fingerprint["log_entries"]
            or old["log_updated"] != fingerprint["log_updated"]
        ):
            return True
        if (
            REGENERATE_ON_ARTIFACT_SAVE in self.regenerate_on
            and old["artifacts"] != fingerprint["artifacts"]
        ):
            return True
        if (
            REGENERATE_ON_ENTITY_THRESHOLD in self.regenerate_on
            and abs(old["entities"] - fingerprint["entities"]) >= self.entity_count_threshold
        ):
            return True
        if (
            REGENERATE_ON_LINT in self.regenerate_on
            and old["lint_version"] != fingerprint["lint_version"]
        ):
            return True
        return False

    async def _fingerprint(self, user_id: str) -> Dict[str, Any]:
        """Cheap change detector over everything the index catalogs."""
        entity_count = 0
        if self.knowledge_graph is not None and getattr(self.knowledge_graph, "enabled", False):
            async with self.db_manager.get_async_session() as session:
                stmt = (
                    select(func.count())
                    .select_from(KGEntity)
                    .filter_by(
                        user_id=user_id,
                        formation_id=self.formation_id,
                        status=STATUS_ACTIVE,
                    )
                )
                entity_count = int((await session.execute(stmt)).scalar() or 0)

        log_count = 0
        log_updated = None
        if self.captains_log is not None and getattr(self.captains_log, "enabled", False):
            async with self.db_manager.get_async_session() as session:
                stmt = (
                    select(func.count(), func.max(CaptainsLogEntry.updated_at))
                    .select_from(CaptainsLogEntry)
                    .where(
                        CaptainsLogEntry.user_id == user_id,
                        CaptainsLogEntry.formation_id == self.formation_id,
                    )
                )
                row = (await session.execute(stmt)).one()
                log_count = int(row[0] or 0)
                log_updated = row[1].isoformat() if row[1] else None

        artifact_count = 0
        if self.artifact_memory is not None and getattr(self.artifact_memory, "enabled", False):
            artifact_count = await self._artifact_count(user_id)

        return {
            "entities": entity_count,
            "log_entries": log_count,
            "log_updated": log_updated,
            "artifacts": artifact_count,
            "lint_version": self._lint_version.get(user_id, 0),
        }

    async def _artifact_count(self, user_id: str) -> int:
        """Count the user's live artifacts through the artifact service."""
        try:
            return len(await self.artifact_memory.list_artifacts(user_id))
        except Exception:
            return 0

    async def _log_stats(self, user_id: str) -> Dict[str, Any]:
        """Entry count, date span, and most recent summary for the log."""
        stats = {"count": 0, "first": None, "last": None, "recent_summary": None}
        if self.captains_log is None or not getattr(self.captains_log, "enabled", False):
            return stats
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(
                    func.count(),
                    func.min(CaptainsLogEntry.date),
                    func.max(CaptainsLogEntry.date),
                )
                .select_from(CaptainsLogEntry)
                .where(
                    CaptainsLogEntry.user_id == user_id,
                    CaptainsLogEntry.formation_id == self.formation_id,
                )
            )
            row = (await session.execute(stmt)).one()
            stats["count"] = int(row[0] or 0)
            stats["first"] = _iso_date(row[1])
            stats["last"] = _iso_date(row[2])
        if stats["count"]:
            entries = await self.captains_log.storage.list_entries(user_id, limit=1)
            if entries and entries[0].get("summary"):
                stats["recent_summary"] = entries[0]["summary"]
        return stats

    # ------------------------------------------------------------------
    # Rendering (size-capped)
    # ------------------------------------------------------------------

    def _render(
        self,
        entity_count: int,
        entities: List[Dict[str, Any]],
        log_stats: Dict[str, Any],
        artifacts: List[Dict[str, Any]],
        gaps: List[str],
    ) -> str:
        """Render the index blob within the max_tokens character budget."""
        if not entity_count and not log_stats["count"] and not artifacts and not gaps:
            return ""

        header = f"[Memory Index - as of {utc_now_naive().date().isoformat()}]"
        sections: List[str] = []

        if entity_count:
            names = [_entity_label(entity) for entity in entities]
            sections.append(
                _fit_listing(f"Entities ({entity_count}): ", names, entity_count, budget=None)
            )

        if log_stats["count"]:
            line = f"Captain's Log: {log_stats['count']} entries"
            if log_stats["first"] and log_stats["last"]:
                if log_stats["first"] == log_stats["last"]:
                    line += f" on {log_stats['last']}"
                else:
                    line += f" spanning {log_stats['first']} - {log_stats['last']}"
            if log_stats["recent_summary"]:
                line += f". Most recent: {_clip(log_stats['recent_summary'], 120)}"
            sections.append(line)

        if artifacts:
            labels = [_artifact_label(artifact) for artifact in artifacts]
            sections.append(
                _fit_listing(f"Artifacts ({len(artifacts)}): ", labels, len(artifacts), budget=None)
            )

        if gaps:
            shown = gaps[:MAX_GAPS_RENDERED]
            line = "Knowledge gaps flagged by last lint: " + "; ".join(
                _clip(gap, 100) for gap in shown
            )
            if len(gaps) > len(shown):
                line += f" [+{len(gaps) - len(shown)} more]"
            sections.append(line)

        # Assemble under the hard budget: sections that overflow get their
        # listings re-fit into the remaining space, never silently dropped
        # mid-item.
        budget = self.max_chars - len(header)
        rendered: List[str] = [header]
        for section in sections:
            available = budget - 2  # the joining blank costs "\n\n"
            if available <= 0:
                break
            if len(section) > available:
                section = _clip(section, available)
            rendered.append(section)
            budget -= len(section) + 2
        return "\n\n".join(rendered)

    # ------------------------------------------------------------------
    # Lint findings (Phase 5 write-back)
    # ------------------------------------------------------------------

    async def set_lint_findings(self, user_id: Any, findings: List[str]) -> None:
        """
        Store the latest lint findings and invalidate the cached index.

        Called by the Phase 5 lint job after each run so agents see the
        memory store's known weaknesses. Persisted in system_config
        (key ``memory_lint:{user_id}``) to survive restarts.
        """
        user_id = str(user_id)
        findings = [str(finding) for finding in findings]
        self._lint_findings[user_id] = findings
        await self._system_set(
            LINT_FINDINGS_KEY_FORMAT.format(user_id=user_id), json.dumps(findings)
        )
        self.invalidate(user_id, reason="lint")

    async def get_lint_findings(self, user_id: Any) -> List[str]:
        """Return the last lint run's findings for the user (may be [])."""
        user_id = str(user_id)
        cached = self._lint_findings.get(user_id)
        if cached is not None:
            return cached
        raw = await self._system_get(LINT_FINDINGS_KEY_FORMAT.format(user_id=user_id))
        findings: List[str] = []
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    findings = [str(finding) for finding in loaded]
            except (ValueError, TypeError):
                findings = []
        self._lint_findings[user_id] = findings
        return findings

    # ------------------------------------------------------------------
    # system_config persistence
    # ------------------------------------------------------------------

    async def _persist_block(self, user_id: str, block: str) -> None:
        """Write-through the rendered blob (best-effort, never raises)."""
        try:
            await self._system_set(INDEX_KEY_FORMAT.format(user_id=user_id), block)
        except Exception:
            pass

    async def _system_get(self, key: str) -> Optional[str]:
        async with self.db_manager.get_async_session() as session:
            row = await session.get(SystemConfig, key)
            return row.value if row else None

    async def _system_set(self, key: str, value: str) -> None:
        async with self.db_manager.get_async_session() as session:
            await session.merge(SystemConfig(key=key, value=value))
            await session.flush()


def _entity_label(entity: Dict[str, Any]) -> str:
    """Render one entity as ``Name (Type)`` for the index listing."""
    entity_type = (entity.get("type") or "").capitalize()
    return f"{entity['name']} ({entity_type})" if entity_type else entity["name"]


def _artifact_label(artifact: Dict[str, Any]) -> str:
    """Render one artifact as ``Name (type, date)`` for the index listing."""
    parts = []
    content_type = artifact.get("content_type")
    if content_type:
        parts.append(str(content_type).rsplit("/", 1)[-1])
    created = artifact.get("created_at")
    if created:
        parts.append(str(created)[:10])
    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"{artifact.get('name', '?')}{suffix}"


def _fit_listing(prefix: str, labels: List[str], total: int, budget: Optional[int]) -> str:
    """
    Render ``prefix + comma-joined labels`` with an omitted-items count.

    ``budget`` limits the rendered length (None applies a generous default
    that final assembly may clip further). Truncates on item boundaries
    with ``[+N more]``, per the PRD's truncation rule.
    """
    if budget is None:
        budget = 400
    shown: List[str] = []
    used = len(prefix)
    for label in labels:
        cost = len(label) + (2 if shown else 0)
        if used + cost > budget:
            break
        shown.append(label)
        used += cost
    omitted = total - len(shown)
    line = prefix + ", ".join(shown)
    if omitted > 0:
        line += f" [+{omitted} more]"
    return line


def _clip(text: str, limit: int) -> str:
    """Hard-clip text to ``limit`` chars with an ellipsis marker."""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."


def _iso_date(value) -> Optional[str]:
    """Normalize a DATE column value (date or ISO string) to ISO text."""
    if value is None:
        return None
    if isinstance(value, date_type):
        return value.isoformat()
    return str(value)[:10]
