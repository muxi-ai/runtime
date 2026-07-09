# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Graph Storage - Entity and Relationship Persistence
# Description:  SQLAlchemy-backed storage for the knowledge graph
# Role:         Upserts, contradiction detection, and edge iteration
# Usage:        Used by KnowledgeGraphService and graph algorithm backends
# Author:       Muxi Framework Team
#
# Backend-agnostic persistence layer (Memory Revamp Phase 1). The same ORM
# models and queries run on PostgreSQL and SQLite through the shared
# DatabaseManager async session factory. All rows are scoped by
# (user_id, formation_id) exactly like the flat-fact extractor output.
#
# Contradiction detection (PRD "Contradiction Detection"):
# - Duplicate fact (same subject, predicate, object): merge, keep max
#   confidence.
# - Conflicting fact on an exclusive predicate (same subject and predicate,
#   different object, e.g. lives_in London vs lives_in Berlin):
#   - new confidence exceeds old by more than SUPERSEDE_CONFIDENCE_DELTA:
#     old fact is marked superseded (retained, not deleted).
#   - otherwise both facts are marked conflicted and cross-referenced for
#     later resolution.
# =============================================================================

from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sql_delete, select

from ..events.models import append_event_id
from .models import (
    EXCLUSIVE_RELATIONSHIP_TYPES,
    STATUS_ACTIVE,
    STATUS_CONFLICTED,
    STATUS_MERGED,
    STATUS_SUPERSEDED,
    SUPERSEDE_CONFIDENCE_DELTA,
    KGEntity,
    KGRelationship,
)

# Bound on merge-chain hops followed by the upsert redirect (defensive;
# chains longer than this indicate corrupted bookkeeping).
MAX_MERGE_CHAIN_DEPTH = 10


class KnowledgeGraphStorage:
    """Persistence layer for knowledge graph entities and relationships."""

    def __init__(self, db_manager, formation_id: str):
        """
        Initialize graph storage bound to a formation.

        Args:
            db_manager: Shared DatabaseManager (PostgreSQL or SQLite).
            formation_id: Formation identifier used to scope all rows.
        """
        self.db_manager = db_manager
        self.formation_id = formation_id

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    async def upsert_entity(
        self,
        user_id: str,
        entity_type: str,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        event_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Insert or update an entity keyed by (user, formation, type, name).

        Existing entities merge the new attributes over the old ones and
        keep the highest confidence seen. When ``event_id`` is provided it
        is appended to the row's provenance list (idempotently).

        Sticky entity resolution: a name previously merged away by entity
        resolution redirects to its canonical entity (following the
        ``superseded_by`` merge chain), so re-mentions of the duplicate
        name enrich the canonical row instead of reviving the duplicate.

        Returns:
            Dict representation of the stored entity.
        """
        entity_type = normalize_type(entity_type)
        name = name.strip()
        user_id = str(user_id)

        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity).filter_by(
                user_id=user_id,
                formation_id=self.formation_id,
                type=entity_type,
                name=name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if existing is not None and existing.status == STATUS_MERGED:
                existing = await self._follow_merge_chain(session, existing)

            if existing is not None:
                merged = dict(existing.attributes or {})
                merged.update(attributes or {})
                existing.attributes = merged
                existing.confidence = max(existing.confidence or 0.0, confidence)
                existing.derived_from_event_ids = append_event_id(
                    existing.derived_from_event_ids, event_id
                )
                if existing.status == STATUS_SUPERSEDED:
                    # A fresh observation revives a previously superseded entity.
                    existing.status = STATUS_ACTIVE
                    existing.superseded_by = None
                await session.flush()
                return existing.to_dict()

            entity = KGEntity(
                user_id=user_id,
                formation_id=self.formation_id,
                type=entity_type,
                name=name,
                attributes=attributes or {},
                confidence=confidence,
                derived_from_event_ids=append_event_id([], event_id),
            )
            session.add(entity)
            await session.flush()
            return entity.to_dict()

    @staticmethod
    async def _follow_merge_chain(session, entity: KGEntity) -> KGEntity:
        """Resolve a merged entity to its canonical row (bounded chain).

        Returns the last resolvable row: the canonical entity in the
        normal case, or the input row itself when the chain is broken
        (defensive -- never returns None, so the caller's upsert can
        always merge into an existing row instead of violating the
        (user, formation, type, name) unique constraint).
        """
        current = entity
        for _ in range(MAX_MERGE_CHAIN_DEPTH):
            if current.status != STATUS_MERGED or current.superseded_by is None:
                return current
            target = await session.get(KGEntity, current.superseded_by)
            if target is None:
                return current
            current = target
        return current

    async def get_entity(
        self, user_id: str, entity_type: str, name: str
    ) -> Optional[Dict[str, Any]]:
        """Return the entity matching (user, type, name), or None."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity).filter_by(
                user_id=str(user_id),
                formation_id=self.formation_id,
                type=normalize_type(entity_type),
                name=name.strip(),
            )
            entity = (await session.execute(stmt)).scalar_one_or_none()
            return entity.to_dict() if entity else None

    async def get_entity_by_id(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """Return the entity with the given integer id, or None."""
        async with self.db_manager.get_async_session() as session:
            entity = await session.get(KGEntity, entity_id)
            return entity.to_dict() if entity else None

    async def get_entities_by_ids(self, entity_ids) -> List[Dict[str, Any]]:
        """Return the entities matching the given integer ids in one query.

        Batched lookup for hot paths (context blocks, path rendering) so
        callers never issue one round-trip per id.
        """
        ids = list(entity_ids)
        if not ids:
            return []
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity).filter(KGEntity.id.in_(ids))
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    async def list_entities(
        self,
        user_id: str,
        entity_type: Optional[str] = None,
        status: Optional[str] = STATUS_ACTIVE,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List entities for a user, newest first."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity).filter_by(user_id=str(user_id), formation_id=self.formation_id)
            if entity_type:
                stmt = stmt.filter_by(type=normalize_type(entity_type))
            if status:
                stmt = stmt.filter_by(status=status)
            stmt = stmt.order_by(KGEntity.id.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    async def iter_entity_ids(self, user_id: str) -> List[int]:
        """Return every active entity id in the user's subgraph.

        This is the canonical node source for graph algorithms that must
        see isolated entities (topological_sort): both backends order the
        same node set, fetched independently of the edge set, so entities
        without relationships cannot silently vanish on one backend.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGEntity.id).filter_by(
                user_id=str(user_id),
                formation_id=self.formation_id,
                status=STATUS_ACTIVE,
            )
            return [int(row[0]) for row in (await session.execute(stmt)).all()]

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    async def upsert_relationship(
        self,
        user_id: str,
        from_entity_id: int,
        to_entity_id: int,
        rel_type: str,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        event_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Insert or update a relationship with contradiction detection.

        Duplicate edges (same subject, predicate, object) are merged. On
        exclusive predicates a different object either supersedes the old
        fact (confidence delta above SUPERSEDE_CONFIDENCE_DELTA) or marks
        both facts conflicted. Old facts are retained, never deleted.
        When ``event_id`` is provided it is appended to the row's
        provenance list (idempotently).

        Returns:
            Dict representation of the stored relationship. When the
            write contradicted existing facts, the dict additionally
            carries a ``contradictions`` list (one entry per affected
            fact: detection kind + the public ids of both rows) so the
            caller can record fact.contradicted audit events -- the
            marking itself already happened in this transaction.
        """
        rel_type = normalize_type(rel_type)
        user_id = str(user_id)

        async with self.db_manager.get_async_session() as session:
            stmt = select(KGRelationship).filter_by(
                user_id=user_id,
                formation_id=self.formation_id,
                from_entity_id=from_entity_id,
                type=rel_type,
            )
            same_subject = (await session.execute(stmt)).scalars().all()

            # Duplicate fact: same subject, predicate, and object.
            for existing in same_subject:
                if existing.to_entity_id == to_entity_id:
                    merged = dict(existing.attributes or {})
                    merged.update(attributes or {})
                    existing.attributes = merged
                    existing.confidence = max(existing.confidence or 0.0, confidence)
                    existing.derived_from_event_ids = append_event_id(
                        existing.derived_from_event_ids, event_id
                    )
                    if existing.status == STATUS_SUPERSEDED:
                        existing.status = STATUS_ACTIVE
                        existing.superseded_by = None
                    await session.flush()
                    return existing.to_dict()

            relationship = KGRelationship(
                user_id=user_id,
                formation_id=self.formation_id,
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                type=rel_type,
                attributes=attributes or {},
                confidence=confidence,
                derived_from_event_ids=append_event_id([], event_id),
            )

            # Contradiction detection on exclusive predicates.
            if rel_type in EXCLUSIVE_RELATIONSHIP_TYPES:
                conflicting = [row for row in same_subject if row.status == STATUS_ACTIVE]
                for old in conflicting:
                    if confidence - (old.confidence or 0.0) > SUPERSEDE_CONFIDENCE_DELTA:
                        old.status = STATUS_SUPERSEDED
                    else:
                        old.status = STATUS_CONFLICTED
                        relationship.status = STATUS_CONFLICTED

                session.add(relationship)
                await session.flush()

                conflicted_ids = []
                contradictions = []
                for old in conflicting:
                    if old.status == STATUS_SUPERSEDED:
                        old.superseded_by = relationship.id
                        detection = "superseded"
                    else:
                        old.contradicted_by = relationship.id
                        conflicted_ids.append(old.id)
                        detection = "conflicted"
                    contradictions.append(
                        {
                            "relationship_type": rel_type,
                            "detection": detection,
                            "existing_relationship_public_id": old.public_id,
                            "new_relationship_public_id": relationship.public_id,
                        }
                    )
                if conflicted_ids:
                    # Deterministic back-link: point at the most recent
                    # conflicting fact rather than whichever row the loop
                    # happened to visit last.
                    relationship.contradicted_by = max(conflicted_ids)
                await session.flush()
                stored = relationship.to_dict()
                if contradictions:
                    stored["contradictions"] = contradictions
                return stored

            session.add(relationship)
            await session.flush()
            return relationship.to_dict()

    async def get_relationship_by_id(self, rel_id: int) -> Optional[Dict[str, Any]]:
        """Return the relationship with the given integer id, or None."""
        async with self.db_manager.get_async_session() as session:
            relationship = await session.get(KGRelationship, rel_id)
            return relationship.to_dict() if relationship else None

    async def list_relationships(
        self,
        user_id: str,
        rel_type: Optional[str] = None,
        from_entity_id: Optional[int] = None,
        to_entity_id: Optional[int] = None,
        status: Optional[str] = STATUS_ACTIVE,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """List relationships for a user, highest confidence first."""
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGRelationship).filter_by(
                user_id=str(user_id), formation_id=self.formation_id
            )
            if rel_type:
                stmt = stmt.filter_by(type=normalize_type(rel_type))
            if from_entity_id is not None:
                stmt = stmt.filter_by(from_entity_id=from_entity_id)
            if to_entity_id is not None:
                stmt = stmt.filter_by(to_entity_id=to_entity_id)
            if status:
                stmt = stmt.filter_by(status=status)
            stmt = stmt.order_by(KGRelationship.confidence.desc(), KGRelationship.id.desc())
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    async def iter_edges(
        self, user_id: str, rel_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Return the active edge set for a user's subgraph.

        This is the canonical edge source shared by both graph algorithm
        backends: NetworkX hydrates its DiGraph from it, and the pgRouting
        edge-source SQL mirrors its filters.
        """
        async with self.db_manager.get_async_session() as session:
            stmt = select(KGRelationship).filter_by(
                user_id=str(user_id),
                formation_id=self.formation_id,
                status=STATUS_ACTIVE,
            )
            if rel_types:
                stmt = stmt.filter(KGRelationship.type.in_([normalize_type(t) for t in rel_types]))
            rows = (await session.execute(stmt)).scalars().all()
            return [row.to_dict() for row in rows]

    # ------------------------------------------------------------------
    # Entity resolution (Memory Ingestion maturation)
    # ------------------------------------------------------------------

    async def merge_entities(
        self,
        user_id: str,
        canonical_id: int,
        duplicate_id: int,
        event_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Merge a duplicate identity into its canonical entity.

        Deterministic and idempotent: relationships are re-pointed from
        the duplicate to the canonical entity (an edge that would collide
        with an existing canonical edge, or become a self-loop, is marked
        superseded instead -- facts are retained, never deleted); the
        canonical row absorbs the duplicate's attributes (canonical values
        win on conflict), keeps the max confidence, and records the
        duplicate's name under ``attributes.aliases``. The duplicate row
        is marked ``merged`` with ``superseded_by`` -> canonical, which
        the upsert path treats as a redirect.

        Returns:
            {"repointed": n, "superseded": n} edge counts (both zero when
            either entity is missing or the merge already happened).
        """
        user_id = str(user_id)
        async with self.db_manager.get_async_session() as session:
            canonical = await session.get(KGEntity, canonical_id)
            duplicate = await session.get(KGEntity, duplicate_id)
            if (
                canonical is None
                or duplicate is None
                or canonical.id == duplicate.id
                or canonical.user_id != user_id
                or duplicate.user_id != user_id
                or duplicate.status == STATUS_MERGED
            ):
                return {"repointed": 0, "superseded": 0}

            # Existing canonical edge index for collision detection.
            stmt = select(KGRelationship).filter_by(user_id=user_id, formation_id=self.formation_id)
            edges = (await session.execute(stmt)).scalars().all()
            canonical_edges: Dict[tuple, KGRelationship] = {}
            duplicate_edges = []
            for edge in edges:
                touches_duplicate = duplicate.id in (edge.from_entity_id, edge.to_entity_id)
                if touches_duplicate:
                    duplicate_edges.append(edge)
                elif canonical.id in (edge.from_entity_id, edge.to_entity_id):
                    canonical_edges[(edge.from_entity_id, edge.to_entity_id, edge.type)] = edge

            repointed = superseded = 0
            for edge in duplicate_edges:
                new_from = (
                    canonical.id if edge.from_entity_id == duplicate.id else edge.from_entity_id
                )
                new_to = canonical.id if edge.to_entity_id == duplicate.id else edge.to_entity_id
                collision = canonical_edges.get((new_from, new_to, edge.type))
                if new_from == new_to:
                    # Would become a self-loop (e.g. duplicate -> canonical
                    # "knows" edge): retain as a superseded fact.
                    edge.status = STATUS_SUPERSEDED
                    edge.derived_from_event_ids = append_event_id(
                        edge.derived_from_event_ids, event_id
                    )
                    superseded += 1
                elif collision is not None:
                    collision.confidence = max(collision.confidence or 0.0, edge.confidence or 0.0)
                    merged_attrs = dict(edge.attributes or {})
                    merged_attrs.update(collision.attributes or {})
                    collision.attributes = merged_attrs
                    collision.derived_from_event_ids = append_event_id(
                        collision.derived_from_event_ids, event_id
                    )
                    edge.status = STATUS_SUPERSEDED
                    edge.superseded_by = collision.id
                    superseded += 1
                else:
                    edge.from_entity_id = new_from
                    edge.to_entity_id = new_to
                    edge.derived_from_event_ids = append_event_id(
                        edge.derived_from_event_ids, event_id
                    )
                    canonical_edges[(new_from, new_to, edge.type)] = edge
                    repointed += 1

            # Canonical absorbs the duplicate (canonical attributes win).
            merged_attrs = dict(duplicate.attributes or {})
            merged_attrs.update(canonical.attributes or {})
            aliases = set(merged_attrs.get("aliases") or [])
            aliases.update((duplicate.attributes or {}).get("aliases") or [])
            aliases.add(duplicate.name)
            aliases.discard(canonical.name)
            merged_attrs["aliases"] = sorted(aliases)
            canonical.attributes = merged_attrs
            canonical.confidence = max(canonical.confidence or 0.0, duplicate.confidence or 0.0)
            canonical.derived_from_event_ids = append_event_id(
                canonical.derived_from_event_ids, event_id
            )

            duplicate.status = STATUS_MERGED
            duplicate.superseded_by = canonical.id
            duplicate.derived_from_event_ids = append_event_id(
                duplicate.derived_from_event_ids, event_id
            )
            await session.flush()
            return {"repointed": repointed, "superseded": superseded}

    async def mark_possible_duplicate(
        self, entity_id: int, other_name: str, event_id: Optional[int] = None
    ) -> bool:
        """
        Stamp a below-threshold resolution match on an entity.

        The stored marker is ``attributes.possible_duplicates`` (a sorted,
        de-duplicated name list), so flagged pairs are reviewable without
        a schema change and re-application is idempotent.
        """
        async with self.db_manager.get_async_session() as session:
            entity = await session.get(KGEntity, entity_id)
            if entity is None:
                return False
            attributes = dict(entity.attributes or {})
            flagged = set(attributes.get("possible_duplicates") or [])
            if other_name in flagged:
                return False
            flagged.add(other_name)
            attributes["possible_duplicates"] = sorted(flagged)
            entity.attributes = attributes
            entity.derived_from_event_ids = append_event_id(entity.derived_from_event_ids, event_id)
            await session.flush()
            return True

    # ------------------------------------------------------------------
    # Rebuild support (Memory Event Substrate)
    # ------------------------------------------------------------------

    async def delete_all_for_user(self, user_id: str) -> Dict[str, int]:
        """
        Delete the user's entire subgraph (relationships first, then
        entities). Only the projection rebuild path may call this: the
        knowledge graph is derived state and is repopulated by replaying
        graph.extracted events.

        Returns:
            {"entities": n, "relationships": n} deleted counts.
        """
        user_id = str(user_id)
        async with self.db_manager.get_async_session() as session:
            rel_stmt = (
                sql_delete(KGRelationship)
                .where(KGRelationship.user_id == user_id)
                .where(KGRelationship.formation_id == self.formation_id)
            )
            relationships = int((await session.execute(rel_stmt)).rowcount or 0)
            entity_stmt = (
                sql_delete(KGEntity)
                .where(KGEntity.user_id == user_id)
                .where(KGEntity.formation_id == self.formation_id)
            )
            entities = int((await session.execute(entity_stmt)).rowcount or 0)
            return {"entities": entities, "relationships": relationships}


def normalize_type(value: str) -> str:
    """Normalize an entity/relationship type to the storage form."""
    return value.strip().lower().replace(" ", "_")[:50]
