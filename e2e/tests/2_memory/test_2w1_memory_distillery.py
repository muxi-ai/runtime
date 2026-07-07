#!/usr/bin/env python3
"""Test 2W1: Memory Distillery Endpoint (Phase 3b)

This test validates the /v1/memories/distilled contract end to end:

1. Registration: POST /v1/memory/distilleries (admin) registers a
   distillery with a real Ed25519 public key and returns its
   distillery_id; the trust registry lists it.
2. Fail-closed auth: unsigned batches, bad signatures, stale timestamps
   (replay protection), and unknown distillery ids are all rejected with
   401 -- no partial acceptance, nothing lands.
3. Signed intake: a properly signed batch (facts + a log entry + one
   invalid event) returns 202 with partial acceptance (indexed rejection
   reason); polling GET /v1/memories/distilled/{processing_id} reaches
   "completed" with per-event dispositions.
4. Substrate + projections: accepted events land in memory_events with
   source="distillery" and the event's own user scope; fact rows appear
   in the flat-fact projection with derived_from_event_id provenance.
5. Idempotency: replaying the same batch (fresh signature) creates zero
   new events -- everything reported as duplicates, no second job.
6. Recall: a distilled fact is recallable in a real chat.
7. Revocation: after DELETE /v1/memory/distilleries/{id}, a freshly
   signed batch is rejected with 410 Gone.
"""

import asyncio
import base64
import os
import sys
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_memory_test import BaseMemoryTest  # noqa: E402

from muxi.runtime.services.memory.distillery import signed_message  # noqa: E402
from muxi.runtime.utils.fastjson import json  # noqa: E402

BASE_URL = "http://127.0.0.1:8274/v1"
ADMIN_HEADERS = {
    "X-Muxi-Admin-Key": "test-admin-key-2w1",
    "Content-Type": "application/json",
}
CLIENT_HEADERS = {
    "X-Muxi-Client-Key": "test-client-key-2w1",
    "Content-Type": "application/json",
}
USER_ID = "0"  # single-user formation

TEA_FACT = "My favorite tea is Earl Grey and I drink a cup every morning."
WORK_FACT = "I am leading the Atlas migration project at work, due at the end of Q3."


def make_batch(batch_id: str) -> dict:
    """One distilled batch: two facts, one log entry, one invalid event."""
    return {
        "batch_id": batch_id,
        "distillery_version": "1.0.0",
        "embedding_mode": "none",
        "events": [
            {
                "event_type": "fact.extracted",
                "user_id": USER_ID,
                "source": "distillery",
                "source_id": "note-tea-1",
                "occurred_at": "2026-07-01T09:00:00Z",
                "source_confidence": 0.95,
                "decay_rate": "static",
                # The distillery declares the collection per fact; chat
                # recall searches the standard collections (preferences,
                # activities, ...), so a well-behaved distillery labels
                # facts with the vocabulary from MEMORY_COLLECTIONS.
                "payload": {"memory": TEA_FACT, "collection": "preferences"},
            },
            {
                "event_type": "fact.extracted",
                "user_id": USER_ID,
                "source_id": "note-work-2",
                "decay_rate": "decaying",
                "payload": {"memory": WORK_FACT, "collection": "context"},
            },
            {
                "event_type": "log.entry",
                "user_id": USER_ID,
                "source_id": "digest-2026-07-06",
                "payload": {
                    "date": "2026-07-06",
                    "summary": "Kicked off the Atlas migration and set the Q3 deadline.",
                },
            },
            {
                # Invalid: fact payload missing the required "memory" key.
                "event_type": "fact.extracted",
                "user_id": USER_ID,
                "source_id": "note-bad-3",
                "payload": {"collection": "context"},
            },
        ],
    }


def sign_batch(private_key, distillery_id: str, body: bytes, timestamp: int = None) -> dict:
    """Distillery-side signing: Ed25519 over domain + timestamp + id + body."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    signature = private_key.sign(signed_message(str(timestamp), distillery_id, body))
    return {
        "X-Distillery-ID": distillery_id,
        "X-Distillery-Timestamp": str(timestamp),
        "X-Distillery-Signature": base64.b64encode(signature).decode(),
    }


async def poll_status(client, processing_id, timeout=120.0):
    """Poll the distilled status endpoint until a terminal status."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = await client.get(
            f"{BASE_URL}/memories/distilled/{processing_id}", headers=ADMIN_HEADERS
        )
        assert r.status_code == 200, f"status poll: {r.status_code} {r.text}"
        last = r.json()["data"]
        if last["status"] in ("completed", "failed"):
            return last
        await asyncio.sleep(2)
    raise TimeoutError(f"Distilled job {processing_id} did not finish in {timeout}s: {last}")


class TestMemoryDistillery(BaseMemoryTest):
    """Validate registration, signed intake, projections, and revocation."""

    async def test_memory_distillery(self):
        test_name = "2w1_memory_distillery"
        self.print_test_header(
            test_name, "Memory distillery: signed batches, verification, projections, recall"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        private_key = Ed25519PrivateKey.generate()
        public_der = private_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        public_key = "ed25519:" + base64.b64encode(public_der).decode()

        try:
            # Fresh database for deterministic assertions.
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"distillery_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Formation with distillery config + API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formations" / "formation-distillery"
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)

            memory_events = getattr(self.overlord, "memory_events", None)
            assert memory_events is not None, "memory event substrate missing"
            distillery_service = getattr(self.overlord, "memory_distillery", None)
            assert distillery_service is not None and distillery_service.enabled
            print("  ✓ Distillery service enabled and event substrate wired")
            checks_passed.append("Distillery service wired (memory.distillery.enabled)")

            async with httpx.AsyncClient(timeout=90.0) as client:
                print("\n🔑 Phase 2: Register the distillery (admin API)...")
                r = await client.post(
                    f"{BASE_URL}/memory/distilleries",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "E2E Test Distillery",
                        "description": "On-prem distillery simulated by test 2W1",
                        "public_key": public_key,
                        "scope": {"user_ids": "all"},
                    },
                )
                assert r.status_code == 201, f"register: {r.status_code} {r.text}"
                record = r.json()["data"]
                distillery_id = record["distillery_id"]
                assert record["trust_level"] == "verified", record
                assert record["status"] == "active", record
                print(f"  ✓ Registered distillery {distillery_id} (trust: verified)")
                checks_passed.append("Distillery registration returns distillery_id")

                r = await client.get(f"{BASE_URL}/memory/distilleries", headers=ADMIN_HEADERS)
                assert r.status_code == 200, r.text
                listed = r.json()["data"]["distilleries"]
                assert any(d["distillery_id"] == distillery_id for d in listed), listed
                print("  ✓ Registry lists the registration")
                checks_passed.append("Registry lists registered distilleries")

                print("\n🚫 Phase 3: Fail-closed authentication...")
                batch = make_batch("batch-2w1-001")
                body = json.dumps(batch).encode("utf-8")

                # Unsigned (missing distillery headers entirely).
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=CLIENT_HEADERS, content=body
                )
                assert r.status_code == 401, f"unsigned: {r.status_code} {r.text}"
                print("  ✓ Unsigned batch rejected (401)")
                checks_passed.append("Unsigned batch rejected with 401")

                # Signed by the wrong key.
                wrong_key = Ed25519PrivateKey.generate()
                headers = {**CLIENT_HEADERS, **sign_batch(wrong_key, distillery_id, body)}
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=headers, content=body
                )
                assert r.status_code == 401, f"bad signature: {r.status_code} {r.text}"
                print("  ✓ Bad signature rejected (401)")
                checks_passed.append("Bad signature rejected with 401")

                # Valid signature, tampered body.
                headers = {**CLIENT_HEADERS, **sign_batch(private_key, distillery_id, body)}
                r = await client.post(
                    f"{BASE_URL}/memories/distilled",
                    headers=headers,
                    content=body + b" ",
                )
                assert r.status_code == 401, f"tampered body: {r.status_code} {r.text}"
                print("  ✓ Tampered body rejected (401)")
                checks_passed.append("Tampered body rejected with 401")

                # Stale timestamp (outside the replay window).
                stale = int(time.time()) - 3600
                headers = {
                    **CLIENT_HEADERS,
                    **sign_batch(private_key, distillery_id, body, timestamp=stale),
                }
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=headers, content=body
                )
                assert r.status_code == 401, f"replay: {r.status_code} {r.text}"
                print("  ✓ Stale timestamp rejected (401 replay protection)")
                checks_passed.append("Replayed (stale) timestamp rejected with 401")

                # Unknown distillery id.
                headers = {**CLIENT_HEADERS, **sign_batch(private_key, "unknown-dst", body)}
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=headers, content=body
                )
                assert r.status_code == 401, f"unknown id: {r.status_code} {r.text}"
                print("  ✓ Unknown distillery id rejected (401)")
                checks_passed.append("Unknown distillery id rejected with 401")

                # Nothing landed while auth was failing.
                events = await memory_events.list_events(USER_ID)
                assert events == [], f"events leaked through failed auth: {events}"
                print("  ✓ No events landed from rejected batches")
                checks_passed.append("Failed auth lands zero events")

                print("\n📦 Phase 4: Signed batch -> partial acceptance -> completed...")
                headers = {**CLIENT_HEADERS, **sign_batch(private_key, distillery_id, body)}
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=headers, content=body
                )
                assert r.status_code == 202, f"signed intake: {r.status_code} {r.text}"
                data = r.json()["data"]
                assert data["accepted"] == 3, data
                assert data["duplicates"] == 0, data
                assert data["rejected"] == 1, data
                assert data["rejections"][0]["index"] == 3, data
                assert "invalid event schema" in data["rejections"][0]["reason"], data
                processing_id = data["processing_id"]
                print(
                    f"  ✓ 202 accepted: 3 events, 1 indexed rejection "
                    f"({data['rejections'][0]['reason'][:50]}...)"
                )
                checks_passed.append("Signed batch accepted (202, partial acceptance)")

                status = await poll_status(client, processing_id)
                assert status["status"] == "completed", status
                assert status["counts"]["projected"] == 3, status
                assert status["counts"]["failed"] == 0, status
                print(f"  ✓ Projection job completed: {status['counts']}")
                checks_passed.append("Projection job completes with per-event dispositions")

                print("\n🔁 Phase 5: Idempotent replay (fresh signature, same batch)...")
                headers = {**CLIENT_HEADERS, **sign_batch(private_key, distillery_id, body)}
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=headers, content=body
                )
                assert r.status_code == 200, f"replay: {r.status_code} {r.text}"
                dup = r.json()["data"]
                assert dup["accepted"] == 0, dup
                assert dup["duplicates"] == 3, dup
                assert dup["processing_id"] is None, dup
                print("  ✓ Replay created nothing: 3 duplicates, no new job")
                checks_passed.append("Idempotent replay: zero duplicates created")

            print("\n🗄️  Phase 6: Events + projections carry distillery provenance...")
            events = await memory_events.list_events(USER_ID)
            distilled = [e for e in events if e["source"] == "distillery"]
            keys = {e["source_id"] for e in distilled}
            assert keys == {"note-tea-1", "note-work-2", "digest-2026-07-06"}, keys
            assert all(e["scope_type"] == "user" for e in distilled), distilled
            tea = next(e for e in distilled if e["source_id"] == "note-tea-1")
            assert tea["source_confidence"] == 0.95, tea
            assert tea["occurred_at"].startswith("2026-07-01T09:00:00"), tea
            print(f"  ✓ memory_events carry source=distillery + source_ids: {sorted(keys)}")
            checks_passed.append("Events carry distillery source + idempotency keys")

            long_term_memory = self.overlord.long_term_memory
            internal_user_id = await long_term_memory.get_or_create_user(USER_ID)
            rows = long_term_memory.conn.execute(
                f"""
                SELECT text FROM {long_term_memory.memories_table}
                WHERE user_id = ?
                  AND json_extract(metadata, '$.derived_from_event_id') IS NOT NULL
                ORDER BY text
                """,
                (internal_user_id,),
            ).fetchall()
            texts = [row[0] for row in rows]
            assert TEA_FACT in texts and WORK_FACT in texts, texts
            print(f"  ✓ Flat-fact projection holds {len(texts)} distilled fact rows")
            checks_passed.append("Projections updated (facts with provenance)")

            captains_log = getattr(self.overlord, "captains_log", None)
            if captains_log is not None:
                history = await captains_log.get_history(USER_ID, limit=5)
                assert any("Atlas" in (e.get("summary") or "") for e in history), history
                print("  ✓ Captain's log projection holds the distilled log entry")
                checks_passed.append("Captain's log entry projected")

            print("\n💬 Phase 7: Distilled facts recallable in chat...")
            recall_msg = "What is my favorite tea?"
            response = await self.overlord.chat(
                recall_msg,
                agent_name="assistant",
                user_id=USER_ID,
                use_async=False,
                stream=False,
            )
            recall_text = response.content if hasattr(response, "content") else str(response)
            transcript.append((recall_msg, recall_text))
            print(f"  User: {recall_msg}")
            print(f"  Assistant: {recall_text[:200]}")
            if "earl grey" in recall_text.lower():
                print("  ✓ Chat recalled the distilled tea fact")
                checks_passed.append("Distilled facts recallable in chat")
            else:
                print("  ✗ Chat did not recall the distilled fact")
                all_passed = False

            print("\n🛑 Phase 8: Revocation -> 410 Gone...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.delete(
                    f"{BASE_URL}/memory/distilleries/{distillery_id}", headers=ADMIN_HEADERS
                )
                assert r.status_code == 200, f"revoke: {r.status_code} {r.text}"
                assert r.json()["data"]["status"] == "revoked"

                fresh = make_batch("batch-2w1-002")
                fresh_body = json.dumps(fresh).encode("utf-8")
                headers = {
                    **CLIENT_HEADERS,
                    **sign_batch(private_key, distillery_id, fresh_body),
                }
                r = await client.post(
                    f"{BASE_URL}/memories/distilled", headers=headers, content=fresh_body
                )
                assert r.status_code == 410, f"revoked: {r.status_code} {r.text}"
                print("  ✓ Revoked distillery gets 410 Gone; previous events retained")
                checks_passed.append("Revocation: subsequent batches rejected with 410")

        except Exception as e:
            import traceback

            print(f"  ✗ Test failed with error: {e}")
            traceback.print_exc()
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🏭 AREA 2W1: MEMORY DISTILLERY ENDPOINT")
        print("=" * 60)

        all_passed = await self.test_memory_distillery()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Distilleries authenticate via registration + Ed25519 over the raw body")
        print("- Verification fails closed: bad/missing/stale signatures land nothing")
        print("- Accepted events ride the substrate: idempotent, user-scoped, replayable")
        print("- MUXI does no extraction for distilled batches: verify, embed, append")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestMemoryDistillery()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
