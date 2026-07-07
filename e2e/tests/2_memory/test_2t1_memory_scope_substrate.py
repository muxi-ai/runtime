#!/usr/bin/env python3
"""Test 2T1: Memory Namespaces Phase 1 - Scope Substrate

This test validates the zero-behavior-change scope substrate:
1. The memories_{dim} table carries the new scope_type / scope_id
   columns (plus the scope index) alongside the existing schema
2. A full conversation + recall flow behaves identically with the new
   schema live: flat facts, knowledge graph, captain's log, and recall
   all work exactly as before
3. Every long-term memory write is stamped as user scope
   (scope_type='user', scope_id=<owning internal user id>)
4. Memory events record the same user scope the LTM writes carry
   (one consistent shape across substrate and projections)
5. Legacy rows (scope_id NULL, scope_type via column default) stay
   readable and searchable next to newly stamped rows
6. Working-memory partitions use the structured scope-key scheme
   (session:{id} / formation) without changing retrieval behavior
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest


class TestMemoryScopeSubstrate(BaseMemoryTest):
    """Validate the memory-namespaces Phase 1 scope substrate."""

    async def test_scope_substrate(self):
        """Scope columns live; conversation + recall flow unchanged."""
        test_name = "2t1_memory_scope_substrate"
        self.print_test_header(
            test_name, "Test scope columns, user-scope stamping, and unchanged recall flow"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "scope_test_user"

        try:
            # Start from a fresh database so schema and row assertions
            # are deterministic (2S1 pattern).
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"memory_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Conversation with the scope substrate live...")
            await self.setup_memory_formation("sqlite")

            # SQLite runs in single-user mode: every external user id is
            # normalized to "0" before extraction sees it.
            effective_user_id = user_id if self.overlord.is_multi_user else "0"

            user_msg1 = (
                "My name is Riley. I work at a company called Northlight and I "
                "live in Lisbon. Today we decided to ship the Atlas project in August."
            )
            response1 = await self.overlord.chat(
                user_msg1, user_id=user_id, use_async=False, stream=False
            )
            response1_text = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append((user_msg1, response1_text))
            print(f"User: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            user_msg2 = "My favorite drink is green tea and I have a dog named Pixel."
            response2 = await self.overlord.chat(
                user_msg2, user_id=user_id, use_async=False, stream=False
            )
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append((user_msg2, response2_text))
            print(f"User: {user_msg2}")
            print(f"Assistant: {response2_text[:200]}...")

            long_term_memory = getattr(self.overlord, "long_term_memory", None)
            memory_events = getattr(self.overlord, "memory_events", None)

            # Wait for the fire-and-forget extraction passes to land rows.
            # Poll until the second turn's fact (green tea) is extracted so
            # the recall phase below has something to recall (2B1 pattern).
            extracted_rows = []
            for _ in range(12):
                await asyncio.sleep(5)
                if long_term_memory.memories_table is None:
                    continue
                extracted_rows = long_term_memory.conn.execute(f"""
                    SELECT scope_type, scope_id, user_id, text
                    FROM {long_term_memory.memories_table}
                    WHERE json_extract(metadata, '$.source') = 'extraction'
                    """).fetchall()
                if any("green tea" in row[3].lower() for row in extracted_rows):
                    break
            print(f"  Extracted facts: {[row[3] for row in extracted_rows]}")

            # Check 1: scope columns + scope index exist on the live table
            table = long_term_memory.memories_table
            columns = [
                row[1]
                for row in long_term_memory.conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            if "scope_type" in columns and "scope_id" in columns:
                print(f"  ✓ {table} carries scope_type / scope_id columns")
                checks_passed.append("Scope columns present")
            else:
                print(f"  ✗ Scope columns missing from {table} (found: {columns})")
                all_passed = False

            indexes = {
                row[1]
                for row in long_term_memory.conn.execute(f"PRAGMA index_list({table})").fetchall()
            }
            if f"idx_{table}_scope" in indexes:
                print("  ✓ Scope fan-out index created")
                checks_passed.append("Scope index created")
            else:
                print(f"  ✗ Scope index missing (found: {indexes})")
                all_passed = False

            # Check 2: every extraction-derived write is stamped user scope
            internal_user_id = await long_term_memory.get_or_create_user(effective_user_id)
            stamped = all(row[0] == "user" and row[1] == str(row[2]) for row in extracted_rows)
            if extracted_rows and stamped:
                print(
                    f"  ✓ All {len(extracted_rows)} extracted memories stamped as user scope "
                    f"(scope_id mirrors the owning user id)"
                )
                checks_passed.append("LTM writes stamp user scope")
            else:
                print(f"  ✗ Extraction rows missing user-scope stamps: {extracted_rows}")
                all_passed = False

            # Check 3: memory events carry the same user scope as the
            # LTM writes (one consistent shape).
            events = await memory_events.list_events(effective_user_id)
            events_scoped = all(
                e["scope_type"] == "user" and e["scope_id"] == effective_user_id for e in events
            )
            if events and events_scoped:
                print(f"  ✓ All {len(events)} memory events carry user scope")
                checks_passed.append("Events aligned with LTM scope")
            else:
                print("  ✗ Memory events missing user scope values")
                all_passed = False

            # Check 4: knowledge graph and captain's log projections are
            # intact with the new schema live.
            knowledge_graph = getattr(self.overlord, "knowledge_graph", None)
            entities = await knowledge_graph.storage.list_entities(
                effective_user_id, status=None, limit=100
            )
            if entities:
                print(f"  ✓ Knowledge graph populated ({len(entities)} entities)")
                checks_passed.append("Knowledge graph intact")
            else:
                print("  ✗ Knowledge graph empty after conversation")
                all_passed = False

            captains_log = getattr(self.overlord, "captains_log", None)
            model = getattr(self.overlord, "extraction_model", None) or getattr(
                self.overlord, "default_model", None
            )
            totals = await captains_log.run_periodic_summarization(model)
            print(f"  Digest totals: {totals}")
            if totals["entries"] >= 1:
                print("  ✓ Captain's log digest works on the new schema")
                checks_passed.append("Captain's log intact")
            else:
                print("  ✗ Captain's log digest produced no entries")
                all_passed = False

            # Check 5: a legacy row (scope_id NULL — pre-migration shape)
            # stays readable and searchable next to stamped rows.
            print("\n🕰️  Phase 2: Legacy-row readability...")
            legacy_id = "legacy-scope-row-0000"
            donor = long_term_memory.conn.execute(
                f"SELECT embedding, collection FROM {table} LIMIT 1"
            ).fetchone()
            long_term_memory.conn.execute(
                f"""
                INSERT INTO {table} (id, user_id, collection, text, embedding, metadata)
                VALUES (?, ?, ?, ?, ?, '{{}}')
                """,
                (legacy_id, internal_user_id, donor[1], "Riley's lucky number is 42", donor[0]),
            )
            long_term_memory.conn.commit()
            legacy_row = long_term_memory.conn.execute(
                f"SELECT scope_type, scope_id FROM {table} WHERE id = ?", (legacy_id,)
            ).fetchone()
            if legacy_row and legacy_row[0] == "user" and legacy_row[1] is None:
                print("  ✓ Legacy row reads as user scope (default scope_type, NULL scope_id)")
                checks_passed.append("Legacy rows readable as user scope")
            else:
                print(f"  ✗ Legacy row has unexpected scope values: {legacy_row}")
                all_passed = False

            legacy_hits = await long_term_memory.search(
                "Riley's lucky number", limit=5, user_id=effective_user_id
            )
            if any("42" in r["text"] for r in legacy_hits):
                print("  ✓ Legacy (NULL scope_id) row surfaces in vector search")
                checks_passed.append("Legacy rows searchable")
            else:
                print(f"  ✗ Legacy row missing from search results: {legacy_hits}")
                all_passed = False

            # Check 6: working-memory partitions use the structured
            # scope-key scheme without changing retrieval behavior.
            print("\n🧭 Phase 3: Working-memory partition scheme...")
            buffer_memory = getattr(self.overlord, "buffer_memory", None)
            partition_keys = set(buffer_memory.partitions.keys()) if buffer_memory else set()
            print(f"  Partition keys: {sorted(partition_keys)}")
            valid_keys = all(
                key == "formation" or key.startswith(("session:", "user:", "group:"))
                for key in partition_keys
            )
            if valid_keys:
                print("  ✓ All working-memory partitions use the structured scope keys")
                checks_passed.append("Structured partition keys")
            else:
                print("  ✗ Found partition keys outside the structured scheme")
                all_passed = False

            # Check 7: recall flow behaves identically with the schema live.
            # The retrieval probe pins the substrate directly (deterministic);
            # the chat below then exercises the full enhancement + agent flow.
            print("\n🔁 Phase 4: Recall flow...")
            recall_msg = "What is my favorite drink?"
            probe = await self.overlord.persistent_memory_manager.search_long_term_memory(
                query=recall_msg,
                k=5,
                user_id=user_id,
                collections=["preferences", "user_identity", "goals", "default"],
            )
            print(f"  Retrieval probe: {[r.get('text') for r in probe]}")
            if any("green tea" in (r.get("text") or "").lower() for r in probe):
                print("  ✓ Persistent-memory retrieval surfaces the stored fact")
                checks_passed.append("Retrieval surfaces stored facts")
            else:
                print("  ✗ Persistent-memory retrieval missed the stored fact")
                all_passed = False
            # The chat turn exercises the full enhancement + agent flow.
            # The agent's final context draws on the knowledge graph and
            # captain's log blocks (plus buffer history), so ask about the
            # entities the conversation established. The agent is pinned:
            # this test validates the memory substrate, not LLM routing
            # (the router occasionally flakes to the generalist fallback).
            recall_chat_msg = (
                "Tell me what you remember about me - my name, where I live, and my dog."
            )
            recall_response = await self.overlord.chat(
                recall_chat_msg,
                agent_name="memory_agent",
                user_id=user_id,
                use_async=False,
                stream=False,
            )
            recall_text = (
                recall_response.content
                if hasattr(recall_response, "content")
                else str(recall_response)
            )
            transcript.append((recall_chat_msg, recall_text))
            print(f"User: {recall_chat_msg}")
            print(f"Assistant: {recall_text[:300]}...")

            recall_lower = recall_text.lower()
            markers_found = [
                m
                for m in ("riley", "pixel", "lisbon", "northlight", "green tea")
                if m in recall_lower
            ]
            if len(markers_found) >= 2:
                print(f"  ✓ Recall works unchanged on the scoped schema (markers: {markers_found})")
                checks_passed.append("Recall intact on scoped schema")
            else:
                print(f"  ✗ Recall failed with the scope substrate live (markers: {markers_found})")
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
        print("🧭 AREA 2T1: MEMORY SCOPE SUBSTRATE")
        print("=" * 60)

        all_passed = await self.test_scope_substrate()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Every long-term memory write is stamped (scope_type='user', scope_id=owner)")
        print("- Legacy rows read as user scope via the additive column defaults")
        print(
            "- Working-memory partitions moved to structured scope keys with zero behavior change"
        )

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestMemoryScopeSubstrate()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
