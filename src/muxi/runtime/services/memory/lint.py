# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memory Lint - Background Knowledge Store Audit
# Description:  Detects conflicts/gaps/staleness and cleans up graph debris
# Role:         Formation-level background job (weekly + on-demand)
# Usage:        Created in formation initialization, started by the Overlord
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 5 (Lint Operation). A background audit job (weekly by
# default, or on demand via ``run_lint``, surfaced at
# ``POST /memory/lint``) that walks every user's memory store and produces
# a health report:
#
# | Check                                             | Action              |
# |---------------------------------------------------|---------------------|
# | Conflicted facts unresolved after N days          | Surface as finding  |
# | Superseded facts older than the retention window  | Hard-delete         |
# | Orphaned relationships (endpoint entity deleted)  | Auto-remove         |
# | Captain's log gaps (> 7 days between entries)     | Flag as gap         |
# | Artifacts not accessed in > stale_artifact_days   | Flag for review     |
# | Knowledge index staleness                          | Regenerate per run  |
#
# Findings are written back into the Phase 4 knowledge index
# (``set_lint_findings``) as "knowledge gaps flagged by last lint" so agents
# are aware of the memory store's known weaknesses.
#
# Lifecycle follows the shared background-loop pattern (Phase 1 convention):
# started by the Overlord beside the scheduler, cancelled on shutdown, and
# failure-isolated -- a lint failure is logged and the loop keeps running.
#
# Inert when unconfigured: the formation only constructs this service when
# the ``memory.lint`` block is present (pinned by unit test).
# =============================================================================

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import delete, select

from ...utils.datetime_utils import utc_now_naive
from .. import observability
from .graph.models import STATUS_CONFLICTED, STATUS_SUPERSEDED, KGEntity, KGRelationship
from .log.models import CaptainsLogEntry

# PRD defaults (Configuration Reference -> memory.lint).
DEFAULT_SCHEDULE = "weekly"
DEFAULT_CONFLICT_RESOLUTION_DAYS = 7
DEFAULT_ORPHAN_CLEANUP = True
DEFAULT_STALE_ARTIFACT_DAYS = 90

# Retention window for superseded facts before hard deletion. Superseded
# rows are kept (not deleted) at write time so the graph retains what was
# believed and when it changed; lint reclaims them once they age out.
DEFAULT_SUPERSEDED_RETENTION_DAYS = 30

# PRD: "Captain's log gaps (> 7 days with no entry despite activity)".
LOG_GAP_DAYS = 7

_SCHEDULE_SECONDS = {"daily": 86400, "weekly": 604800}


def _schedule_to_seconds(schedule: Any) -> float:
    """Convert a lint schedule config value to seconds."""
    if isinstance(schedule, (int, float)) and not isinstance(schedule, bool) and schedule > 0:
        return float(schedule)
    if isinstance(schedule, str):
        seconds = _SCHEDULE_SECONDS.get(schedule.strip().lower())
        if seconds is not None:
            return float(seconds)
    return float(_SCHEDULE_SECONDS[DEFAULT_SCHEDULE])


class MemoryLintService:
    """Audits the knowledge store and feeds findings to the knowledge index."""

    def __init__(
        self,
        db_manager,
        formation_id: str,
        config: Optional[Dict[str, Any]] = None,
        knowledge_graph=None,
        captains_log=None,
        artifact_memory=None,
        index=None,
    ):
        """
        Initialize the lint service.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier scoping all rows.
            config: The ``memory.lint`` formation config section.
            knowledge_graph: Phase 1 KnowledgeGraphService (or None).
            captains_log: Phase 2 CaptainsLogService (or None).
            artifact_memory: ArtifactMemoryService (or None).
            index: Phase 4 KnowledgeIndexService (or None) receiving the
                findings write-back and forced regeneration.
        """
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.interval_seconds = _schedule_to_seconds(config.get("schedule", DEFAULT_SCHEDULE))
        self.conflict_resolution_days = int(
            config.get("conflict_resolution_days", DEFAULT_CONFLICT_RESOLUTION_DAYS)
        )
        self.orphan_cleanup = bool(config.get("orphan_cleanup", DEFAULT_ORPHAN_CLEANUP))
        self.stale_artifact_days = int(
            config.get("stale_artifact_days", DEFAULT_STALE_ARTIFACT_DAYS)
        )
        self.superseded_retention_days = int(
            config.get("superseded_retention_days", DEFAULT_SUPERSEDED_RETENTION_DAYS)
        )

        self.db_manager = db_manager
        self.formation_id = formation_id
        self.knowledge_graph = knowledge_graph
        self.captains_log = captains_log
        self.artifact_memory = artifact_memory
        self.index = index

        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Background loop (shared lifecycle pattern)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic lint background loop."""
        if not self.enabled:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background loop, if running."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        """Sleep-run loop for the periodic audit."""
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await self.run_lint()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LINT_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"error": str(e), "error_type": type(e).__name__, "pass": "loop"},
                    description=f"Memory lint run failed: {e}",
                )

    # ------------------------------------------------------------------
    # The audit (weekly loop + on-demand entry point)
    # ------------------------------------------------------------------

    async def run_lint(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Audit the knowledge store; returns the aggregate health report.

        Args:
            user_id: Limit the audit to one user (the on-demand path);
                None audits every user with memory rows.
        """
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LINT_STARTED,
            level=observability.EventLevel.DEBUG,
            data={"user_id": user_id, "scope": "user" if user_id else "all"},
            description="Memory lint run started",
        )
        report: Dict[str, Any] = {
            "users": 0,
            "unresolved_conflicts": 0,
            "superseded_deleted": 0,
            "orphans_removed": 0,
            "log_gaps": 0,
            "stale_artifacts": 0,
            "index_regenerated": 0,
            "findings": {},
        }
        users = [str(user_id)] if user_id else sorted(await self._list_user_ids())
        for uid in users:
            try:
                user_report = await self._lint_user(uid)
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LINT_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"user_id": uid, "error": str(e), "error_type": type(e).__name__},
                    description=f"Memory lint failed for user {uid}: {e}",
                )
                continue
            report["users"] += 1
            for key in (
                "unresolved_conflicts",
                "superseded_deleted",
                "orphans_removed",
                "log_gaps",
                "stale_artifacts",
                "index_regenerated",
            ):
                report[key] += user_report[key]
            if user_report["findings"]:
                report["findings"][uid] = user_report["findings"]

        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_LINT_COMPLETED,
            level=observability.EventLevel.DEBUG,
            data={key: value for key, value in report.items() if key != "findings"},
            description=(
                f"Memory lint completed for {report['users']} user(s): "
                f"{report['unresolved_conflicts']} unresolved conflict(s), "
                f"{report['orphans_removed']} orphan(s) removed"
            ),
        )
        return report

    async def _lint_user(self, user_id: str) -> Dict[str, Any]:
        """Run every check for one user and write findings to the index."""
        findings: List[str] = []
        report = {
            "unresolved_conflicts": 0,
            "superseded_deleted": 0,
            "orphans_removed": 0,
            "log_gaps": 0,
            "stale_artifacts": 0,
            "index_regenerated": 0,
            "findings": findings,
        }

        graph_active = self.knowledge_graph is not None and getattr(
            self.knowledge_graph, "enabled", False
        )
        if graph_active:
            conflicts = await self._unresolved_conflicts(user_id)
            report["unresolved_conflicts"] = len(conflicts)
            findings.extend(conflicts)

            report["superseded_deleted"] = await self._purge_superseded(user_id)

            if self.orphan_cleanup:
                report["orphans_removed"] = await self._remove_orphan_relationships(user_id)

            if report["superseded_deleted"] or report["orphans_removed"]:
                self.knowledge_graph.algorithms.invalidate(user_id)

        gaps = await self._log_gaps(user_id)
        report["log_gaps"] = len(gaps)
        findings.extend(gaps)

        stale = await self._stale_artifacts(user_id)
        report["stale_artifacts"] = len(stale)
        findings.extend(stale)

        if self.index is not None and getattr(self.index, "enabled", False):
            await self.index.set_lint_findings(user_id, findings)
            # set_lint_findings just invalidated the cached blob, so
            # regenerate unconditionally: lint runs weekly, regeneration is
            # a handful of indexed queries (no LLM work), and rebuilding on
            # every run satisfies the PRD's "index stale > 24h -> force
            # regeneration" check by construction.
            await self.index.regenerate(user_id)
            report["index_regenerated"] = 1

        return report

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    async def _list_user_ids(self) -> Set[str]:
        """Every user with knowledge graph or captain's log rows."""
        from .log.formation import FORMATION_LOG_USER_ID

        users: Set[str] = set()
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity.user_id).filter_by(formation_id=self.formation_id).distinct()
            users.update(str(row[0]) for row in (await session.execute(stmt)).all())
            stmt = (
                select(CaptainsLogEntry.user_id)
                .filter_by(formation_id=self.formation_id)
                .distinct()
            )
            users.update(str(row[0]) for row in (await session.execute(stmt)).all())
        # The formation-scope log sentinel is not a user: its cadence is
        # the tuning interval, so the per-user log-gap check would flag it
        # spuriously (and per-user lint passes have nothing to audit).
        users.discard(FORMATION_LOG_USER_ID)
        return users

    async def _unresolved_conflicts(self, user_id: str) -> List[str]:
        """Conflicted facts that have sat unresolved past the threshold."""
        cutoff = utc_now_naive() - timedelta(days=self.conflict_resolution_days)
        findings: List[str] = []
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity).filter_by(
                user_id=user_id, formation_id=self.formation_id, status=STATUS_CONFLICTED
            )
            for entity in (await session.execute(stmt)).scalars().all():
                if (entity.updated_at or entity.created_at) <= cutoff:
                    findings.append(
                        f"unresolved conflict on entity '{entity.name}' "
                        f"(since {(entity.updated_at or entity.created_at).date().isoformat()})"
                    )
            stmt = select(KGRelationship).filter_by(
                user_id=user_id, formation_id=self.formation_id, status=STATUS_CONFLICTED
            )
            relationships = (await session.execute(stmt)).scalars().all()
            entity_ids = {r.from_entity_id for r in relationships} | {
                r.to_entity_id for r in relationships
            }
            names: Dict[int, str] = {}
            if entity_ids:
                stmt = select(KGEntity.id, KGEntity.name).filter(KGEntity.id.in_(entity_ids))
                names = {row[0]: row[1] for row in (await session.execute(stmt)).all()}
            for relationship in relationships:
                if (relationship.updated_at or relationship.created_at) <= cutoff:
                    findings.append(
                        "unresolved conflict: "
                        f"{names.get(relationship.from_entity_id, '?')} "
                        f"-[{relationship.type}]-> "
                        f"{names.get(relationship.to_entity_id, '?')}"
                    )
        return findings

    async def _purge_superseded(self, user_id: str) -> int:
        """Hard-delete superseded facts older than the retention window.

        Uses column-only selects plus bulk DELETEs (never ORM instance
        deletes): a superseded relationship whose endpoint entity is also
        superseded would otherwise be deleted twice -- once by the edge
        cleanup for the purged entity and once by the ORM unit of work --
        making the flush raise StaleDataError.
        """
        cutoff = utc_now_naive() - timedelta(days=self.superseded_retention_days)
        deleted = 0
        async with self.db_manager.get_async_session() as session:
            # Superseded relationships past retention (ids only).
            stmt = select(
                KGRelationship.id, KGRelationship.updated_at, KGRelationship.created_at
            ).filter_by(user_id=user_id, formation_id=self.formation_id, status=STATUS_SUPERSEDED)
            old_rel_ids = [
                row[0]
                for row in (await session.execute(stmt)).all()
                if (row[1] or row[2]) <= cutoff
            ]
            if old_rel_ids:
                await session.execute(
                    delete(KGRelationship).where(KGRelationship.id.in_(old_rel_ids))
                )
                deleted += len(old_rel_ids)

            # Superseded entities past retention (ids only).
            stmt = select(KGEntity.id, KGEntity.updated_at, KGEntity.created_at).filter_by(
                user_id=user_id, formation_id=self.formation_id, status=STATUS_SUPERSEDED
            )
            old_entity_ids = [
                row[0]
                for row in (await session.execute(stmt)).all()
                if (row[1] or row[2]) <= cutoff
            ]
            if old_entity_ids:
                # Remove every edge referencing a purged entity before the
                # entity rows so the FK never dangles mid-transaction
                # (cascade cleanup, not counted as superseded deletions).
                await session.execute(
                    delete(KGRelationship).where(
                        KGRelationship.from_entity_id.in_(old_entity_ids)
                        | KGRelationship.to_entity_id.in_(old_entity_ids)
                    )
                )
                await session.execute(delete(KGEntity).where(KGEntity.id.in_(old_entity_ids)))
                deleted += len(old_entity_ids)
            await session.flush()
        return deleted

    async def _remove_orphan_relationships(self, user_id: str) -> int:
        """Delete relationships whose endpoints no longer exist."""
        removed = 0
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity.id).filter_by(user_id=user_id, formation_id=self.formation_id)
            entity_ids = {int(row[0]) for row in (await session.execute(stmt)).all()}
            stmt = select(KGRelationship).filter_by(user_id=user_id, formation_id=self.formation_id)
            for relationship in (await session.execute(stmt)).scalars().all():
                if (
                    relationship.from_entity_id not in entity_ids
                    or relationship.to_entity_id not in entity_ids
                ):
                    await session.delete(relationship)
                    removed += 1
            await session.flush()
        return removed

    async def _log_gaps(self, user_id: str) -> List[str]:
        """Gaps of more than LOG_GAP_DAYS between consecutive log entries."""
        if self.captains_log is None or not getattr(self.captains_log, "enabled", False):
            return []
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(CaptainsLogEntry.date)
                .filter_by(user_id=user_id, formation_id=self.formation_id)
                .order_by(CaptainsLogEntry.date.asc())
            )
            dates = [row[0] for row in (await session.execute(stmt)).all()]
        findings = []
        for previous, current in zip(dates, dates[1:]):
            gap_days = (current - previous).days
            if gap_days > LOG_GAP_DAYS:
                findings.append(
                    f"captain's log gap: {gap_days} days between "
                    f"{previous.isoformat()} and {current.isoformat()}"
                )
        return findings

    async def _stale_artifacts(self, user_id: str) -> List[str]:
        """Artifacts not accessed within stale_artifact_days."""
        if self.artifact_memory is None or not getattr(self.artifact_memory, "enabled", False):
            return []
        cutoff = utc_now_naive() - timedelta(days=self.stale_artifact_days)
        findings = []
        for artifact in await self.artifact_memory.list_artifacts(user_id):
            last_accessed = artifact.get("last_accessed_at")
            if not last_accessed:
                continue
            try:
                # Normalize tz-aware stamps to naive: the runtime stores
                # naive UTC, but external artifact rows may carry offsets;
                # comparing aware vs naive raises TypeError, and an
                # unparseable stamp raises ValueError -- either would
                # otherwise abort the whole user's lint pass.
                accessed_at = datetime.fromisoformat(str(last_accessed)).replace(tzinfo=None)
            except (ValueError, TypeError):
                continue
            if accessed_at <= cutoff:
                findings.append(
                    f"stale artifact '{artifact.get('name', '?')}' "
                    f"(last accessed {str(last_accessed)[:10]})"
                )
        return findings
