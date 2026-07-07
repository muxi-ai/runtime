#!/usr/bin/env python3
"""Test 2V1: Memory Ingestion Endpoint + Tiered Pipeline (Phase 3a)

This test validates the /v1/memories ingestion contract end to end:

1. Single ingest: POST /v1/memories with source/source_id returns 202
   with a processing_id; polling GET /v1/memories/ingestion/{id}
   reaches "completed" with per-stage outcomes and token usage.
2. Idempotency: replaying the same (source, source_id) returns 200 with
   duplicate: true and the original event id + derived events -- never
   a second processing run, never an error.
3. Batch ingest: POST /v1/memories/batch with a fresh item, a duplicate,
   an invalid item, and a noisy item returns per-item statuses in order;
   the noisy item (unconfigured source -> strict gate) is filtered with
   its disposition recorded as an ingestion.filtered event.
4. Events carry provenance: memory.ingested events hold the developer's
   source/source_id; derived fact.extracted events link via caused_by
   and carry the true source.
5. Ingested facts are recallable in a real chat.
6. Replay: wipe-and-rebuild of the flat-facts projection reproduces the
   ingested state from the event log.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_memory_test import BaseMemoryTest  # noqa: E402

BASE_URL = "http://127.0.0.1:8273/v1"
CLIENT_HEADERS = {
    "X-Muxi-Client-Key": "test-client-key-2v1",
    "X-Muxi-User-ID": "0",  # sqlite formation runs in single-user mode
    "Content-Type": "application/json",
}
USER_ID = "0"

TEA_FACT = "My favorite tea is Earl Grey and I drink a cup every morning."
WORK_FACT = "I am leading the Atlas migration project at work, due at the end of Q3."
NOISE_ITEM = "ALERT: CPU usage above 90% on host web-03 for 15 minutes."


async def poll_status(client, processing_id, timeout=180.0):
    """Poll the ingestion status endpoint until a terminal status."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = await client.get(
            f"{BASE_URL}/memories/ingestion/{processing_id}", headers=CLIENT_HEADERS
        )
        assert r.status_code == 200, f"status poll: {r.status_code} {r.text}"
        last = r.json()["data"]
        if last["status"] in ("completed", "failed"):
            return last
        await asyncio.sleep(2)
    raise TimeoutError(f"Ingestion {processing_id} did not finish in {timeout}s: {last}")


def snapshot_ingested_facts(long_term_memory, internal_user_id):
    """Event-derived flat-fact rows (rows carrying derived_from_event_id)."""
    import json

    rows = long_term_memory.conn.execute(
        f"""
        SELECT text, collection, metadata FROM {long_term_memory.memories_table}
        WHERE user_id = ?
          AND json_extract(metadata, '$.derived_from_event_id') IS NOT NULL
        ORDER BY text
        """,
        (internal_user_id,),
    ).fetchall()
    normalized = []
    for text, collection, metadata in rows:
        meta = json.loads(metadata or "{}")
        meta.pop("timestamp", None)  # storage-assigned write time
        normalized.append((text, collection, tuple(sorted(meta.items()))))
    return normalized


class TestMemoryIngestion(BaseMemoryTest):
    """Validate the ingestion contract, pipeline, events, and replay."""

    async def test_memory_ingestion(self):
        test_name = "2v1_memory_ingestion"
        self.print_test_header(
            test_name, "Memory ingestion endpoint: idempotent accept, pipeline, events, replay"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Fresh database for deterministic assertions (sqlite db lands
            # in this test's working directory).
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"ingestion_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Formation with sqlite memory + API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formations" / "formation-ingestion"
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)

            memory_events = getattr(self.overlord, "memory_events", None)
            assert memory_events is not None, "memory event substrate missing"
            assert getattr(self.overlord, "memory_ingestion", None) is not None
            print("  ✓ Ingestion service and event substrate wired")
            checks_passed.append("Ingestion service wired")

            print("\n📨 Phase 2: Single ingest -> poll to completed...")
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=CLIENT_HEADERS,
                    json={
                        "content": TEA_FACT,
                        "source": "notes",
                        "source_id": "note-1",
                        "timestamp": "2026-07-01T09:00:00Z",
                        "metadata": {"channel": "e2e"},
                    },
                )
                assert r.status_code == 202, f"ingest: {r.status_code} {r.text}"
                data = r.json()["data"]
                assert data["status"] == "accepted", data
                assert data["duplicate"] is False, data
                processing_id = data["processing_id"]
                assert data["status_url"].endswith(processing_id), data
                print(f"  ✓ 202 accepted with processing_id {processing_id}")
                checks_passed.append("Single ingest accepted (202 + processing_id)")

                status = await poll_status(client, processing_id)
                assert status["status"] == "completed", status
                item = status["items"][0]
                assert item["disposition"] == "stored", item
                assert item["classification"]["category"], item
                assert "filter_level" in item, item
                assert "usage" in status and "total" in status["usage"], status
                print(
                    f"  ✓ Completed: disposition={item['disposition']}, "
                    f"category={item['classification']['category']}, "
                    f"tokens={status['usage']['total'][0]}"
                )
                checks_passed.append("Status lifecycle reaches completed with stage outcomes")
                checks_passed.append("Cost attribution (token usage) reported")

                print("\n🔁 Phase 3: Idempotent replay of the same (source, source_id)...")
                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=CLIENT_HEADERS,
                    json={"content": TEA_FACT, "source": "notes", "source_id": "note-1"},
                )
                assert r.status_code == 200, f"replay: {r.status_code} {r.text}"
                dup = r.json()["data"]
                assert dup["duplicate"] is True, dup
                assert dup["status"] == "duplicate", dup
                assert "processing_id" not in dup, dup
                derived_types = {d["event_type"] for d in dup.get("derived_events", [])}
                assert "fact.extracted" in derived_types, dup
                print("  ✓ Replay returned duplicate: true + original derived events")
                checks_passed.append("Idempotent replay returns original result (200)")

                print("\n📦 Phase 4: Batch ingest (fresh + duplicate + invalid + noise)...")
                r = await client.post(
                    f"{BASE_URL}/memories/batch",
                    headers=CLIENT_HEADERS,
                    json={
                        "items": [
                            {"content": WORK_FACT, "source": "notes", "source_id": "note-2"},
                            {"content": TEA_FACT, "source": "notes", "source_id": "note-1"},
                            {"content": "item without a source"},
                            {
                                "content": NOISE_ITEM,
                                "source": "monitoring",
                                "source_id": "alert-1",
                            },
                        ]
                    },
                )
                assert r.status_code == 200, f"batch: {r.status_code} {r.text}"
                batch = r.json()["data"]
                statuses = [i["status"] for i in batch["items"]]
                assert statuses == ["accepted", "duplicate", "invalid", "accepted"], batch
                assert [i["index"] for i in batch["items"]] == [0, 1, 2, 3], batch
                assert batch["counts"] == {"accepted": 2, "duplicate": 1, "invalid": 1}, batch
                assert "'source' is required" in batch["items"][2]["error"], batch
                print(f"  ✓ Per-item statuses in order: {statuses}")
                checks_passed.append("Batch per-item statuses (accepted/duplicate/invalid)")

                batch_status = await poll_status(client, batch["processing_id"])
                assert batch_status["status"] == "completed", batch_status
                by_index = {i["index"]: i for i in batch_status["items"]}
                assert by_index[0]["disposition"] == "stored", by_index
                assert by_index[3]["disposition"] == "filtered", by_index
                assert by_index[3]["filter_level"] == "strict", by_index
                print(
                    f"  ✓ Batch completed: work fact stored, monitoring alert filtered "
                    f"(category={by_index[3]['classification']['category']})"
                )
                checks_passed.append("Pipeline stores kept items and filters noise")

            print("\n🗄️  Phase 5: Events carry source/source_id + dispositions...")
            events = await memory_events.list_events(USER_ID)
            ingested = [e for e in events if e["event_type"] == "memory.ingested"]
            keys = {(e["source"], e["source_id"]) for e in ingested}
            assert ("notes", "note-1") in keys, keys
            assert ("notes", "note-2") in keys, keys
            assert ("monitoring", "alert-1") in keys, keys
            assert len([e for e in ingested if e["source_id"] == "note-1"]) == 1, (
                "duplicate replay must not append a second raw event"
            )
            print(f"  ✓ memory.ingested events carry (source, source_id): {sorted(keys)}")
            checks_passed.append("Raw events carry source/source_id (no duplicates)")

            filtered = [e for e in events if e["event_type"] == "ingestion.filtered"]
            alert_event = next(e for e in ingested if e["source_id"] == "alert-1")
            assert filtered, "expected an ingestion.filtered disposition event"
            assert any(e["caused_by"] == alert_event["id"] for e in filtered), filtered
            print("  ✓ Filtered disposition recorded as event with caused_by provenance")
            checks_passed.append("Filtered dispositions recorded as events")

            facts = [e for e in events if e["event_type"] == "fact.extracted"]
            note1 = next(e for e in ingested if e["source_id"] == "note-1")
            linked = [e for e in facts if e["caused_by"] == note1["id"]]
            assert linked, "expected fact.extracted events derived from note-1"
            assert all(e["source"] == "notes" for e in linked), linked
            print("  ✓ Derived facts link caused_by -> raw event and carry source 'notes'")
            checks_passed.append("Derived facts carry provenance + true source")

            # Let fire-and-forget writes settle before snapshotting.
            await asyncio.sleep(10)

            print("\n🔄 Phase 6: Replay reproduces ingested state...")
            long_term_memory = self.overlord.long_term_memory
            internal_user_id = await long_term_memory.get_or_create_user(USER_ID)
            before = snapshot_ingested_facts(long_term_memory, internal_user_id)
            assert before, "expected event-derived fact rows before the rebuild"

            report = await memory_events.rebuild(USER_ID, projection="flat_facts")
            print(f"  Rebuild report: {report}")
            assert report["flat_facts"]["failed"] == 0, report
            after = snapshot_ingested_facts(long_term_memory, internal_user_id)
            if after == before:
                print(f"  ✓ Wipe-and-replay reproduced {len(before)} event-derived fact rows")
                checks_passed.append("Replay reproduces ingested state")
            else:
                print(f"  ✗ Replay diverged:\n    before: {before}\n    after: {after}")
                all_passed = False

            print("\n💬 Phase 7: Ingested facts recallable in chat...")
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
                print("  ✓ Chat recalled the ingested tea fact")
                checks_passed.append("Ingested facts recallable in chat")
            else:
                print("  ✗ Chat did not recall the ingested fact")
                all_passed = False

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
        print("📥 AREA 2V1: MEMORY INGESTION ENDPOINT + PIPELINE")
        print("=" * 60)

        all_passed = await self.test_memory_ingestion()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- (source, source_id) is an exact idempotency key: replays return the original")
        print("- The pipeline classifies locally, gates noise per source, extracts via LLM")
        print("- Every stage leaves events: raw content, dispositions, derived facts")
        print("- Wipe-and-replay reproduces ingested memory from the event log")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestMemoryIngestion()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
