# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Artifact Memory Storage - Metadata Persistence and Versioning
# Description:  SQLAlchemy-backed storage for the artifacts table
# Role:         Version-chained inserts, reads, retention expiry marking
# Usage:        Used by ArtifactMemoryService
# Author:       Muxi Framework Team
#
# Backend-agnostic persistence layer for artifact metadata. The same ORM
# model and queries run on PostgreSQL and SQLite through the shared
# DatabaseManager async session factory. All rows are scoped by
# (user_id, formation_id) exactly like the other memory tables.
#
# Versioning (PRD 1.4): a capture whose name matches the user's current
# latest live artifact extends the version chain -- the previous head is
# demoted (is_latest = False) and the new row points back at it through
# ``parent_id`` with ``version = previous + 1``, all in one transaction.
# Previous versions' blobs are retained for history. Chain integrity is
# race-proof at two layers: the service serializes same-chain writers
# in-process, and the ``idx_artifacts_chain_head`` partial unique index
# backstops multi-process deployments (a lost race rolls back and the
# insert is retried once against the re-read head).
#
# Retention (PRD 1.5): ``expires_at`` is computed at capture time by the
# service; ``mark_expired`` soft-deletes every live row past its expiry --
# cascading through each retired row's ancestor versions so superseded
# history cannot outlive its chain head -- and returns the affected rows
# so the service can prune their blobs.
# =============================================================================

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ....utils.datetime_utils import utc_now_naive
from .models import Artifact, SystemConfig


class ArtifactMemoryStorage:
    """Persistence layer for artifact metadata rows."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize artifact storage bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier used to scope all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id

    # ------------------------------------------------------------------
    # system_config (formation instance identity)
    # ------------------------------------------------------------------

    async def get_or_create_system_value(self, key: str, default_factory) -> str:
        """
        Return the ``system_config`` value for ``key``, inserting the
        ``default_factory()`` result once when the key does not exist.

        The insert races safely: a concurrent first boot loses the
        IntegrityError race and re-reads the winner's value, so the
        formation instance id is generated exactly once.
        """
        async with self.db_manager.get_async_session() as session:
            row = await session.get(SystemConfig, key)
            if row is not None:
                return row.value
        value = str(default_factory())
        try:
            async with self.db_manager.get_async_session() as session:
                session.add(SystemConfig(key=key, value=value))
                await session.flush()
            return value
        except Exception:
            # Lost the first-boot race (or the insert failed transiently):
            # the value must already exist -- read it back.
            async with self.db_manager.get_async_session() as session:
                row = await session.get(SystemConfig, key)
                if row is not None:
                    return row.value
                raise

    # ------------------------------------------------------------------
    # Capture (version-chained insert)
    # ------------------------------------------------------------------

    async def save_artifact(
        self,
        user_id: str,
        public_id: str,
        name: str,
        content_type: str,
        summary: str,
        storage_ref: str,
        size_bytes: int,
        compressed_bytes: int,
        checksum_sha256: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        derived_from_event_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Insert one artifact row, extending the version chain on name match.

        The read-head/insert transaction can lose a chain-head race to
        another *process* (the service's per-chain lock already serializes
        in-process writers): both transactions read the same head, and the
        loser's insert violates ``idx_artifacts_chain_head``. On that
        IntegrityError the transaction is rolled back and re-run once
        against the re-read head; a second loss propagates to the
        failure-isolated capture path.

        ``created_at`` / ``derived_from_event_id`` are the replay path's
        stamps (artifact-metadata projector): a rebuilt row keeps its
        original capture time and its provenance bridge into the event log.

        Returns the inserted row as a dict (version/parent_id reflect the
        chain position).
        """
        fields = {
            "user_id": str(user_id),
            "public_id": public_id,
            "name": name,
            "content_type": content_type,
            "summary": summary,
            "storage_ref": storage_ref,
            "size_bytes": size_bytes,
            "compressed_bytes": compressed_bytes,
            "checksum_sha256": checksum_sha256,
            "category": category,
            "tags": tags,
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "expires_at": expires_at,
            "created_at": created_at,
            "derived_from_event_id": derived_from_event_id,
        }
        try:
            return await self._insert_version(**fields)
        except IntegrityError:
            return await self._insert_version(**fields)

    async def _insert_version(
        self,
        user_id: str,
        public_id: str,
        name: str,
        content_type: str,
        summary: str,
        storage_ref: str,
        size_bytes: int,
        compressed_bytes: int,
        checksum_sha256: str,
        category: Optional[str],
        tags: Optional[List[str]],
        agent_id: Optional[str],
        conversation_id: Optional[str],
        expires_at: Optional[datetime],
        created_at: Optional[datetime] = None,
        derived_from_event_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """One read-head -> demote -> insert transaction (see save_artifact)."""
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(Artifact)
                .filter_by(
                    user_id=user_id,
                    formation_id=self.formation_id,
                    name=name,
                    is_latest=True,
                )
                .filter(Artifact.deleted_at.is_(None))
                .order_by(Artifact.version.desc())
            )
            previous = (await session.execute(stmt)).scalars().first()

            version, parent_id = 1, None
            if previous is not None:
                previous.is_latest = False
                version = previous.version + 1
                parent_id = previous.id
                # The demotion must hit the database before the new head
                # is inserted or the chain-head unique index rejects the
                # insert; flush explicitly instead of relying on the unit
                # of work's statement ordering.
                await session.flush()

            artifact = Artifact(
                public_id=public_id,
                user_id=user_id,
                formation_id=self.formation_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                version=version,
                parent_id=parent_id,
                is_latest=True,
                name=name,
                content_type=content_type,
                category=category,
                summary=summary,
                tags=list(tags or []),
                storage_ref=storage_ref,
                size_bytes=size_bytes,
                compressed_bytes=compressed_bytes,
                checksum_sha256=checksum_sha256,
                expires_at=expires_at,
                derived_from_event_id=derived_from_event_id,
            )
            if created_at is not None:
                artifact.created_at = created_at
                artifact.updated_at = created_at
                artifact.last_accessed_at = created_at
            session.add(artifact)
            await session.flush()
            return artifact.to_dict()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_by_public_id(
        self, user_id: str, public_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Return one artifact by public id (user-scoped), or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(Artifact).filter_by(
                user_id=str(user_id), formation_id=self.formation_id, public_id=public_id
            )
            if not include_deleted:
                stmt = stmt.filter(Artifact.deleted_at.is_(None))
            artifact = (await session.execute(stmt)).scalars().first()
            return artifact.to_dict() if artifact else None

    async def get_latest_by_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Return the live chain head for one (user, name), or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(Artifact)
                .filter_by(
                    user_id=str(user_id),
                    formation_id=self.formation_id,
                    name=name,
                    is_latest=True,
                )
                .filter(Artifact.deleted_at.is_(None))
            )
            artifact = (await session.execute(stmt)).scalars().first()
            return artifact.to_dict() if artifact else None

    async def list_artifacts(
        self,
        user_id: str,
        name: Optional[str] = None,
        latest_only: bool = True,
        include_deleted: bool = False,
        limit: Optional[int] = None,
        order_by_last_accessed: bool = False,
    ) -> List[Dict[str, Any]]:
        """List a user's artifacts, newest first.

        ``order_by_last_accessed`` switches to the manifest ordering
        (PRD 2.1: ``last_accessed_at DESC``); ``limit`` caps the fetch so
        the manifest never pulls a user's entire artifact history.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = select(Artifact).filter_by(user_id=str(user_id), formation_id=self.formation_id)
            if name is not None:
                stmt = stmt.filter_by(name=name)
            if latest_only:
                stmt = stmt.filter_by(is_latest=True)
            if not include_deleted:
                stmt = stmt.filter(Artifact.deleted_at.is_(None))
            if order_by_last_accessed:
                stmt = stmt.order_by(Artifact.last_accessed_at.desc(), Artifact.id.desc())
            else:
                stmt = stmt.order_by(Artifact.id.desc())
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    async def count_artifacts(self, user_id: str, latest_only: bool = True) -> int:
        """Count a user's live artifacts without materializing the rows."""
        from sqlalchemy import func

        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(func.count())
                .select_from(Artifact)
                .where(
                    Artifact.user_id == str(user_id),
                    Artifact.formation_id == self.formation_id,
                    Artifact.deleted_at.is_(None),
                )
            )
            if latest_only:
                stmt = stmt.where(Artifact.is_latest.is_(True))
            return int((await session.execute(stmt)).scalar() or 0)

    async def get_version_chain(
        self, user_id: str, public_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Return the full version chain containing ``public_id``.

        Walks ancestors through ``parent_id`` and descendants through the
        reverse link, so any version's public id resolves the whole chain.
        Returned newest-version-first. Empty when the id is unknown for
        this user.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = select(Artifact).filter_by(
                user_id=str(user_id), formation_id=self.formation_id, public_id=public_id
            )
            if not include_deleted:
                stmt = stmt.filter(Artifact.deleted_at.is_(None))
            anchor = (await session.execute(stmt)).scalars().first()
            if anchor is None:
                return []

            chain: Dict[int, Dict[str, Any]] = {anchor.id: anchor.to_dict()}

            # Ancestors: follow parent_id links up to the chain root. The
            # user check is defensive -- chains never legitimately cross
            # users, but a stray link must not leak another user's rows.
            parent_id = anchor.parent_id
            while parent_id is not None and parent_id not in chain:
                parent = await session.get(Artifact, parent_id)
                if (
                    parent is None
                    or parent.user_id != str(user_id)
                    or parent.formation_id != self.formation_id
                    or (not include_deleted and parent.deleted_at is not None)
                ):
                    break
                chain[parent.id] = parent.to_dict()
                parent_id = parent.parent_id

            # Descendants: follow the reverse link down to the chain head,
            # scoped by user like every other chain query.
            current_id = anchor.id
            while True:
                stmt = select(Artifact).filter_by(
                    user_id=str(user_id),
                    formation_id=self.formation_id,
                    parent_id=current_id,
                )
                if not include_deleted:
                    stmt = stmt.filter(Artifact.deleted_at.is_(None))
                child = (await session.execute(stmt)).scalars().first()
                if child is None or child.id in chain:
                    break
                chain[child.id] = child.to_dict()
                current_id = child.id

            return sorted(chain.values(), key=lambda row: row["version"], reverse=True)

    async def touch_last_accessed(self, artifact_id: int, expires_at: Optional[datetime]) -> None:
        """
        Refresh ``last_accessed_at`` (and, for the last_accessed retention
        policy, ``expires_at``) after a content read.
        """
        async with self.db_manager.get_async_session() as session:
            artifact = await session.get(Artifact, artifact_id)
            if artifact is None:
                return
            artifact.last_accessed_at = utc_now_naive()
            if expires_at is not None:
                artifact.expires_at = expires_at
            await session.flush()

    # ------------------------------------------------------------------
    # Event substrate support (provenance stamping + rebuild)
    # ------------------------------------------------------------------

    async def set_derived_event(self, artifact_id: int, event_id: int) -> None:
        """Stamp a row's provenance bridge into the memory event log.

        Idempotent: an already-stamped row keeps its original event id
        (the first artifact.saved event is the row's origin; replays and
        backfills must not rewrite history).
        """
        async with self.db_manager.get_async_session() as session:
            artifact = await session.get(Artifact, artifact_id)
            if artifact is None or artifact.derived_from_event_id is not None:
                return
            artifact.derived_from_event_id = event_id
            await session.flush()

    async def delete_event_sourced_for_user(self, user_id: str) -> int:
        """
        Delete the user's event-sourced metadata rows (rebuild support).

        Only rows carrying a ``derived_from_event_id`` are removed --
        replaying artifact.saved events recreates exactly those. Blobs
        are never touched: they live in artifact storage and are not a
        projection. Pre-substrate rows (NULL provenance) survive so a
        rebuild can never orphan a blob's only metadata. Returns the
        number of rows deleted.
        """
        from sqlalchemy import delete as sql_delete

        async with self.db_manager.get_async_session() as session:
            stmt = (
                sql_delete(Artifact)
                .where(Artifact.user_id == str(user_id))
                .where(Artifact.formation_id == self.formation_id)
                .where(Artifact.derived_from_event_id.is_not(None))
            )
            result = await session.execute(stmt)
            return int(result.rowcount or 0)

    # ------------------------------------------------------------------
    # Retention (soft delete of expired rows)
    # ------------------------------------------------------------------

    async def mark_expired(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Soft-delete every live artifact past its expiry.

        The expiry cascades through version chains: when an expired row is
        retired, every live ancestor version (reached through ``parent_id``)
        is retired with it in the same pass. Ancestors are strictly older
        than their descendants and are invisible to latest-only listings,
        so once the row that superseded them ages out they serve no purpose
        -- without the cascade, non-latest versions whose ``expires_at`` is
        NULL would keep their blobs forever.

        Returns the affected rows (as dicts) so the caller can prune the
        corresponding blobs. Metadata rows are retained for audit.
        """
        now = now or utc_now_naive()
        expired: List[Dict[str, Any]] = []
        async with self.db_manager.get_async_session() as session:
            stmt = (
                select(Artifact)
                .filter_by(formation_id=self.formation_id)
                .filter(
                    Artifact.expires_at.is_not(None),
                    Artifact.expires_at < now,
                    Artifact.deleted_at.is_(None),
                )
            )
            to_retire = {
                artifact.id: artifact for artifact in (await session.execute(stmt)).scalars().all()
            }

            # Cascade: walk each expired row's ancestor chain and retire
            # every live version it supersedes.
            for artifact in list(to_retire.values()):
                parent_id = artifact.parent_id
                while parent_id is not None and parent_id not in to_retire:
                    parent = await session.get(Artifact, parent_id)
                    if parent is None or parent.deleted_at is not None:
                        break
                    to_retire[parent.id] = parent
                    parent_id = parent.parent_id

            for artifact in to_retire.values():
                artifact.deleted_at = now
                expired.append(artifact.to_dict())
            await session.flush()
        return expired
