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
            )
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

    async def list_artifacts(
        self,
        user_id: str,
        name: Optional[str] = None,
        latest_only: bool = True,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """List a user's artifacts, newest first."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(Artifact).filter_by(user_id=str(user_id), formation_id=self.formation_id)
            if name is not None:
                stmt = stmt.filter_by(name=name)
            if latest_only:
                stmt = stmt.filter_by(is_latest=True)
            if not include_deleted:
                stmt = stmt.filter(Artifact.deleted_at.is_(None))
            stmt = stmt.order_by(Artifact.id.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

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
