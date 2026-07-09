"""Unit tests for entity resolution (Memory Ingestion maturation).

Covers:

  * Probabilistic scoring per PRD dimension (name / email / handle /
    role / relationship context), deterministic and pure.
  * Auto-merge at/above the high-confidence threshold; flag (event +
    stored attributes.possible_duplicates marker) below it.
  * Merge mechanics: relationship re-pointing (collisions and would-be
    self-loops superseded, never deleted), attribute absorption,
    aliases, and the merged-name upsert redirect (sticky merges).
  * Determinism + idempotency: re-running resolution appends nothing
    (per-pair source_id rides the substrate's idempotency index) and a
    full projection rebuild replays the recorded decisions to the same
    merged graph.
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import MemoryEventService
from muxi.runtime.services.memory.events.models import EVENT_ENTITY_RESOLVED, SOURCE_SYNTHESIS
from muxi.runtime.services.memory.events.projectors import KnowledgeGraphProjector
from muxi.runtime.services.memory.graph.models import (
    STATUS_ACTIVE,
    STATUS_MERGED,
    STATUS_SUPERSEDED,
)
from muxi.runtime.services.memory.graph.resolution import (
    DECISION_FLAGGED,
    DECISION_MERGED,
    EntityResolver,
    pair_source_id,
    pick_canonical,
    score_identity_match,
)
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.ingest.config import parse_ingestion_config

FORMATION_ID = "resolution-test-formation"

USER = "u1"


def entity(name, entity_id=1, confidence=0.9, **attributes):
    return {"id": entity_id, "name": name, "confidence": confidence, "attributes": attributes}


def resolution_settings(**overrides):
    return parse_ingestion_config({"entity_resolution": overrides}).entity_resolution


@pytest.fixture
def graph_env(tmp_path):
    """Real graph service + event substrate over one SQLite database."""
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/resolution.db")
    db_manager.create_tables(Base.metadata)
    events = MemoryEventService(db_manager, FORMATION_ID, config={"enabled": True})
    graph = KnowledgeGraphService(db_manager, FORMATION_ID, config={}, event_log=events)
    events.register_projector(KnowledgeGraphProjector(graph))
    yield graph, events
    db_manager.engine.dispose()


# ----------------------------------------------------------------------
# Scoring per PRD dimension
# ----------------------------------------------------------------------


class TestScoring:
    def test_email_match(self):
        score, signals = score_identity_match(
            entity("Ryan", email="ryan@nabo.dev"),
            entity("Ryan Leveille", 2, email="RYAN@nabo.dev"),
        )
        assert "email_match" in signals and "name_subset" in signals
        assert score == pytest.approx(0.95)

    def test_email_found_in_any_attribute_value(self):
        score, signals = score_identity_match(
            entity("Ryan", note="contact: ryan@nabo.dev"),
            entity("Rian", 2, emails=["ryan@nabo.dev"]),
        )
        assert "email_match" in signals
        assert score >= 0.6

    def test_handle_match(self):
        score, signals = score_identity_match(
            entity("Ryan Leveille", github="@rleveille"),
            entity("Ryan", 2, handle="rleveille"),
        )
        assert "handle_match" in signals
        assert score == pytest.approx(0.4 + 0.35)

    def test_name_exact_tokens(self):
        score, signals = score_identity_match(entity("ryan leveille"), entity("Leveille, Ryan", 2))
        assert signals == ["name_match"]
        assert score == pytest.approx(0.5)

    def test_first_name_only(self):
        score, signals = score_identity_match(entity("Ryan Smith"), entity("Ryan Jones", 2))
        assert signals == ["first_name_match"]
        assert score == pytest.approx(0.15)

    def test_role_match(self):
        _, signals = score_identity_match(
            entity("Ryan", role="CTO"), entity("Ryan Leveille", 2, title="cto")
        )
        assert "role_match" in signals

    def test_shared_context(self):
        score, signals = score_identity_match(
            entity("Ryan"), entity("Ryan Leveille", 2), shared_neighbors=1
        )
        assert "shared_context" in signals
        assert score == pytest.approx(0.35 + 0.2)

    def test_unrelated_entities_score_low(self):
        score, signals = score_identity_match(entity("Ryan"), entity("Sarah", 2))
        assert score == 0.0
        assert signals == []

    def test_pick_canonical_prefers_fuller_name(self):
        canonical, duplicate = pick_canonical(entity("Ryan", 5), entity("Ryan Leveille", 9))
        assert canonical["name"] == "Ryan Leveille"
        assert duplicate["name"] == "Ryan"

    def test_pick_canonical_tie_falls_to_older_row(self):
        canonical, _ = pick_canonical(entity("Ryan A", 5), entity("Ryan B", 9))
        assert canonical["id"] == 5  # same token count + confidence -> lower id

    def test_pair_source_id_is_order_independent(self):
        assert pair_source_id("person", "Ryan", "Ryan Leveille", "merged") == pair_source_id(
            "person", "Ryan Leveille", "Ryan", "merged"
        )


# ----------------------------------------------------------------------
# Resolver: merge / flag decisions over a real graph
# ----------------------------------------------------------------------


async def seed_duplicate_identities(graph, *, email=True):
    """Two person entities + edges: the classic 'Ryan' duplicate."""
    attributes = {"email": "ryan@nabo.dev"} if email else {}
    full = await graph.storage.upsert_entity(
        USER, "person", "Ryan Leveille", attributes=attributes, confidence=0.9
    )
    short = await graph.storage.upsert_entity(
        USER, "person", "Ryan", attributes=attributes, confidence=0.8
    )
    company = await graph.storage.upsert_entity(USER, "company", "Nabo", confidence=0.9)
    await graph.storage.upsert_relationship(
        USER, full["id"], company["id"], "works_at", confidence=0.9
    )
    await graph.storage.upsert_relationship(
        USER, short["id"], company["id"], "works_at", confidence=0.8
    )
    return full, short, company


class TestResolver:
    async def test_auto_merge_above_threshold(self, graph_env):
        graph, events = graph_env
        full, short, company = await seed_duplicate_identities(graph)
        resolver = EntityResolver(graph, events, resolution_settings())

        counts = await resolver.resolve_user(USER)
        assert counts == {"merged": 1, "flagged": 0}

        # Decision recorded as an entity.resolved event (source synthesis,
        # deterministic per-pair key).
        recorded = await events.list_events(USER, event_types=[EVENT_ENTITY_RESOLVED])
        assert len(recorded) == 1
        payload = recorded[0]["payload"]
        assert payload["decision"] == DECISION_MERGED
        assert payload["canonical_name"] == "Ryan Leveille"
        assert payload["duplicate_name"] == "Ryan"
        assert "email_match" in payload["signals"]
        assert recorded[0]["source"] == SOURCE_SYNTHESIS

        # Duplicate marked merged -> canonical; canonical carries alias.
        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED
        assert merged["superseded_by"] == full["id"]
        canonical = await graph.storage.get_entity(USER, "person", "Ryan Leveille")
        assert canonical["attributes"]["aliases"] == ["Ryan"]

        # The duplicate's works_at edge collided with the canonical's:
        # superseded (retained), never deleted; one active edge remains.
        active = await graph.storage.list_relationships(USER, rel_type="works_at")
        assert len(active) == 1
        assert active[0]["from_entity_id"] == full["id"]
        superseded = await graph.storage.list_relationships(
            USER, rel_type="works_at", status=STATUS_SUPERSEDED
        )
        assert len(superseded) == 1

        # Merged entities disappear from the active listing.
        names = {e["name"] for e in await graph.storage.list_entities(USER, entity_type="person")}
        assert names == {"Ryan Leveille"}

    async def test_repoints_unique_edges_to_canonical(self, graph_env):
        graph, events = graph_env
        full, short, _ = await seed_duplicate_identities(graph)
        project = await graph.storage.upsert_entity(USER, "project", "Atlas", confidence=0.9)
        await graph.storage.upsert_relationship(
            USER, short["id"], project["id"], "building", confidence=0.8
        )

        resolver = EntityResolver(graph, events, resolution_settings())
        await resolver.resolve_user(USER)

        building = await graph.storage.list_relationships(USER, rel_type="building")
        assert len(building) == 1
        assert building[0]["from_entity_id"] == full["id"]

    async def test_flag_below_merge_threshold(self, graph_env):
        graph, events = graph_env
        # Name subset + shared employer = 0.55: above the flag threshold,
        # below the merge threshold.
        await seed_duplicate_identities(graph, email=False)
        resolver = EntityResolver(graph, events, resolution_settings())

        counts = await resolver.resolve_user(USER)
        assert counts == {"merged": 0, "flagged": 1}

        recorded = await events.list_events(USER, event_types=[EVENT_ENTITY_RESOLVED])
        assert recorded[0]["payload"]["decision"] == DECISION_FLAGGED

        # Stored marker on both rows; both stay active.
        full = await graph.storage.get_entity(USER, "person", "Ryan Leveille")
        short = await graph.storage.get_entity(USER, "person", "Ryan")
        assert full["attributes"]["possible_duplicates"] == ["Ryan"]
        assert short["attributes"]["possible_duplicates"] == ["Ryan Leveille"]
        assert full["status"] == short["status"] == STATUS_ACTIVE

    async def test_flagged_pair_can_merge_on_new_evidence(self, graph_env):
        graph, events = graph_env
        full, short, _ = await seed_duplicate_identities(graph, email=False)
        resolver = EntityResolver(graph, events, resolution_settings())
        assert (await resolver.resolve_user(USER))["flagged"] == 1

        # New evidence lands (shared email attribute): the pair now
        # crosses the merge threshold; merged/flagged keys are distinct
        # so the earlier flag does not block the merge.
        await graph.storage.upsert_entity(
            USER, "person", "Ryan Leveille", attributes={"email": "ryan@nabo.dev"}
        )
        await graph.storage.upsert_entity(
            USER, "person", "Ryan", attributes={"email": "ryan@nabo.dev"}
        )
        counts = await resolver.resolve_user(USER)
        assert counts["merged"] == 1
        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED

    async def test_resolution_is_idempotent(self, graph_env):
        graph, events = graph_env
        await seed_duplicate_identities(graph)
        resolver = EntityResolver(graph, events, resolution_settings())

        assert (await resolver.resolve_user(USER))["merged"] == 1
        # Re-running (same content, e.g. re-ingestion) appends nothing
        # and merges nothing new.
        assert await resolver.resolve_user(USER) == {"merged": 0, "flagged": 0}
        recorded = await events.list_events(USER, event_types=[EVENT_ENTITY_RESOLVED])
        assert len(recorded) == 1

    async def test_merged_name_upsert_redirects_to_canonical(self, graph_env):
        graph, events = graph_env
        full, _, _ = await seed_duplicate_identities(graph)
        resolver = EntityResolver(graph, events, resolution_settings())
        await resolver.resolve_user(USER)

        # A later mention of the duplicate name (re-ingestion, new email)
        # enriches the canonical row instead of reviving the duplicate.
        redirected = await graph.storage.upsert_entity(
            USER, "person", "Ryan", attributes={"phone_style": "signal"}, confidence=0.7
        )
        assert redirected["id"] == full["id"]
        assert redirected["attributes"]["phone_style"] == "signal"
        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED  # never revived

    async def test_disabled_resolution_is_inert(self, graph_env):
        graph, events = graph_env
        await seed_duplicate_identities(graph)
        resolver = EntityResolver(graph, events, resolution_settings(enabled=False))
        assert await resolver.resolve_user(USER) == {"merged": 0, "flagged": 0}
        assert await events.list_events(USER, event_types=[EVENT_ENTITY_RESOLVED]) == []

    async def test_resolver_never_raises(self, graph_env):
        graph, events = graph_env

        class Boom:
            def __getattr__(self, name):
                raise RuntimeError("storage down")

        broken = EntityResolver(Boom(), events, resolution_settings())
        assert await broken.resolve_user(USER) == {"merged": 0, "flagged": 0}


# ----------------------------------------------------------------------
# Rebuild determinism (replay reproduces the merged graph)
# ----------------------------------------------------------------------


def graph_snapshot(entities, relationships):
    return (
        sorted(
            (
                e["type"],
                e["name"],
                e["status"],
                e["superseded_by"] is not None,
                tuple(sorted((e["attributes"] or {}).get("aliases", []))),
            )
            for e in entities
        ),
        sorted(
            (r["type"], r["from_entity_id"], r["to_entity_id"], r["status"]) for r in relationships
        ),
    )


class TestRebuildDeterminism:
    async def test_rebuild_replays_recorded_decisions(self, graph_env):
        graph, events = graph_env

        # Live flow: extractions recorded as graph.extracted events (the
        # dual-write path), then resolution merges the duplicate.
        await graph.store_extraction(
            USER,
            {
                "entities": [
                    {
                        "name": "Ryan Leveille",
                        "type": "person",
                        "attributes": {"email": "ryan@nabo.dev"},
                        "confidence": 0.9,
                    },
                    {"name": "Nabo", "type": "company", "attributes": {}, "confidence": 0.9},
                ],
                "relationships": [
                    {
                        "from": "Ryan Leveille",
                        "from_type": "person",
                        "to": "Nabo",
                        "to_type": "company",
                        "type": "works_at",
                        "confidence": 0.9,
                    }
                ],
            },
        )
        await graph.store_extraction(
            USER,
            {
                "entities": [
                    {
                        "name": "Ryan",
                        "type": "person",
                        "attributes": {"email": "ryan@nabo.dev"},
                        "confidence": 0.8,
                    }
                ],
                "relationships": [],
            },
        )
        resolver = EntityResolver(graph, events, resolution_settings())
        assert (await resolver.resolve_user(USER))["merged"] == 1

        entities = await graph.storage.list_entities(USER, status=None, limit=100)
        relationships = await graph.storage.list_relationships(USER, status=None, limit=100)
        before = graph_snapshot(entities, relationships)

        # Wipe-and-replay through the substrate's rebuild machinery.
        report = await events.rebuild(USER, projection="knowledge_graph")
        assert report["knowledge_graph"]["failed"] == 0
        # graph.extracted x2 + entity.resolved x1 replayed in append order.
        assert report["knowledge_graph"]["events"] == 3

        entities = await graph.storage.list_entities(USER, status=None, limit=100)
        relationships = await graph.storage.list_relationships(USER, status=None, limit=100)
        assert graph_snapshot(entities, relationships) == before

        # And a second rebuild converges again (idempotent replay).
        await events.rebuild(USER, projection="knowledge_graph")
        entities = await graph.storage.list_entities(USER, status=None, limit=100)
        relationships = await graph.storage.list_relationships(USER, status=None, limit=100)
        assert graph_snapshot(entities, relationships) == before

    async def test_replay_never_rescores(self, graph_env):
        # Threshold changes after the fact must not rewrite history: the
        # projector applies the recorded decision payload verbatim.
        graph, events = graph_env
        await seed_duplicate_identities(graph)
        resolver = EntityResolver(graph, events, resolution_settings())
        await resolver.resolve_user(USER)

        (event,) = await events.list_events(USER, event_types=[EVENT_ENTITY_RESOLVED])
        projector = KnowledgeGraphProjector(graph)
        result = await projector.apply(event)
        # Re-applying the merged decision is a no-op (already merged).
        assert result["applied"] is True
        merged = await graph.storage.get_entity(USER, "person", "Ryan")
        assert merged["status"] == STATUS_MERGED
