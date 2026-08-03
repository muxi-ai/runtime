"""Unit tests for Memory Distillery Phase 3b: /v1/memories/distilled.

Covers the distillery surface at the unit level:

  * Signature verification: valid batches verify; invalid, missing,
    tampered, and replayed (stale-timestamp) batches fail closed with
    401 semantics and an observability alert path.
  * Registration: public keys must parse as Ed25519 (DER SPKI or raw 32
    bytes, "ed25519:" prefix optional); trust levels validated; scope
    defaults filled from formation config; revocation flips subsequent
    batches to 410 semantics.
  * Contract: batch envelope validation (batch_id, events, batch-size
    ceiling, embedding modes) and per-event validation with indexed
    rejection reasons (unsupported types, out-of-scope user_id/event_type,
    schema violations) that never fail the whole batch.
  * Distilled payload -> events -> projections: accepted events land in
    the substrate event-first with source="distillery" and the event's
    own user_id (the distillery is a SYSTEM-LEVEL principal; every write
    stays user-scoped -- no shared-scope writes), then the background job
    projects fact.extracted rows through apply_fact_event and log.entry
    rows through the captain's log service.
  * Idempotency: replayed batches reuse the substrate's
    (source="distillery", source_id) key -- zero duplicates, reported in
    the `duplicates` count, no second projection run.
  * Trust levels: provisional caps source_confidence; verified does not.
  * Embedding modes: pre_computed vectors are stored when the declared
    model matches the formation's model (and the dimension checks out),
    discarded + re-embedded on mismatch (graceful degradation).
  * Daily quota: the per-distillery counter rejects with 429 semantics.
  * Inertness: without memory.distillery.enabled the service refuses all
    work, so unconfigured formations are untouched.
"""

from __future__ import annotations

import asyncio
import base64
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from muxi.runtime.formation.background.request_tracker import RequestStatus, RequestTracker
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.distillery import (
    DISPOSITION_PROJECTED,
    DISPOSITION_RECORDED,
    PROVISIONAL_CONFIDENCE_CAP,
    SOURCE_DISTILLERY,
    DistilleryAuthError,
    DistilleryQuotaCounter,
    DistilleryQuotaStore,
    DistilleryRateLimitError,
    DistilleryRevokedError,
    DistilleryUnavailableError,
    MemoryDistilleryService,
    RegisteredDistillery,
    SignatureVerificationError,
    check_timestamp,
    parse_public_key,
    signed_message,
    user_id_in_scope,
    validate_distilled_event,
    verify_signature,
)
from muxi.runtime.services.memory.events import MemoryEventService
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    MemoryEvent,
    ProjectionCheckpoint,
)
from muxi.runtime.services.memory.events.projectors import FACT_EVENT_METADATA_KEY

FORMATION_ID = "distillery-test-formation"

TABLES = [
    MemoryEvent.__table__,
    ProjectionCheckpoint.__table__,
    RegisteredDistillery.__table__,
    DistilleryQuotaCounter.__table__,
]


# ----------------------------------------------------------------------
# Crypto fixtures (mock distillery keypair)
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def keypair():
    """One Ed25519 keypair shared by the module's tests."""
    private = Ed25519PrivateKey.generate()
    der = private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return private, "ed25519:" + base64.b64encode(der).decode()


def sign(private, timestamp, distillery_id, body: bytes) -> str:
    """Sign one batch the way the reference distillery does."""
    return base64.b64encode(
        private.sign(signed_message(str(timestamp), distillery_id, body))
    ).decode()


# ----------------------------------------------------------------------
# Test doubles (same posture as the ingestion unit tests)
# ----------------------------------------------------------------------


class RecordingLTM:
    """Minimal long-term-memory double recording add() calls."""

    def __init__(self, model="local/all-MiniLM-L6-v2", dimension=4):
        self._embedding_model_name = model
        self.dimension = dimension
        self.rows = []

    async def add(
        self, content, metadata=None, user_id=None, collection=None, embedding=None, scope=None
    ):
        self.rows.append(
            {
                "content": content,
                "metadata": dict(metadata or {}),
                "user_id": user_id,
                "collection": collection,
                "embedding": embedding,
                "scope": scope,
            }
        )
        return f"m{len(self.rows)}"


class RecordingCaptainsLog:
    """Captain's log double recording apply_log_entry_event calls."""

    def __init__(self):
        self.entries = []

    async def apply_log_entry_event(self, user_id, payload, event_id=None):
        self.entries.append({"user_id": user_id, "payload": payload, "event_id": event_id})
        return {"id": len(self.entries)}, {}


def make_overlord(memory_events, *, distillery_config=None, long_term_memory=None):
    """Build the minimal overlord surface the distillery service uses."""
    config = {"enabled": True} if distillery_config is None else distillery_config
    return SimpleNamespace(
        formation_config={"memory": {"distillery": config}},
        formation_id=FORMATION_ID,
        memory_events=memory_events,
        request_tracker=RequestTracker(),
        long_term_memory=long_term_memory or RecordingLTM(),
        captains_log=RecordingCaptainsLog(),
        is_multi_user=True,
    )


@pytest.fixture
def memory_events(tmp_path):
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/events.db")
    db_manager.create_tables(Base.metadata, tables=TABLES)
    service = MemoryEventService(db_manager, FORMATION_ID, config={"enabled": True})
    yield service
    db_manager.engine.dispose()


@pytest.fixture
def service(memory_events):
    return MemoryDistilleryService(make_overlord(memory_events))


async def register(service, keypair, **overrides):
    """Register a distillery with sane defaults for the tests."""
    _, public_key = keypair
    kwargs = {
        "name": "Acme Internal Distillery",
        "public_key": public_key,
        "scope": service.scope_defaults(overrides.pop("scope", None)),
        "trust_level": overrides.pop("trust_level", "verified"),
    }
    kwargs.update(overrides)
    return await service.registry.register(**kwargs)


def fact_event(source_id="slack-1", user_id="alice@acme.com", **overrides):
    event = {
        "event_type": "fact.extracted",
        "user_id": user_id,
        "source": "distillery",
        "source_id": source_id,
        "payload": {
            "memory": "Alice is a member of the Engineering team",
            "collection": "context",
        },
    }
    event.update(overrides)
    return event


def make_batch(events, **overrides):
    batch = {"batch_id": "batch-2026-07-07-001", "events": events}
    batch.update(overrides)
    return batch


async def finish_job(overlord, processing_id):
    """Await the background projection task and return the tracker state."""
    state = await overlord.request_tracker.get_request(processing_id)
    assert state is not None
    await state.task_ref
    return await overlord.request_tracker.get_request(processing_id)


async def accept(service, distillery, batch):
    """Envelope-validate + submit one batch (the route's post-auth path)."""
    meta, error = service.validate_batch(batch, distillery)
    assert error is None, error
    return await service.submit(distillery, meta)


# ----------------------------------------------------------------------
# Signature verification
# ----------------------------------------------------------------------


class TestSignatureVerification:
    def test_valid_signature_verifies(self, keypair):
        private, public = keypair
        body = b'{"batch_id": "b-1", "events": []}'
        signature = sign(private, 1234, "dst-1", body)
        verify_signature(public, signature, "1234", "dst-1", body)  # no raise

    def test_missing_signature_fails_closed(self, keypair):
        _, public = keypair
        with pytest.raises(SignatureVerificationError, match="required"):
            verify_signature(public, None, "1234", "dst-1", b"{}")

    def test_invalid_signature_rejected(self, keypair):
        private, public = keypair
        signature = sign(private, 1234, "dst-1", b'{"batch_id": "b-1"}')
        with pytest.raises(SignatureVerificationError):
            verify_signature(public, signature, "1234", "dst-1", b'{"batch_id": "b-2"}')

    def test_signature_bound_to_headers(self, keypair):
        # A signature lifted from one batch cannot be replayed with a
        # different timestamp or distillery id (header binding).
        private, public = keypair
        body = b'{"batch_id": "b-1"}'
        signature = sign(private, 1234, "dst-1", body)
        with pytest.raises(SignatureVerificationError):
            verify_signature(public, signature, "9999", "dst-1", body)
        with pytest.raises(SignatureVerificationError):
            verify_signature(public, signature, "1234", "dst-2", body)

    def test_garbage_signature_material_fails_closed(self, keypair):
        _, public = keypair
        with pytest.raises(SignatureVerificationError):
            verify_signature(public, "not-base64!!", "1234", "dst-1", b"{}")

    def test_wrong_key_rejected(self, keypair):
        private, _ = keypair
        other = Ed25519PrivateKey.generate()
        other_pub = base64.b64encode(
            other.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        ).decode()
        body = b"{}"
        signature = sign(private, 1234, "dst-1", body)
        with pytest.raises(SignatureVerificationError):
            verify_signature("ed25519:" + other_pub, signature, "1234", "dst-1", body)

    def test_replay_window(self):
        now = time.time()
        assert check_timestamp(str(int(now)), now, 300) == int(now)
        # Modest skew on either side is tolerated (symmetric window)...
        check_timestamp(str(int(now) - 299), now, 300)
        check_timestamp(str(int(now) + 299), now, 300)
        # ...but stale captures and far-future stamps are replays.
        with pytest.raises(SignatureVerificationError, match="replay"):
            check_timestamp(str(int(now) - 301), now, 300)
        with pytest.raises(SignatureVerificationError, match="replay"):
            check_timestamp(str(int(now) + 301), now, 300)
        with pytest.raises(SignatureVerificationError):
            check_timestamp(None, now, 300)
        with pytest.raises(SignatureVerificationError):
            check_timestamp("yesterday", now, 300)

    def test_public_key_forms(self, keypair):
        private, public = keypair
        parse_public_key(public)  # ed25519: + DER
        parse_public_key(public[len("ed25519:") :])  # bare DER
        raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        parse_public_key(base64.b64encode(raw).decode())  # raw 32 bytes
        with pytest.raises(ValueError):
            parse_public_key("ed25519:AAAA")  # neither raw-32 nor DER
        with pytest.raises(ValueError):
            parse_public_key("")


class TestAuthenticate:
    async def test_end_to_end_authentication(self, service, keypair, memory_events):
        private, _ = keypair
        record = await register(service, keypair)
        body = b'{"batch_id": "b-1", "events": []}'
        timestamp = str(int(time.time()))
        signature = sign(private, timestamp, record["distillery_id"], body)

        distillery = await service.authenticate(record["distillery_id"], signature, timestamp, body)
        assert distillery["distillery_id"] == record["distillery_id"]

        # Unknown id, bad signature, and stale timestamp all fail closed.
        with pytest.raises(DistilleryAuthError):
            await service.authenticate("nope", signature, timestamp, body)
        with pytest.raises(DistilleryAuthError):
            await service.authenticate(record["distillery_id"], signature, timestamp, b"tampered")
        stale = str(int(time.time()) - 3600)
        stale_sig = sign(private, stale, record["distillery_id"], body)
        with pytest.raises(DistilleryAuthError):
            await service.authenticate(record["distillery_id"], stale_sig, stale, body)
        with pytest.raises(DistilleryAuthError):
            await service.authenticate(None, signature, timestamp, body)

    async def test_revoked_distillery_gets_410_semantics(self, service, keypair):
        private, _ = keypair
        record = await register(service, keypair)
        await service.registry.revoke(record["distillery_id"])
        body = b"{}"
        timestamp = str(int(time.time()))
        signature = sign(private, timestamp, record["distillery_id"], body)
        with pytest.raises(DistilleryRevokedError):
            await service.authenticate(record["distillery_id"], signature, timestamp, body)


# ----------------------------------------------------------------------
# Registration + configuration
# ----------------------------------------------------------------------


class TestRegistration:
    async def test_register_fills_scope_defaults(self, service, keypair):
        record = await register(service, keypair, scope={"user_ids": "pattern:*@acme.com"})
        assert record["scope"]["user_ids"] == "pattern:*@acme.com"
        assert record["scope"]["event_types"] == ["fact.extracted", "log.entry", "interaction.turn"]
        assert record["scope"]["max_batch_size"] == 10_000
        assert record["scope"]["max_events_per_day"] == 1_000_000
        assert record["status"] == "active"

    async def test_register_rejects_bad_key_and_trust(self, service, keypair):
        with pytest.raises(ValueError, match="base64|DER|Ed25519|public_key"):
            await service.registry.register(
                name="bad", public_key="ed25519:zzzz", scope={}, trust_level="verified"
            )
        with pytest.raises(ValueError, match="trust_level"):
            await register(service, keypair, trust_level="ultra")
        with pytest.raises(ValueError, match="'name'"):
            await register(service, keypair, name="  ")

    async def test_list_and_revoke(self, service, keypair):
        first = await register(service, keypair, name="one")
        second = await register(service, keypair, name="two")
        listed = await service.registry.list()
        assert [d["name"] for d in listed] == ["two", "one"]

        revoked = await service.registry.revoke(first["distillery_id"])
        assert revoked["status"] == "revoked"
        assert revoked["revoked_at"] is not None
        active = await service.registry.list(include_revoked=False)
        assert [d["distillery_id"] for d in active] == [second["distillery_id"]]
        assert await service.registry.revoke("unknown") is None

    def test_config_validation_and_defaults(self, memory_events):
        service = MemoryDistilleryService(
            make_overlord(
                memory_events,
                distillery_config={
                    "enabled": True,
                    "default_max_batch_size": 50,
                    "default_max_events_per_day": "not-a-number",
                    "default_trust_level": "weird",
                    "signature_max_age_seconds": 60,
                },
            )
        )
        assert service.enabled
        assert service.default_max_batch_size == 50
        assert service.default_max_events_per_day == 1_000_000  # fallback
        assert service.default_trust_level == "provisional"  # fallback
        assert service.signature_max_age_seconds == 60

    async def test_no_config_is_inert(self, memory_events, keypair):
        # A formation without memory.distillery config gets a disabled
        # service that refuses every operation -- zero behavior change.
        service = MemoryDistilleryService(make_overlord(memory_events, distillery_config={}))
        assert service.enabled is False
        with pytest.raises(DistilleryUnavailableError, match="not enabled"):
            await service.authenticate("id", "sig", str(int(time.time())), b"{}")
        with pytest.raises(DistilleryUnavailableError):
            _ = service.registry

    async def test_substrate_required(self, keypair):
        service = MemoryDistilleryService(make_overlord(None))
        with pytest.raises(DistilleryUnavailableError, match="event substrate"):
            _ = service.registry


# ----------------------------------------------------------------------
# Contract: envelope + per-event validation
# ----------------------------------------------------------------------


class TestBatchValidation:
    @pytest.fixture
    def distillery(self, service):
        return {
            "distillery_id": "dst-1",
            "trust_level": "verified",
            "scope": service.scope_defaults(None),
        }

    def test_envelope_rules(self, service, distillery):
        _, error = service.validate_batch("nope", distillery)
        assert "JSON object" in error
        _, error = service.validate_batch({"events": [fact_event()]}, distillery)
        assert "'batch_id'" in error
        _, error = service.validate_batch({"batch_id": "b", "events": []}, distillery)
        assert "'events'" in error
        meta, error = service.validate_batch(make_batch([fact_event()]), distillery)
        assert error is None
        assert meta["embedding_mode"] == "none"

    def test_batch_size_ceiling(self, service, distillery):
        distillery["scope"]["max_batch_size"] = 2
        batch = make_batch([fact_event(source_id=f"s{i}") for i in range(3)])
        _, error = service.validate_batch(batch, distillery)
        assert "max_batch_size" in error

    def test_embedding_mode_rules(self, service, distillery):
        _, error = service.validate_batch(
            make_batch([fact_event()], embedding_mode="fancy"), distillery
        )
        assert "embedding_mode" in error
        _, error = service.validate_batch(
            make_batch([fact_event()], embedding_mode="pre_computed"), distillery
        )
        assert "embedding_model" in error
        _, error = service.validate_batch(
            make_batch(
                [fact_event()],
                embedding_mode="pre_computed",
                embedding_model="no-provider-prefix",
            ),
            distillery,
        )
        assert "provider-prefixed" in error
        meta, error = service.validate_batch(
            make_batch(
                [fact_event()],
                embedding_mode="pre_computed",
                embedding_model="local/all-MiniLM-L6-v2",
            ),
            distillery,
        )
        assert error is None


class TestEventValidation:
    SCOPE = {
        "user_ids": "pattern:*@acme.com",
        "event_types": ["fact.extracted", "log.entry"],
    }

    def check(self, entry, **kwargs):
        scope = kwargs.pop("scope", self.SCOPE)
        trust = kwargs.pop("trust_level", "verified")
        multi = kwargs.pop("is_multi_user", True)
        return validate_distilled_event(entry, scope, trust, multi)

    def test_valid_event_normalized(self):
        event, error = self.check(
            fact_event(
                occurred_at="2026-07-07T10:00:00Z",
                source_confidence=0.92,
                decay_rate="decaying",
            )
        )
        assert error is None
        assert event.user_id == "alice@acme.com"
        assert event.occurred_at.hour == 10 and event.occurred_at.tzinfo is None
        assert event.source_confidence == pytest.approx(0.92)
        assert event.decay_rate == "decaying"

    def test_rejection_reasons(self):
        _, error = self.check("not-a-dict")
        assert "must be an object" in error
        _, error = self.check(fact_event(event_type="entity.resolved"))
        assert "unsupported event_type" in error
        _, error = self.check(fact_event(event_type="interaction.turn"))
        assert "outside distillery scope" in error  # not in the allowed list
        _, error = self.check(fact_event(user_id="mallory@evil.com"))
        assert "outside distillery scope" in error
        _, error = self.check(fact_event(source="gmail"))
        assert 'must be "distillery"' in error
        _, error = self.check(fact_event(source_id="  "))
        assert "'source_id' is required" in error
        _, error = self.check(fact_event(payload={"collection": "context"}))
        assert "invalid event schema" in error and "memory" in error
        _, error = self.check(fact_event(occurred_at="not-a-date"))
        assert "ISO 8601" in error
        _, error = self.check(fact_event(source_confidence=1.5))
        assert "between 0 and 1" in error
        _, error = self.check(fact_event(decay_rate="sometimes"))
        assert "decay_rate" in error
        _, error = self.check(fact_event(surprise_key=True))
        assert "unknown event keys" in error
        _, error = self.check(fact_event(embedding_vectors={"memory": "vec"}))
        assert "non-empty array" in error
        _, error = self.check(fact_event(embedding_vectors={"memory": [0.1, "x"]}))
        assert "only numbers" in error

    def test_multi_user_requires_user_id(self):
        entry = fact_event()
        del entry["user_id"]
        _, error = self.check(entry, scope={"user_ids": "all"})
        assert "'user_id' is required" in error
        # Single-user formations default to "0".
        event, error = self.check(entry, scope={"user_ids": "all"}, is_multi_user=False)
        assert error is None and event.user_id == "0"

    def test_provisional_confidence_cap(self):
        event, _ = self.check(fact_event(source_confidence=0.95), trust_level="provisional")
        assert event.source_confidence == PROVISIONAL_CONFIDENCE_CAP
        event, _ = self.check(fact_event(source_confidence=0.5), trust_level="provisional")
        assert event.source_confidence == 0.5

    def test_user_scope_shapes(self):
        assert user_id_in_scope("anyone", "all")
        assert user_id_in_scope("anyone", None)
        assert user_id_in_scope("a@acme.com", "pattern:*@acme.com")
        assert not user_id_in_scope("a@evil.com", "pattern:*@acme.com")
        assert user_id_in_scope("bob", ["alice", "bob"])
        assert not user_id_in_scope("carol", ["alice", "bob"])
        assert user_id_in_scope("alice", "alice")
        assert not user_id_in_scope("alice", 42)  # unknown shape fails closed


# ----------------------------------------------------------------------
# Accept path: events -> substrate -> projections
# ----------------------------------------------------------------------


class TestSubmitAndProjections:
    async def test_batch_lands_events_and_projections(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair)

        batch = make_batch(
            [
                fact_event(source_id="slack-1", source_confidence=0.92),
                {
                    "event_type": "log.entry",
                    "user_id": "alice@acme.com",
                    "source_id": "digest-2026-07-06",
                    "payload": {"date": "2026-07-06", "summary": "Shipped the Atlas migration"},
                },
                {
                    "event_type": "interaction.turn",
                    "user_id": "bob@acme.com",
                    "source_id": "slack-msg-2",
                    "payload": {"user_message": "The launch is moved to Friday"},
                },
                fact_event(source_id="bad-1", payload={"collection": "context"}),  # rejected
            ]
        )
        outcome = await accept(service, record, batch)
        assert outcome["accepted"] == 3
        assert outcome["duplicates"] == 0
        assert outcome["rejected"] == 1
        assert outcome["rejections"][0]["index"] == 3
        assert "invalid event schema" in outcome["rejections"][0]["reason"]

        # Events landed event-first, user-scoped, with source="distillery".
        alice_events = await memory_events.list_events("alice@acme.com")
        assert {e["event_type"] for e in alice_events} == {"fact.extracted", "log.entry"}
        for event in alice_events:
            assert event["source"] == SOURCE_DISTILLERY
            assert event["scope_type"] == "user"
            assert event["scope_id"] == "alice@acme.com"
        fact = next(e for e in alice_events if e["event_type"] == EVENT_FACT_EXTRACTED)
        assert fact["source_confidence"] == pytest.approx(0.92)  # verified: no cap

        # The background job projected facts + log entries.
        state = await finish_job(overlord, outcome["processing_id"])
        assert state.status == RequestStatus.COMPLETED
        counts = state.result["counts"]
        assert counts[DISPOSITION_PROJECTED] == 2
        assert counts[DISPOSITION_RECORDED] == 1  # interaction.turn: log only
        assert counts["failed"] == 0

        ltm = overlord.long_term_memory
        assert len(ltm.rows) == 1
        row = ltm.rows[0]
        assert row["content"] == "Alice is a member of the Engineering team"
        assert row["user_id"] == "alice@acme.com"
        assert row["metadata"][FACT_EVENT_METADATA_KEY] == fact["id"]
        assert row["scope"] is None  # user scope: system principal never widens it
        assert row["embedding"] is None  # mode "none": MUXI embeds on receipt

        log = overlord.captains_log.entries[0]
        assert log["user_id"] == "alice@acme.com"
        assert log["payload"]["summary"] == "Shipped the Atlas migration"

    async def test_idempotent_replay_reuses_events(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair)

        first = await accept(service, record, make_batch([fact_event(source_id="slack-1")]))
        await finish_job(overlord, first["processing_id"])

        # Full-batch retry (same source_ids): zero new events, no new job.
        second = await accept(service, record, make_batch([fact_event(source_id="slack-1")]))
        assert second["accepted"] == 0
        assert second["duplicates"] == 1
        assert second["processing_id"] is None

        events = await memory_events.list_events("alice@acme.com")
        assert len(events) == 1
        assert len(overlord.long_term_memory.rows) == 1  # no re-projection

    async def test_provisional_trust_caps_stored_confidence(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, trust_level="provisional")

        outcome = await accept(service, record, make_batch([fact_event(source_confidence=0.99)]))
        await finish_job(overlord, outcome["processing_id"])
        events = await memory_events.list_events("alice@acme.com")
        assert events[0]["source_confidence"] == pytest.approx(PROVISIONAL_CONFIDENCE_CAP)

    async def test_daily_quota_429_semantics(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 2})

        outcome = await accept(
            service,
            record,
            make_batch([fact_event(source_id="s1"), fact_event(source_id="s2")]),
        )
        await finish_job(overlord, outcome["processing_id"])
        with pytest.raises(DistilleryRateLimitError):
            await accept(service, record, make_batch([fact_event(source_id="s3")]))

    async def test_projection_failure_is_contained(self, memory_events, keypair):
        class ExplodingLTM(RecordingLTM):
            async def add(self, *args, **kwargs):
                raise RuntimeError("vector store offline")

        overlord = make_overlord(memory_events, long_term_memory=ExplodingLTM())
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair)

        outcome = await accept(
            service,
            record,
            make_batch(
                [
                    fact_event(source_id="s1"),
                    {
                        "event_type": "interaction.turn",
                        "user_id": "alice@acme.com",
                        "source_id": "s2",
                        "payload": {"user_message": "hello"},
                    },
                ]
            ),
        )
        state = await finish_job(overlord, outcome["processing_id"])
        assert state.status == RequestStatus.COMPLETED  # job survives item failure
        by_index = {item["index"]: item for item in state.result["items"]}
        assert by_index[0]["disposition"] == "failed"
        assert "vector store offline" in by_index[0]["error"]
        assert by_index[1]["disposition"] == DISPOSITION_RECORDED


# ----------------------------------------------------------------------
# Embedding modes (pre_computed match / mismatch / hybrid)
# ----------------------------------------------------------------------


class TestEmbeddingModes:
    async def run_batch(self, memory_events, keypair, ltm, **batch_kwargs):
        overlord = make_overlord(memory_events, long_term_memory=ltm)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair)
        outcome = await accept(service, record, make_batch(**batch_kwargs))
        state = await finish_job(overlord, outcome["processing_id"])
        return ltm, state

    async def test_matching_model_stores_shipped_vectors(self, memory_events, keypair):
        ltm = RecordingLTM(model="local/all-MiniLM-L6-v2", dimension=4)
        vector = [0.1, 0.2, 0.3, 0.4]
        ltm, state = await self.run_batch(
            memory_events,
            keypair,
            ltm,
            events=[fact_event(embedding_vectors={"memory": vector})],
            embedding_mode="pre_computed",
            embedding_model="local/all-MiniLM-L6-v2",
        )
        assert state.result["pre_computed_vectors_used"] is True
        assert ltm.rows[0]["embedding"] == pytest.approx(vector)

    async def test_model_mismatch_discards_vectors(self, memory_events, keypair):
        ltm = RecordingLTM(model="openai/text-embedding-3-small", dimension=4)
        ltm, state = await self.run_batch(
            memory_events,
            keypair,
            ltm,
            events=[fact_event(embedding_vectors={"memory": [0.1, 0.2, 0.3, 0.4]})],
            embedding_mode="pre_computed",
            embedding_model="local/all-MiniLM-L6-v2",
        )
        # Graceful degradation: accepted, vectors discarded, re-embedded.
        assert state.status == RequestStatus.COMPLETED
        assert state.result["pre_computed_vectors_used"] is False
        assert ltm.rows[0]["embedding"] is None

    async def test_dimension_backstop_discards_wrong_shape(self, memory_events, keypair):
        ltm = RecordingLTM(model="local/all-MiniLM-L6-v2", dimension=4)
        ltm, state = await self.run_batch(
            memory_events,
            keypair,
            ltm,
            events=[fact_event(embedding_vectors={"memory": [0.1, 0.2]})],  # wrong dim
            embedding_mode="pre_computed",
            embedding_model="local/all-MiniLM-L6-v2",
        )
        assert state.result["pre_computed_vectors_used"] is True
        assert ltm.rows[0]["embedding"] is None  # this vector was unusable

    async def test_hybrid_events_without_vectors_are_embedded(self, memory_events, keypair):
        ltm = RecordingLTM(model="local/all-MiniLM-L6-v2", dimension=4)
        ltm, state = await self.run_batch(
            memory_events,
            keypair,
            ltm,
            events=[fact_event()],  # pre_computed batch, but no vector shipped
            embedding_mode="pre_computed",
            embedding_model="local/all-MiniLM-L6-v2",
        )
        assert ltm.rows[0]["embedding"] is None  # embedded on receipt


# ----------------------------------------------------------------------
# Quota ordering (net-new gating; idempotent retries never 429)
# ----------------------------------------------------------------------


class TestQuotaOrdering:
    async def test_all_duplicate_replay_succeeds_at_exhausted_quota(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 2})

        first = await accept(
            service,
            record,
            make_batch([fact_event(source_id="s1"), fact_event(source_id="s2")]),
        )
        await finish_job(overlord, first["processing_id"])
        # Quota is now exhausted (2/2 consumed) -- yet the full-batch
        # retry must succeed: it would create zero events, so it needs
        # zero headroom (the idempotent-retry guarantee).
        replay = await accept(
            service,
            record,
            make_batch([fact_event(source_id="s1"), fact_event(source_id="s2")]),
        )
        assert replay["accepted"] == 0
        assert replay["duplicates"] == 2
        assert replay["processing_id"] is None

    async def test_mixed_batch_needs_quota_only_for_net_new(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 3})

        first = await accept(
            service,
            record,
            make_batch([fact_event(source_id="s1"), fact_event(source_id="s2")]),
        )
        await finish_job(overlord, first["processing_id"])

        # 1 quota slot left; a 3-event batch with 2 duplicates only needs
        # headroom for its single net-new event.
        mixed = await accept(
            service,
            record,
            make_batch(
                [
                    fact_event(source_id="s1"),
                    fact_event(source_id="s2"),
                    fact_event(source_id="s3"),
                ]
            ),
        )
        assert mixed["accepted"] == 1
        assert mixed["duplicates"] == 2
        await finish_job(overlord, mixed["processing_id"])

        # Quota now exhausted: one more net-new event must 429...
        with pytest.raises(DistilleryRateLimitError):
            await accept(service, record, make_batch([fact_event(source_id="s4")]))
        # ...and the rejected batch consumed nothing: replaying the
        # already-accepted keys still succeeds.
        replay = await accept(service, record, make_batch([fact_event(source_id="s3")]))
        assert replay["duplicates"] == 1

    async def test_rejected_batch_appends_nothing(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 1})

        with pytest.raises(DistilleryRateLimitError):
            await accept(
                service,
                record,
                make_batch([fact_event(source_id="s1"), fact_event(source_id="s2")]),
            )
        # The 429 fired before any append: the substrate is untouched and
        # the full batch remains retryable.
        assert await memory_events.list_events("alice@acme.com") == []


# ----------------------------------------------------------------------
# Durable quota counters (DB-backed; restart-proof, replica-safe)
# ----------------------------------------------------------------------


class TestDurableQuota:
    async def test_quota_survives_service_restart(self, memory_events, keypair):
        # Exhaust the quota with one service instance...
        first_overlord = make_overlord(memory_events)
        first_service = MemoryDistilleryService(first_overlord)
        record = await register(first_service, keypair, scope={"max_events_per_day": 2})
        outcome = await accept(
            first_service,
            record,
            make_batch([fact_event(source_id="s1"), fact_event(source_id="s2")]),
        )
        await finish_job(first_overlord, outcome["processing_id"])

        # ...then "restart": a brand-new service instance over the same
        # database must still see the day as exhausted (the old in-process
        # dict reset to zero here; the DB counter must not).
        restarted = MemoryDistilleryService(make_overlord(memory_events))
        with pytest.raises(DistilleryRateLimitError):
            await accept(restarted, record, make_batch([fact_event(source_id="s3")]))

    async def test_quota_resets_across_days(self, memory_events, keypair, monkeypatch):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 1})

        outcome = await accept(service, record, make_batch([fact_event(source_id="s1")]))
        await finish_job(overlord, outcome["processing_id"])
        with pytest.raises(DistilleryRateLimitError):
            await accept(service, record, make_batch([fact_event(source_id="s2")]))

        # UTC day rollover: the date key changes, so the quota is fresh.
        monkeypatch.setattr(DistilleryQuotaStore, "today", staticmethod(lambda: "2999-01-01"))
        rolled = await accept(service, record, make_batch([fact_event(source_id="s2")]))
        assert rolled["accepted"] == 1
        await finish_job(overlord, rolled["processing_id"])

    async def test_concurrent_consumes_never_overshoot(self, memory_events):
        # Hammer the guarded upsert directly: 40 concurrent single-slot
        # consumers against a limit of 15 -- exactly 15 may win, and the
        # stored counter must equal the limit (no lost updates, no
        # overshoot from a check-then-act window).
        store = DistilleryQuotaStore(memory_events.db_manager, FORMATION_ID)
        day = DistilleryQuotaStore.today()
        results = await asyncio.gather(
            *(store.try_consume("dst-hammer", day, 1, 15) for _ in range(40))
        )
        assert sum(results) == 15
        assert await store.used("dst-hammer", day) == 15

    async def test_concurrent_batches_respect_limit_end_to_end(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 3})

        async def submit_one(i):
            return await accept(service, record, make_batch([fact_event(source_id=f"c{i}")]))

        outcomes = await asyncio.gather(*(submit_one(i) for i in range(6)), return_exceptions=True)
        accepted = [o for o in outcomes if isinstance(o, dict)]
        limited = [o for o in outcomes if isinstance(o, DistilleryRateLimitError)]
        unexpected = [o for o in outcomes if not isinstance(o, (dict, DistilleryRateLimitError))]
        assert unexpected == []
        assert len(accepted) == 3 and len(limited) == 3
        for outcome in accepted:
            await finish_job(overlord, outcome["processing_id"])
        assert sum(o["accepted"] for o in accepted) == 3

    async def test_batch_is_all_or_nothing(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 2})

        # A 3-event batch against a 2/day limit: rejected as a whole, and
        # the rejection consumed zero slots.
        with pytest.raises(DistilleryRateLimitError):
            await accept(
                service,
                record,
                make_batch([fact_event(source_id=f"s{i}") for i in range(3)]),
            )
        used = await service.quota_store.used(record["distillery_id"], DistilleryQuotaStore.today())
        assert used == 0

        # The full limit is still available for a fitting batch.
        fits = await accept(
            service,
            record,
            make_batch([fact_event(source_id="s0"), fact_event(source_id="s1")]),
        )
        assert fits["accepted"] == 2
        await finish_job(overlord, fits["processing_id"])

    async def test_within_batch_duplicates_release_reserved_slots(self, memory_events, keypair):
        overlord = make_overlord(memory_events)
        service = MemoryDistilleryService(overlord)
        record = await register(service, keypair, scope={"max_events_per_day": 2})

        # Two events sharing one source_id: pass 1 sees both as net-new
        # (the key isn't in the DB yet), pass 2 creates one and resolves
        # the other as a duplicate -- its reserved slot must be returned.
        outcome = await accept(
            service,
            record,
            make_batch([fact_event(source_id="dup"), fact_event(source_id="dup")]),
        )
        assert outcome["accepted"] == 1
        assert outcome["duplicates"] == 1
        await finish_job(overlord, outcome["processing_id"])
        used = await service.quota_store.used(record["distillery_id"], DistilleryQuotaStore.today())
        assert used == 1

    async def test_old_day_counters_are_pruned_on_consume(self, memory_events):
        store = DistilleryQuotaStore(memory_events.db_manager, FORMATION_ID)
        await store.try_consume("dst-old", "2020-01-01", 5, 10)
        assert await store.used("dst-old", "2020-01-01") == 5

        # A consume for today prunes day buckets past the retention window.
        day = DistilleryQuotaStore.today()
        assert await store.try_consume("dst-new", day, 1, 10)
        assert await store.used("dst-old", "2020-01-01") == 0
        assert await store.used("dst-new", day) == 1
