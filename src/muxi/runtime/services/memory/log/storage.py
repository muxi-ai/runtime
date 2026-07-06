# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Captain's Log Storage - Entry, Source, and Lesson Persistence
# Description:  SQLAlchemy-backed storage for the narrative memory layer
# Role:         Entry upserts, source lineage (DAG), and lesson lifecycle
# Usage:        Used by CaptainsLogService
# Author:       Muxi Framework Team
#
# Memory Revamp Phase 2 (Captain's Log). Backend-agnostic persistence
# following the Phase 1 knowledge graph storage conventions: the same ORM
# models and queries run on PostgreSQL and SQLite through the shared
# DatabaseManager async session factory, with all rows scoped by
# (user_id, formation_id).
#
# Lineage rules (PRD "captains_log_sources"):
# - Duplicate sources for one entry are ignored (idempotent digest re-runs).
# - 'log_entry' sources form the derivation DAG between entries. Every
#   write of such an edge is validated against the existing DAG with the
#   shared lexicographic topological sort; an edge that would create a
#   cycle is rejected (processing-order validation for lineage writes).
#
# Lesson rules (PRD "Lessons Learned"):
# - Deduplicated by sha256(normalize(rule)) per (user, agent, formation);
#   a duplicate write is a confirmation: hits increments and confidence
#   is bumped by CONFIRMATION_CONFIDENCE_BUMP (capped at 1.0).
# - Decay subtracts confidence_decay_per_30d pro-rated by the days since
#   the last confirmation or decay pass; lessons falling below the archive
#   threshold are archived (soft-delete, kept for audit).
# =============================================================================

import hashlib
from datetime import date as date_type, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select

from ....utils.datetime_utils import utc_now_naive
from ..graph.algorithms import lexicographic_topological_sort
from .models import SOURCE_TYPE_LOG_ENTRY, SOURCE_TYPES, CaptainsLogEntry, CaptainsLogSource, Lesson

# Confidence added when an existing lesson is re-confirmed (duplicate write).
CONFIRMATION_CONFIDENCE_BUMP = 0.1

# Days per decay unit: confidence_decay_per_30d is expressed per this window.
DECAY_WINDOW_DAYS = 30.0


class CaptainsLogStorage:
    """Persistence layer for captain's log entries and source lineage."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize log storage bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier used to scope all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------

    async def upsert_entry(
        self,
        user_id: str,
        entry_date: date_type,
        summary: Optional[str] = None,
        decisions: Optional[List[str]] = None,
        projects: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Insert or update the entry keyed by (user, formation, date).

        The caller passes the full merged section content (the digest
        prompt already folds the previous entry in), so an update
        replaces the stored sections rather than appending.

        Returns:
            Dict representation of the stored entry.
        """
        user_id = str(user_id)
        async with self.db_manager.get_async_session() as session:
            stmt = select(CaptainsLogEntry).filter_by(
                user_id=user_id, formation_id=self.formation_id, date=entry_date
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                existing.summary = summary
                existing.decisions = decisions or []
                existing.projects = projects or []
                existing.context = context
                await session.flush()
                return existing.to_dict()

            entry = CaptainsLogEntry(
                user_id=user_id,
                formation_id=self.formation_id,
                date=entry_date,
                summary=summary,
                decisions=decisions or [],
                projects=projects or [],
                context=context,
            )
            session.add(entry)
            await session.flush()
            return entry.to_dict()

    async def get_entry(self, user_id: str, entry_date: date_type) -> Optional[Dict[str, Any]]:
        """Return the entry for (user, date), or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(CaptainsLogEntry).filter_by(
                user_id=str(user_id), formation_id=self.formation_id, date=entry_date
            )
            entry = (await session.execute(stmt)).scalar_one_or_none()
            return entry.to_dict() if entry else None

    async def get_entry_by_public_id(
        self, user_id: str, public_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return the entry with the given public id for this user, or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(CaptainsLogEntry).filter_by(
                user_id=str(user_id), formation_id=self.formation_id, public_id=public_id
            )
            entry = (await session.execute(stmt)).scalar_one_or_none()
            return entry.to_dict() if entry else None

    async def list_entries(
        self,
        user_id: str,
        limit: int = 10,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
    ) -> List[Dict[str, Any]]:
        """List entries for a user, newest date first."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(CaptainsLogEntry).filter_by(
                user_id=str(user_id), formation_id=self.formation_id
            )
            if date_from is not None:
                stmt = stmt.filter(CaptainsLogEntry.date >= date_from)
            if date_to is not None:
                stmt = stmt.filter(CaptainsLogEntry.date <= date_to)
            stmt = stmt.order_by(CaptainsLogEntry.date.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    # ------------------------------------------------------------------
    # Source lineage (evidence trail + derivation DAG)
    # ------------------------------------------------------------------

    async def add_sources(
        self, user_id: str, log_id: int, sources: List[Dict[str, str]]
    ) -> Dict[str, int]:
        """
        Attach source lineage rows to an entry.

        Duplicate (log, type, id) rows are skipped so digest re-runs are
        idempotent. 'log_entry' sources are validated against the user's
        existing derivation DAG; an edge that would create a cycle is
        rejected and counted, never written.

        Returns:
            {"added": n, "skipped": n, "rejected": n}
        """
        user_id = str(user_id)
        counts = {"added": 0, "skipped": 0, "rejected": 0}
        dag_edges: Optional[List[Tuple[int, int]]] = None

        async with self.db_manager.get_async_session() as session:
            for source in sources:
                source_type = str(source.get("source_type", "")).strip()
                source_id = str(source.get("source_id", "")).strip()
                if source_type not in SOURCE_TYPES or not source_id:
                    counts["rejected"] += 1
                    continue

                stmt = select(CaptainsLogSource).filter_by(
                    log_id=log_id, source_type=source_type, source_id=source_id
                )
                if (await session.execute(stmt)).scalar_one_or_none() is not None:
                    counts["skipped"] += 1
                    continue

                if source_type == SOURCE_TYPE_LOG_ENTRY:
                    if dag_edges is None:
                        dag_edges = await self.iter_log_edges(user_id)
                    candidate = dag_edges + [(int(source_id), log_id)]
                    if not lexicographic_topological_sort((), candidate):
                        counts["rejected"] += 1
                        continue
                    dag_edges = candidate

                session.add(
                    CaptainsLogSource(log_id=log_id, source_type=source_type, source_id=source_id)
                )
                await session.flush()
                counts["added"] += 1
        return counts

    async def get_sources(self, log_id: int) -> List[Dict[str, Any]]:
        """Return the source lineage rows for one entry, oldest first."""
        grouped = await self.get_sources_for_logs([log_id])
        return grouped.get(log_id, [])

    async def get_sources_for_logs(self, log_ids) -> Dict[int, List[Dict[str, Any]]]:
        """Return source lineage rows for many entries in one query.

        Batched lookup for the history path so callers never issue one
        round-trip per entry. Rows are grouped by log_id, oldest first;
        entries without sources are absent from the result.
        """
        ids = list(log_ids)
        if not ids:
            return {}
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(CaptainsLogSource)
                .filter(CaptainsLogSource.log_id.in_(ids))
                .order_by(CaptainsLogSource.id.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(row.log_id, []).append(row.to_dict())
            return grouped

    async def iter_log_edges(self, user_id: str) -> List[Tuple[int, int]]:
        """
        Return the user's log derivation DAG as (source_log_id, log_id) edges.

        This is the edge provider for GraphAlgorithms.topological_sort on
        the "captains_log_sources" DAG: a source entry precedes the entry
        derived from it.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(CaptainsLogSource.source_id, CaptainsLogSource.log_id)
                .join(CaptainsLogEntry, CaptainsLogEntry.id == CaptainsLogSource.log_id)
                .filter(
                    CaptainsLogEntry.user_id == str(user_id),
                    CaptainsLogEntry.formation_id == self.formation_id,
                    CaptainsLogSource.source_type == SOURCE_TYPE_LOG_ENTRY,
                )
            )
            rows = (await session.execute(stmt)).all()
            edges: List[Tuple[int, int]] = []
            for source_id, log_id in rows:
                try:
                    edges.append((int(source_id), int(log_id)))
                except (TypeError, ValueError):
                    continue  # malformed source_id: not part of the DAG
            return edges


class LessonStorage:
    """Persistence layer for the lessons self-improvement loop."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize lesson storage bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier used to scope all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id

    async def upsert_lesson(
        self,
        user_id: str,
        agent_id: str,
        rule: str,
        context: Optional[str] = None,
        confidence: float = 0.5,
        source_log_id: Optional[int] = None,
        hits: int = 1,
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Insert a lesson or confirm an existing one.

        Dedup key is sha256(normalize(rule)) per (user, agent, formation).
        On conflict the write is a confirmation: hits increments, confidence
        is bumped, and a previously archived lesson is revived.

        Returns:
            (lesson dict, created) where created is False on confirmation.
        """
        user_id = str(user_id)
        agent_id = str(agent_id)
        rule = rule.strip()
        digest = rule_hash(rule)

        async with self.db_manager.get_async_session() as session:
            stmt = select(Lesson).filter_by(
                user_id=user_id,
                agent_id=agent_id,
                formation_id=self.formation_id,
                rule_hash=digest,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                existing.hits = (existing.hits or 1) + 1
                existing.confidence = min(
                    1.0,
                    max(existing.confidence or 0.0, confidence) + CONFIRMATION_CONFIDENCE_BUMP,
                )
                if context:
                    existing.context = context
                if source_log_id is not None:
                    existing.source_log_id = source_log_id
                if existing.archived:
                    existing.archived = False  # re-confirmation revives it
                await session.flush()
                return existing.to_dict(), False

            lesson = Lesson(
                user_id=user_id,
                agent_id=agent_id,
                formation_id=self.formation_id,
                rule=rule,
                context=context,
                rule_hash=digest,
                source_log_id=source_log_id,
                confidence=confidence,
                hits=hits,
            )
            session.add(lesson)
            await session.flush()
            return lesson.to_dict(), True

    async def list_active(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List active lessons, highest confidence first (id breaks ties)."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(Lesson).filter_by(
                user_id=str(user_id), formation_id=self.formation_id, archived=False
            )
            if agent_id is not None:
                stmt = stmt.filter_by(agent_id=str(agent_id))
            stmt = stmt.order_by(Lesson.confidence.desc(), Lesson.id.asc())
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    async def mark_applied(self, lesson_ids: List[int], now: Optional[datetime] = None) -> None:
        """Record that the given lessons were injected into a prompt."""
        if not lesson_ids:
            return
        now = now or utc_now_naive()
        async with self.db_manager.get_async_session() as session:
            stmt = select(Lesson).filter(Lesson.id.in_(lesson_ids))
            for lesson in (await session.execute(stmt)).scalars().all():
                lesson.last_applied_at = now
            await session.flush()

    async def archive_lessons(self, lesson_ids: List[int]) -> int:
        """Archive the given lessons (soft-delete); returns count archived."""
        if not lesson_ids:
            return 0
        archived = 0
        async with self.db_manager.get_async_session() as session:
            stmt = select(Lesson).filter(Lesson.id.in_(lesson_ids), Lesson.archived.is_(False))
            for lesson in (await session.execute(stmt)).scalars().all():
                lesson.archived = True
                archived += 1
            await session.flush()
        return archived

    async def run_decay(
        self,
        decay_per_30d: float,
        archive_threshold: float,
        now: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """
        Apply time-based confidence decay across all active lessons.

        Decay is pro-rated: decay_per_30d * (days since the last
        confirmation or decay pass) / 30, applied only once at least a
        full day has elapsed so hourly loops don't churn rows. Lessons
        whose confidence drops below archive_threshold are archived.

        Returns:
            {"decayed": n, "archived": n}
        """
        now = now or utc_now_naive()
        counts = {"decayed": 0, "archived": 0}
        if decay_per_30d <= 0:
            return counts

        async with self.db_manager.get_async_session() as session:
            stmt = select(Lesson).filter_by(formation_id=self.formation_id, archived=False)
            for lesson in (await session.execute(stmt)).scalars().all():
                anchor = lesson.decayed_at or lesson.updated_at or lesson.created_at
                if anchor is None:
                    continue
                elapsed_days = (now - anchor).total_seconds() / 86400.0
                if elapsed_days < 1.0:
                    continue
                decay = decay_per_30d * (elapsed_days / DECAY_WINDOW_DAYS)
                lesson.confidence = max(0.0, (lesson.confidence or 0.0) - decay)
                lesson.decayed_at = now
                counts["decayed"] += 1
                if lesson.confidence < archive_threshold:
                    lesson.archived = True
                    counts["archived"] += 1
            await session.flush()
        return counts

    async def scopes_over_cap(self, cap: int) -> List[Tuple[str, str, int]]:
        """Return (user_id, agent_id, active_count) tuples exceeding the cap."""
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(Lesson.user_id, Lesson.agent_id, func.count(Lesson.id))
                .filter_by(formation_id=self.formation_id, archived=False)
                .group_by(Lesson.user_id, Lesson.agent_id)
                .having(func.count(Lesson.id) > cap)
            )
            rows = (await session.execute(stmt)).all()
            return [(row[0], row[1], int(row[2])) for row in rows]


def normalize_rule(rule: str) -> str:
    """Normalize a rule for hashing: lowercase, collapsed whitespace."""
    return " ".join(rule.strip().lower().split())


def rule_hash(rule: str) -> str:
    """Return the hex sha256 of the normalized rule text."""
    return hashlib.sha256(normalize_rule(rule).encode("utf-8")).hexdigest()
