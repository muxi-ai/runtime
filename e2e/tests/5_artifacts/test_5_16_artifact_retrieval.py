#!/usr/bin/env python3
"""Test 5_16: Artifact Memory Phase 2 - manifest and retrieval tools.

Verifies that captured artifacts are usable in later turns:

1. generate_file in one turn leaves a captured artifact (Phase 1).
2. The knowledge index manifest carries the PRD 2.1 shape (artifact id,
   version, producing agent) so agents can navigate to it.
3. A later chat turn retrieves the artifact by id through the built-in
   get_artifact_content tool -- proven deterministically by the
   last_accessed_at refresh on the exact artifact row, plus the content
   appearing in the response.
4. Regenerating the same filename with different content extends the
   version chain (v2), and get_artifact_history returns the full chain.
5. The direct service surface agrees end to end: resolve_version walks
   back to v1 and its content still round-trips.
"""

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import TestOutputFormatter  # noqa: E402

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-artifact-memory"
USER_ID = "artifact_user"
CAPTURE_WAIT_SECONDS = 20


class Test516:
    def __init__(self):
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None

    def _clean_state(self):
        """Remove the previous run's database and blob store."""
        for name in ("memory.db", "memory.db-wal", "memory.db-shm"):
            try:
                (FORMATION_DIR / name).unlink()
            except FileNotFoundError:
                pass
        shutil.rmtree(FORMATION_DIR / "artifacts", ignore_errors=True)

    async def _wait_for_capture(self, service, expected_count=1):
        """Poll for background captures to land; returns (user_id, rows)."""
        deadline = time.time() + CAPTURE_WAIT_SECONDS
        while time.time() < deadline:
            for user_id in (USER_ID, "0"):
                rows = await service.list_artifacts(user_id, latest_only=False)
                if len(rows) >= expected_count:
                    return user_id, rows
            await asyncio.sleep(0.5)
        return USER_ID, []

    async def run_test(self):
        test_name = "5_16"
        self.formatter.print_test_header(test_name, "Artifact Memory Retrieval Tools")
        start_time = time.time()
        checks = []
        transcript = []
        all_passed = True

        try:
            # 1. Load formation (artifact memory ON via persistent memory)
            print("\n  1. Loading formation with artifact memory...")
            self._clean_state()
            self.formation = Formation()
            await self.formation.load(str(FORMATION_DIR / "formation.yaml"))
            self.overlord = await self.formation.start_overlord()

            service = getattr(self.formation, "_artifact_memory", None)
            assert service is not None, "Artifact memory service not initialized"
            assert getattr(self.overlord, "artifact_memory", None) is not None
            print("     Artifact memory active; retrieval tools registered")
            checks.append("Artifact memory service wired into the overlord")

            # 2. Turn 1: generate a file
            print("\n  2. Generating a file through chat...")
            prompt = (
                "Use generate_file to create a CSV file named sales.csv with "
                "exactly three rows of sample sales data (columns: month, revenue). "
                "Use the months January, February, March."
            )
            transcript.append(("User", prompt))
            response = await asyncio.wait_for(
                self.overlord.chat(prompt, user_id=USER_ID, use_async=False, stream=False),
                timeout=180,
            )
            content = response.content if hasattr(response, "content") else str(response)
            transcript.append(("System", content[:150]))
            artifacts = getattr(response, "artifacts", None) or []
            assert artifacts, "No artifacts on the response (generate_file did not run)"
            checks.append("generate_file produced an artifact")

            print("\n  3. Waiting for background capture...")
            effective_user, rows = await self._wait_for_capture(service)
            assert rows, "Artifact was not captured into artifact memory"
            v1 = rows[0]
            artifact_id = v1["public_id"]
            print(f"     Captured: {v1['name']} v{v1['version']} (id {artifact_id})")
            checks.append(f"Artifact captured: {v1['name']} v1, id {artifact_id}")

            # 4. Manifest: the knowledge index carries id + version + agent
            print("\n  4. Checking the artifact manifest in the knowledge index...")
            memory_index = getattr(self.overlord, "memory_index", None)
            assert memory_index is not None, "Knowledge index service not initialized"
            memory_index.invalidate(effective_user, reason="test")
            block = await memory_index.get_index_block(effective_user)
            assert artifact_id in block, f"Manifest missing artifact id: {block!r}"
            assert f"- {artifact_id} v1 |" in block, f"Manifest shape unexpected: {block!r}"
            assert " by " in block, "Manifest missing the producing agent"
            print("     Manifest line carries id, version, and producing agent")
            checks.append("Knowledge index manifest renders the PRD shape (id/version/agent)")

            # 5. Turn 2: retrieve the artifact by id in a later turn
            print("\n  5. Retrieving the artifact by id in a later turn...")
            before_access = (await service.get_metadata(effective_user, artifact_id))[
                "last_accessed_at"
            ]
            prompt = (
                f"Use the get_artifact_content tool with id '{artifact_id}' to read back "
                "the stored sales.csv artifact, then show me its exact contents."
            )
            transcript.append(("User", prompt))
            response = await asyncio.wait_for(
                self.overlord.chat(prompt, user_id=USER_ID, use_async=False, stream=False),
                timeout=180,
            )
            content = response.content if hasattr(response, "content") else str(response)
            transcript.append(("System", content[:200]))

            after_access = (await service.get_metadata(effective_user, artifact_id))[
                "last_accessed_at"
            ]
            assert (
                after_access > before_access
            ), "last_accessed_at did not move - the retrieval tool did not read the artifact"
            print("     get_artifact_content ran (last_accessed_at refreshed)")
            checks.append("Artifact retrieved by id in a later turn (last_accessed_at refreshed)")
            if any(month in content for month in ("January", "February", "March")):
                checks.append("Retrieved CSV content surfaced in the response")

            # 6. Turn 3: regenerate with different content -> version 2
            print("\n  6. Updating the artifact (new version)...")
            prompt = (
                "Use generate_file to create sales.csv again, but now with four rows "
                "(months January to April) and an extra 'units' column."
            )
            transcript.append(("User", prompt))
            response = await asyncio.wait_for(
                self.overlord.chat(prompt, user_id=USER_ID, use_async=False, stream=False),
                timeout=180,
            )
            content = response.content if hasattr(response, "content") else str(response)
            transcript.append(("System", content[:150]))

            _, rows = await self._wait_for_capture(service, expected_count=2)
            assert len(rows) >= 2, "Second capture did not land"
            head = next(row for row in rows if row["is_latest"])
            assert head["version"] == 2, f"Expected version 2 head, got {head['version']}"
            print(f"     Version chain extended: {head['name']} now v{head['version']}")
            checks.append("Regeneration extended the version chain to v2")

            # 7. History: the full chain resolves from any version's id
            print("\n  7. Listing artifact history after the update...")
            chain = await service.get_history(effective_user, artifact_id)
            assert [row["version"] for row in chain] == [
                2,
                1,
            ], f"Unexpected chain: {[row['version'] for row in chain]}"
            checks.append("get_artifact_history chain: v2 -> v1 from the v1 id")

            prompt = (
                f"Use the get_artifact_history tool with id '{artifact_id}' and tell me "
                "how many versions of that artifact exist."
            )
            transcript.append(("User", prompt))
            response = await asyncio.wait_for(
                self.overlord.chat(prompt, user_id=USER_ID, use_async=False, stream=False),
                timeout=180,
            )
            content = response.content if hasattr(response, "content") else str(response)
            transcript.append(("System", content[:200]))
            assert "2" in content, f"History turn did not report 2 versions: {content[:200]}"
            print("     Chat turn reported the 2-version history")
            checks.append("get_artifact_history answered through a chat turn")

            # 8. Old version content still round-trips
            print("\n  8. Reading version 1 content back...")
            v1_row = await service.resolve_version(effective_user, head["public_id"], version=1)
            assert v1_row is not None, "resolve_version could not walk back to v1"
            restored = await service.read_content(effective_user, v1_row["public_id"])
            assert len(restored) == v1_row["size_bytes"], "v1 content round-trip mismatch"
            print(f"     v1 round-tripped {len(restored)} bytes")
            checks.append("Previous version content decrypts and decompresses intact")

            # 9. REST read surface over real HTTP (real formation ->
            #    overlord -> route wiring; guards the serving-time
            #    attribute contract the unit mocks cannot).
            print("\n  9. Exercising the REST read surface over HTTP...")
            import httpx

            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            base_url = "http://127.0.0.1:8275/v1"
            headers = {
                "X-Muxi-Client-Key": "test-client-key-456",
                "X-Muxi-User-ID": effective_user,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(f"{base_url}/artifacts", headers=headers)
                assert r.status_code == 200, f"GET /artifacts returned {r.status_code}: {r.text}"
                data = r.json()["data"]
                assert data["total"] >= 1, f"REST listing empty: {data}"
                listed_ids = {row["id"] for row in data["artifacts"]}
                assert head["public_id"] in listed_ids, "REST listing missing the chain head"
                print(f"     GET /artifacts listed {data['total']} artifact(s)")
                checks.append("REST GET /v1/artifacts served the captured artifacts")

                r = await client.get(
                    f"{base_url}/artifacts/{head['public_id']}/content", headers=headers
                )
                assert r.status_code == 200, f"content download returned {r.status_code}"
                assert r.headers["x-muxi-artifact-id"] == head["public_id"]
                assert len(r.content) == head["size_bytes"], "HTTP content size mismatch"
                assert b"units" in r.content, "downloaded CSV missing the v2 'units' column"
                print(f"     Content download streamed {len(r.content)} bytes")
                checks.append("REST content download decrypted and streamed the latest version")

        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback

            traceback.print_exc()
            all_passed = False
            checks.append(f"FAILED: {e}")

        finally:
            try:
                if self.formation:
                    await self.formation.stop_overlord()
                    self.formation.stop()
            except Exception:
                pass

            duration = time.time() - start_time
            self.formatter.print_test_result(test_name, all_passed, checks, transcript, duration)

        return all_passed


if __name__ == "__main__":
    test = Test516()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    os._exit(0 if result else 1)
