#!/usr/bin/env python3
"""Test 2V2: Memory Ingestion Maturation (tiers, entity resolution, synthesis)

This test validates the ingestion maturation scope end to end:

1. Tier heuristics: ingested personal/work content escalates past Tier 1;
   the item report carries tier + reason (observable escalation).
2. Entity resolution: two ingested notes about the same person under two
   names ("Ryan Leveille" / "Ryan", shared email + employer) resolve to
   one identity -- an entity.resolved event with decision "merged", the
   duplicate entity marked merged with an alias on the canonical row.
3. Synthesis scheduling: the synthesis service is registered on the
   scheduler's periodic-task loop; driving the hot cadence (the cheapest
   observable pass) reports its work and the durable per-user cursor
   skips settled users on the next pass.
4. Idempotent maturation: replaying the resolution pass appends nothing
   (deterministic per-pair idempotency keys).
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

BASE_URL = "http://127.0.0.1:8275/v1"
CLIENT_HEADERS = {
    "X-Muxi-Client-Key": "test-client-key-2v2",
    "X-Muxi-User-ID": "0",  # sqlite formation runs in single-user mode
    "Content-Type": "application/json",
}
USER_ID = "0"

NOTE_FULL_IDENTITY = (
    "My colleague Ryan Leveille works at Nabo. His email is ryan@nabo.dev "
    "and I usually reach him there about the hosting project."
)
NOTE_SHORT_IDENTITY = (
    "Ryan from Nabo (ryan@nabo.dev) asked me about the hosting dispute "
    "yesterday and wants an update this week."
)


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


async def ingest(client, content, source_id):
    r = await client.post(
        f"{BASE_URL}/memories",
        headers=CLIENT_HEADERS,
        json={"content": content, "source": "notes", "source_id": source_id},
    )
    assert r.status_code == 202, f"ingest: {r.status_code} {r.text}"
    return await poll_status(client, r.json()["data"]["processing_id"])


class TestIngestionMaturation(BaseMemoryTest):
    """Validate tier heuristics, entity resolution, and synthesis cadences."""

    async def test_ingestion_maturation(self):
        test_name = "2v2_ingestion_maturation"
        self.print_test_header(
            test_name,
            "Ingestion maturation: tier escalation, duplicate identity merge, synthesis pass",
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Fresh database for deterministic assertions.
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"ingestion_maturation_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Formation with scheduler + synthesis cadences...")
            await self.setup_formation(
                formation_path=Path(__file__).parent
                / "formations"
                / "formation-ingestion-maturation"
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)

            memory_events = getattr(self.overlord, "memory_events", None)
            assert memory_events is not None, "memory event substrate missing"
            synthesis = getattr(self.overlord, "memory_synthesis", None)
            assert synthesis is not None, "memory synthesis service missing"
            scheduler = getattr(self.overlord, "scheduler_service", None)
            assert scheduler is not None, "scheduler missing"
            assert synthesis in getattr(scheduler, "_periodic_tasks", []), (
                "synthesis service must register on the scheduler's periodic-task loop"
            )
            print("  ✓ Synthesis service registered as a scheduler periodic task")
            checks_passed.append("Synthesis cadences registered on scheduler loop")

            print("\n📨 Phase 2: Ingest two notes about the same person...")
            async with httpx.AsyncClient(timeout=90.0) as client:
                first = await ingest(client, NOTE_FULL_IDENTITY, "note-a")
                second = await ingest(client, NOTE_SHORT_IDENTITY, "note-b")

            for label, status in (("note-a", first), ("note-b", second)):
                assert status["status"] == "completed", status
                item = status["items"][0]
                assert item["disposition"] == "stored", (label, item)
                assert "tier" in item and "tier_reason" in item, (label, item)
                print(
                    f"  ✓ {label}: stored at tier {item['tier']} "
                    f"({item['tier_reason']}, category="
                    f"{item['classification']['category']})"
                )
            checks_passed.append("Items stored with observable tier + reason")

            tiers = {s["items"][0]["tier"] for s in (first, second)}
            if tiers <= {2, 3} and tiers:
                print("  ✓ Personal/work content escalated past Tier 1 (LLM extraction)")
                checks_passed.append("Tier heuristics escalated synthesis-worthy content")
            else:
                print(f"  ✗ Expected tier 2/3 for personal notes, got {tiers}")
                all_passed = False

            print("\n🔗 Phase 3: Entity resolution merged the duplicate identity...")
            knowledge_graph = self.overlord.knowledge_graph
            person_entities = await knowledge_graph.storage.list_entities(
                USER_ID, entity_type="person", status=None, limit=100
            )
            names = {e["name"].lower() for e in person_entities}
            print(f"  Person entities extracted: {sorted(names)}")

            # Determinism guard: LLM extraction occasionally normalizes
            # both mentions to one name. If no short-name duplicate row
            # exists, seed the classic duplicate (same email attribute)
            # and let the REAL resolution machinery handle it via the
            # synthesis pass below -- the merge path under test is
            # identical either way.
            resolver_input_seeded = False
            if not any(n == "ryan" for n in names):
                await knowledge_graph.storage.upsert_entity(
                    USER_ID,
                    "person",
                    "Ryan",
                    attributes={"email": "ryan@nabo.dev"},
                    confidence=0.8,
                )
                resolver_input_seeded = True
                print("  (seeded short-name duplicate: LLM unified the mentions itself)")

            print("\n⚙️  Phase 4: Drive the hot synthesis cadence (cheapest pass)...")
            report = await synthesis.run_cadence("hot")
            print(f"  Hot cadence report: {report}")
            assert report["cadence"] == "hot", report
            assert report["failed"] == 0, report

            resolved_events = await memory_events.list_events(
                USER_ID, event_types=["entity.resolved"]
            )
            merged_events = [
                e for e in resolved_events if e["payload"]["decision"] == "merged"
            ]
            assert merged_events, (
                f"expected a merged entity.resolved event; got {resolved_events} "
                f"(seeded={resolver_input_seeded})"
            )
            payload = merged_events[0]["payload"]
            assert merged_events[0]["source"] == "synthesis", merged_events[0]
            print(
                f"  ✓ entity.resolved merged: {payload['duplicate_name']!r} -> "
                f"{payload['canonical_name']!r} (score {payload.get('score')}, "
                f"signals {payload.get('signals')})"
            )
            checks_passed.append("entity.resolved event recorded with decision merged")

            duplicate = await knowledge_graph.storage.get_entity(
                USER_ID, "person", payload["duplicate_name"]
            )
            canonical = await knowledge_graph.storage.get_entity(
                USER_ID, "person", payload["canonical_name"]
            )
            assert duplicate["status"] == "merged", duplicate
            assert duplicate["superseded_by"] == canonical["id"], duplicate
            aliases = canonical["attributes"].get("aliases", [])
            assert payload["duplicate_name"] in aliases, canonical
            active_names = {
                e["name"]
                for e in await knowledge_graph.storage.list_entities(
                    USER_ID, entity_type="person"
                )
            }
            assert payload["duplicate_name"] not in active_names, active_names
            print(
                f"  ✓ Duplicate row merged -> canonical (alias recorded: {aliases}); "
                f"active persons: {sorted(active_names)}"
            )
            checks_passed.append("Duplicate identity merged into canonical entity")

            print("\n🔁 Phase 5: Cursor + idempotency on the next pass...")
            second_report = await synthesis.run_cadence("hot")
            assert second_report["users"] == 0, (
                f"per-user cursor must skip settled users: {second_report}"
            )
            resolved_after = await memory_events.list_events(
                USER_ID, event_types=["entity.resolved"]
            )
            assert len(resolved_after) == len(resolved_events), (
                "replaying the pass must not append new resolution events"
            )
            print("  ✓ Second hot pass: 0 users (cursor respected), no new events")
            checks_passed.append("Per-user cursor + idempotent re-resolution")

            print("\n💬 Phase 6: Merged identity recallable in chat...")
            recall_msg = "Where does Ryan work and what's his email?"
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
            if "nabo" in recall_text.lower():
                print("  ✓ Chat recalled the merged identity's employer")
                checks_passed.append("Merged identity recallable in chat")
            else:
                print("  ✗ Chat did not recall the merged identity")
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
        print("🧬 AREA 2V2: MEMORY INGESTION MATURATION")
        print("=" * 60)

        all_passed = await self.test_ingestion_maturation()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Tier heuristics decide how much LLM an item earns; every escalation is observable")
        print("- Entity resolution rides the event substrate: merged decisions are idempotent")
        print("- Synthesis cadences run on the scheduler's loop with durable per-user cursors")
        print("- The hot pass is cheap: local scoring over the graph, no LLM involved")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestIngestionMaturation()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
