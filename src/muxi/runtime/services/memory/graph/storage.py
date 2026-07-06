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

from sqlalchemy import select

from .models import (
    EXCLUSIVE_RELATIONSHIP_TYPES,
    STATUS_ACTIVE,
    STATUS_CONFLICTED,
    STATUS_SUPERSEDED,
    SUPERSEDE_CONFIDENCE_DELTA,
    KGEntity,
    KGRelationship,
)


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
    ) -> Dict[str, Any]:
        """
        Insert or update an entity keyed by (user, formation, type, name).

        Existing entities merge the new attributes over the old ones and
        keep the highest confidence seen.

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

            if existing is not None:
                merged = dict(existing.attributes or {})
                merged.update(attributes or {})
                existing.attributes = merged
                existing.confidence = max(existing.confidence or 0.0, confidence)
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
            )
            session.add(entity)
            await session.flush()
            return entity.to_dict()

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
    ) -> Dict[str, Any]:
        """
        Insert or update a relationship with contradiction detection.

        Duplicate edges (same subject, predicate, object) are merged. On
        exclusive predicates a different object either supersedes the old
        fact (confidence delta above SUPERSEDE_CONFIDENCE_DELTA) or marks
        both facts conflicted. Old facts are retained, never deleted.

        Returns:
            Dict representation of the stored relationship.
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

                for old in conflicting:
                    if old.status == STATUS_SUPERSEDED:
                        old.superseded_by = relationship.id
                    else:
                        old.contradicted_by = relationship.id
                        relationship.contradicted_by = old.id
                await session.flush()
                return relationship.to_dict()

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


def normalize_type(value: str) -> str:
    """Normalize an entity/relationship type to the storage form."""
    return value.strip().lower().replace(" ", "_")[:50]
