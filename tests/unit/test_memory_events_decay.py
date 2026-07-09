"""Decay tests for the Memory Event Substrate (Phase 2c).

Covers the pure decay math (half-life semantics), fail-fast settings
validation, the volatile default TTL stamped at write time, the volatile
expiry sweep (soft-delete -> excluded from replay), and query-time
re-ranking in the knowledge graph context block.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import DecaySettings, MemoryEventService
from muxi.runtime.services.memory.events.decay import (
    decayed_confidence,
    effective_event_confidence,
    effective_fact_confidence,
)
from muxi.runtime.services.memory.events.models import (
    DECAY_DECAYING,
    DECAY_STATIC,
    DECAY_VOLATILE,
    EVENT_FACT_EXTRACTED,
)
from muxi.runtime.utils.datetime_utils import utc_now_naive

FORMATION_ID = "decay-test-formation"
USER = "u1"


@pytest.fixture
def service(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/decay.db")
    db_manager.create_tables(Base.metadata)
    yield MemoryEventService(db_manager, FORMATION_ID)
    db_manager.engine.dispose()


class TestDecayMath:
    def test_zero_age_keeps_confidence(self):
        assert decayed_confidence(0.9, 0.0, 90.0) == 0.9

    def test_one_half_life_halves(self):
        assert decayed_confidence(0.8, 90.0, 90.0) == pytest.approx(0.4)

    def test_two_half_lives_quarter(self):
        assert decayed_confidence(0.8, 180.0, 90.0) == pytest.approx(0.2)

    def test_static_event_never_fades(self):
        event = {
            "source_confidence": 0.9,
            "decay_rate": DECAY_STATIC,
            "occurred_at": (utc_now_naive() - timedelta(days=1000)).isoformat(),
        }
        assert effective_event_confidence(event) == 0.9

    def test_decaying_event_fades_with_default_half_life(self):
        decay = DecaySettings({"default_half_life_days": 100})
        event = {
            "source_confidence": 1.0,
            "decay_rate": DECAY_DECAYING,
            "occurred_at": (utc_now_naive() - timedelta(days=100)).isoformat(),
        }
        assert effective_event_confidence(event, decay) == pytest.approx(0.5, abs=0.01)

    def test_volatile_event_zero_after_expiry(self):
        event = {
            "source_confidence": 1.0,
            "decay_rate": DECAY_VOLATILE,
            "expires_at": (utc_now_naive() - timedelta(hours=1)).isoformat(),
        }
        assert effective_event_confidence(event) == 0.0

    def test_volatile_event_full_before_expiry(self):
        event = {
            "source_confidence": 0.7,
            "decay_rate": DECAY_VOLATILE,
            "expires_at": (utc_now_naive() + timedelta(hours=1)).isoformat(),
        }
        assert effective_event_confidence(event) == 0.7

    def test_disabled_settings_return_stored_confidence(self):
        decay = DecaySettings({"enabled": False})
        event = {
            "source_confidence": 1.0,
            "decay_rate": DECAY_DECAYING,
            "occurred_at": (utc_now_naive() - timedelta(days=1000)).isoformat(),
        }
        assert effective_event_confidence(event, decay) == 1.0

    def test_fact_without_configured_half_life_is_static(self):
        decay = DecaySettings({})
        fact = {
            "type": "lives_in",
            "confidence": 0.9,
            "updated_at": (utc_now_naive() - timedelta(days=1000)).isoformat(),
        }
        assert effective_fact_confidence(fact, decay) == 0.9

    def test_fact_with_configured_half_life_fades(self):
        decay = DecaySettings({"half_lives": {"works_at": 90}})
        fact = {
            "type": "works_at",
            "confidence": 0.8,
            "updated_at": (utc_now_naive() - timedelta(days=90)).isoformat(),
        }
        assert effective_fact_confidence(fact, decay) == pytest.approx(0.4, abs=0.01)


class TestDecaySettingsValidation:
    def test_defaults(self):
        decay = DecaySettings()
        assert decay.enabled is True
        assert decay.default_half_life_days == 180.0
        assert decay.volatile_ttl_hours == 24.0
        assert decay.half_lives == {}

    def test_invalid_half_life_fails_fast(self):
        with pytest.raises(ValueError):
            DecaySettings({"default_half_life_days": 0})

    def test_invalid_ttl_fails_fast(self):
        with pytest.raises(ValueError):
            DecaySettings({"volatile_default_ttl_hours": "soon"})

    def test_invalid_type_half_life_fails_fast(self):
        with pytest.raises(ValueError):
            DecaySettings({"half_lives": {"works_at": -1}})

    def test_non_mapping_half_lives_fails_fast(self):
        with pytest.raises(ValueError):
            DecaySettings({"half_lives": ["works_at"]})


class TestVolatileLifecycle:
    async def test_volatile_default_expiry_stamped_at_write(self, service):
        event = await service.record(
            user_id=USER,
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "User is tired today", "collection": "context"},
            source="interaction",
            decay_rate=DECAY_VOLATILE,
        )
        assert event["expires_at"] is not None

    async def test_expiry_sweep_soft_deletes_and_replay_excludes(self, service):
        now = utc_now_naive()
        expired = await service.record(
            user_id=USER,
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "User is tired today", "collection": "context"},
            source="interaction",
            decay_rate=DECAY_VOLATILE,
            expires_at=now - timedelta(hours=1),
        )
        fresh = await service.record(
            user_id=USER,
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "User is on a deadline this week", "collection": "context"},
            source="interaction",
            decay_rate=DECAY_VOLATILE,
            expires_at=now + timedelta(days=2),
        )

        assert await service.run_volatile_expiry() == 1
        live = await service.list_events(USER)
        assert [event["id"] for event in live] == [fresh["id"]]

        # The audit trail survives until the retention hard purge.
        gone = await service.storage.get_event(expired["id"])
        assert gone["deleted_at"] is not None
        assert gone["deleted_reason"] == "expired"

    async def test_static_events_never_swept(self, service):
        await service.record(
            user_id=USER,
            event_type=EVENT_FACT_EXTRACTED,
            payload={"memory": "Lives in London", "collection": "user_identity"},
            source="interaction",
        )
        assert await service.run_volatile_expiry() == 0
        assert len(await service.list_events(USER)) == 1


class TestContextBlockDecayRanking:
    async def test_stale_decaying_fact_sinks_below_fresh_one(self, tmp_path):
        from muxi.runtime.services.memory.graph.service import KnowledgeGraphService

        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/decay-graph.db")
        db_manager.create_tables(Base.metadata)
        try:
            decay = DecaySettings({"half_lives": {"works_at": 30}})
            graph = KnowledgeGraphService(db_manager, FORMATION_ID, decay=decay)

            user = await graph.storage.upsert_entity(USER, "person", "User", confidence=0.95)
            acme = await graph.storage.upsert_entity(USER, "company", "Acme", confidence=0.9)
            topic = await graph.storage.upsert_entity(USER, "topic", "chess", confidence=0.9)
            stale = await graph.storage.upsert_relationship(
                USER, user["id"], acme["id"], "works_at", confidence=0.95
            )
            await graph.storage.upsert_relationship(
                USER, user["id"], topic["id"], "interested_in", confidence=0.6
            )
            # Age the works_at fact by a year (well past its 30d half-life).
            from sqlalchemy import text

            with db_manager.engine.connect() as conn:
                conn.execute(
                    text("UPDATE kg_relationships SET updated_at = :ts WHERE id = :id"),
                    {
                        "ts": utc_now_naive() - timedelta(days=365),
                        "id": stale["id"],
                    },
                )
                conn.commit()

            block = await graph.get_context_block(USER)
            lines = block.splitlines()
            assert lines[0].startswith("User -[interested_in]->")  # fresh fact ranks first
            assert any("works_at" in line for line in lines)  # stale fact still present
        finally:
            db_manager.engine.dispose()
