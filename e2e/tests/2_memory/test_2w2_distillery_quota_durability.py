#!/usr/bin/env python3
"""Test 2W2: Distillery Quota Durability Across Restarts

This test validates that daily distilled-submission quotas are durable
(DB-backed distillery_quota_counters, PR #304) instead of the old
in-memory dict that reset on every restart:

1. Registration with a small quota: a distillery registered with
   scope.max_events_per_day=3 gets that limit enforced.
2. Pre-restart consumption: a signed batch of 2 events is accepted and
   the durable counter records 2 used slots.
3. Restart: the formation (and its API server) is torn down and a fresh
   Formation instance is loaded on the same SQLite database -- a fresh
   MemoryDistilleryService and DistilleryQuotaStore with no in-process
   state.
4. Durability: after the restart the counter still reads 2, and a batch
   of 2 net-new events (which would take the day to 4 > 3) is rejected
   with 429 and lands nothing. Before PR #304 the counter reset to zero
   on restart and this batch would have sailed through.
5. No starvation: ground-truth reconciliation must not eat legitimate
   headroom -- a batch of 1 net-new event (day total 3 <= 3) is
   accepted after the restart.
6. Exhaustion + duplicate immunity: once the quota is fully consumed a
   further net-new event gets 429, but replaying an already-accepted
   batch (all duplicates, zero net-new) still succeeds.
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
from test_utils import safe_formation_shutdown  # noqa: E402

from muxi.runtime.services.memory.distillery import signed_message  # noqa: E402
from muxi.runtime.utils.fastjson import json  # noqa: E402

BASE_URL = "http://127.0.0.1:8276/v1"
ADMIN_HEADERS = {
    "X-Muxi-Admin-Key": "test-admin-key-2w2",
    "Content-Type": "application/json",
}
CLIENT_HEADERS = {
    "X-Muxi-Client-Key": "test-client-key-2w2",
    "Content-Type": "application/json",
}
USER_ID = "0"  # single-user formation
DAILY_QUOTA = 3
FORMATION_PATH = Path(__file__).parent / "formations" / "formation-distillery-quota"
DB_NAME = "distillery_quota_test.db"


def make_batch(batch_id: str, source_ids: list) -> dict:
    """One distilled batch of valid fact events, one per source_id."""
    return {
        "batch_id": batch_id,
        "distillery_version": "1.0.0",
        "embedding_mode": "none",
        "events": [
            {
                "event_type": "fact.extracted",
                "user_id": USER_ID,
                "source": "distillery",
                "source_id": source_id,
                "source_confidence": 0.9,
                "decay_rate": "static",
                "payload": {
                    "memory": f"Quota durability fact {source_id}.",
                    "collection": "context",
                },
            }
            for source_id in source_ids
        ],
    }


def sign_batch(private_key, distillery_id: str, body: bytes) -> dict:
    """Distillery-side signing: Ed25519 over domain + timestamp + id + body."""
    timestamp = int(time.time())
    signature = private_key.sign(signed_message(str(timestamp), distillery_id, body))
    return {
        "X-Distillery-ID": distillery_id,
        "X-Distillery-Timestamp": str(timestamp),
        "X-Distillery-Signature": base64.b64encode(signature).decode(),
    }


async def submit_batch(client, private_key, distillery_id: str, batch: dict):
    """POST one freshly signed distilled batch; returns the response."""
    body = json.dumps(batch).encode("utf-8")
    headers = {**CLIENT_HEADERS, **sign_batch(private_key, distillery_id, body)}
    return await client.post(f"{BASE_URL}/memories/distilled", headers=headers, content=body)


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


class TestDistilleryQuotaDurability(BaseMemoryTest):
    """Validate the durable daily quota counter across a formation restart."""

    async def start(self):
        """Load the formation and start its API server (fresh instance)."""
        await self.setup_formation(formation_path=FORMATION_PATH)
        self.server = await self.formation.start_server(block=False)
        await asyncio.sleep(2)

    async def restart(self):
        """Tear down the running formation and load a fresh one on the same DB."""
        if getattr(self, "server", None) is not None:
            await self.server.stop()
            self.server = None
        await safe_formation_shutdown(self.formation, timeout=15.0)
        self.formation = None
        self.overlord = None
        await asyncio.sleep(1)
        await self.start()

    async def distilled_event_count(self) -> int:
        """Live distilled events in the substrate (quota ground truth)."""
        events = await self.overlord.memory_events.list_events(USER_ID)
        return len([e for e in events if e["source"] == "distillery"])

    async def quota_used(self, distillery_id: str) -> int:
        """Read the durable counter directly from the current service."""
        store = self.overlord.memory_distillery.quota_store
        return await store.used(distillery_id, store.today())

    async def test_quota_durability(self):
        test_name = "2w2_distillery_quota_durability"
        self.print_test_header(
            test_name, "Distillery daily quota survives a formation restart (durable counters)"
        )

        start_time = time.time()
        checks_passed = []
        all_passed = True
        self.server = None

        private_key = Ed25519PrivateKey.generate()
        public_der = private_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo
        )
        public_key = "ed25519:" + base64.b64encode(public_der).decode()

        try:
            # Fresh database for deterministic quota arithmetic.
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"{DB_NAME}{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Formation + API server (first instance)...")
            await self.start()
            assert self.overlord.memory_distillery is not None
            assert self.overlord.memory_distillery.enabled
            print("  ✓ Distillery service enabled")
            checks_passed.append("Distillery service wired (memory.distillery.enabled)")

            async with httpx.AsyncClient(timeout=90.0) as client:
                print(f"\n🔑 Phase 2: Register distillery with max_events_per_day={DAILY_QUOTA}...")
                r = await client.post(
                    f"{BASE_URL}/memory/distilleries",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "E2E Quota Test Distillery",
                        "description": "Durable quota distillery simulated by test 2W2",
                        "public_key": public_key,
                        "scope": {"user_ids": "all", "max_events_per_day": DAILY_QUOTA},
                    },
                )
                assert r.status_code == 201, f"register: {r.status_code} {r.text}"
                record = r.json()["data"]
                distillery_id = record["distillery_id"]
                assert record["scope"]["max_events_per_day"] == DAILY_QUOTA, record
                print(f"  ✓ Registered {distillery_id} with daily quota {DAILY_QUOTA}")
                checks_passed.append("Registration stores scope.max_events_per_day")

                print("\n📦 Phase 3: Consume 2 of 3 quota slots before the restart...")
                batch_a = make_batch("batch-2w2-a", ["quota-a-1", "quota-a-2"])
                r = await submit_batch(client, private_key, distillery_id, batch_a)
                assert r.status_code == 202, f"batch A: {r.status_code} {r.text}"
                data = r.json()["data"]
                assert data["accepted"] == 2, data
                assert data["rejected"] == 0, data
                status = await poll_status(client, data["processing_id"])
                assert status["status"] == "completed", status
                print("  ✓ Batch A accepted (2 events) and projected")
                checks_passed.append("Pre-restart batch accepted (2 of 3 slots consumed)")

                used = await self.quota_used(distillery_id)
                assert used == 2, f"expected 2 used slots before restart, got {used}"
                print(f"  ✓ Durable counter reads {used}/{DAILY_QUOTA} before restart")
                checks_passed.append("Durable counter records consumption (2 used)")

            print("\n🔄 Phase 4: Restart the formation on the same database...")
            await self.restart()
            assert self.overlord.memory_distillery is not None
            print("  ✓ Fresh Formation + MemoryDistilleryService on the same SQLite DB")
            checks_passed.append("Formation restarted (fresh service, same database)")

            used = await self.quota_used(distillery_id)
            assert used == 2, f"counter did not survive the restart: expected 2, got {used}"
            print(f"  ✓ Counter survived the restart: {used}/{DAILY_QUOTA} used")
            checks_passed.append("Quota counter survives restart (still 2 used)")

            async with httpx.AsyncClient(timeout=90.0) as client:
                print("\n🚫 Phase 5: Over-quota batch after restart -> 429...")
                batch_b = make_batch("batch-2w2-b", ["quota-b-1", "quota-b-2"])
                r = await submit_batch(client, private_key, distillery_id, batch_b)
                assert r.status_code == 429, (
                    f"expected 429 for over-quota batch after restart "
                    f"(counter must not reset), got {r.status_code}: {r.text}"
                )
                assert "quota" in r.text.lower(), r.text
                events = await self.distilled_event_count()
                assert events == 2, f"429 batch leaked events into the substrate: {events}"
                print("  ✓ 2 net-new events (day total 4 > 3) rejected with 429, nothing landed")
                checks_passed.append("Post-restart over-quota batch rejected with 429")

                print("\n✅ Phase 6: Batch within remaining headroom -> accepted...")
                batch_c = make_batch("batch-2w2-c", ["quota-c-1"])
                r = await submit_batch(client, private_key, distillery_id, batch_c)
                assert r.status_code == 202, (
                    f"reconciliation starved a legitimate submission: " f"{r.status_code} {r.text}"
                )
                data = r.json()["data"]
                assert data["accepted"] == 1, data
                status = await poll_status(client, data["processing_id"])
                assert status["status"] == "completed", status
                used = await self.quota_used(distillery_id)
                assert used == DAILY_QUOTA, f"expected {DAILY_QUOTA} used, got {used}"
                events = await self.distilled_event_count()
                assert events == 3, f"expected 3 distilled events, got {events}"
                print(f"  ✓ 1 net-new event accepted; quota now {used}/{DAILY_QUOTA}")
                checks_passed.append("Post-restart in-quota batch accepted (no starvation)")

                print("\n🧱 Phase 7: Exhausted quota -> 429; duplicate replay still OK...")
                batch_d = make_batch("batch-2w2-d", ["quota-d-1"])
                r = await submit_batch(client, private_key, distillery_id, batch_d)
                assert r.status_code == 429, f"exhausted quota: {r.status_code} {r.text}"
                print("  ✓ Net-new event on an exhausted quota rejected with 429")
                checks_passed.append("Exhausted quota rejects further net-new events")

                # A full-duplicate retry consumes no quota and must always
                # succeed, even with the day's quota fully consumed.
                r = await submit_batch(client, private_key, distillery_id, batch_a)
                assert r.status_code == 200, f"duplicate replay: {r.status_code} {r.text}"
                dup = r.json()["data"]
                assert dup["accepted"] == 0, dup
                assert dup["duplicates"] == 2, dup
                used = await self.quota_used(distillery_id)
                assert used == DAILY_QUOTA, f"duplicate replay consumed quota: {used}"
                print("  ✓ Full-duplicate replay succeeds without consuming quota")
                checks_passed.append("Duplicate replay immune to exhausted quota")

        except Exception as e:
            import traceback

            print(f"  ✗ Test failed with error: {e}")
            traceback.print_exc()
            all_passed = False

        finally:
            if getattr(self, "server", None) is not None:
                try:
                    await self.server.stop()
                except Exception:
                    pass
                self.server = None
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, [], duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🏭 AREA 2W2: DISTILLERY QUOTA DURABILITY")
        print("=" * 60)

        all_passed = await self.test_quota_durability()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Daily quotas live in distillery_quota_counters, not process memory")
        print("- A restart cannot reset the day's consumption (no quota laundering)")
        print("- Reconciliation heals leaked reservations without starving real headroom")
        print("- Full-duplicate retries never consume quota, even when exhausted")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestDistilleryQuotaDurability()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
