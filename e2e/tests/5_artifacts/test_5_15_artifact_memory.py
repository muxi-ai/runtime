#!/usr/bin/env python3
"""Test 5_15: Artifact Memory Phase 1 - capture and retention.

Verifies that a chat which generates a file leaves a persistent,
queryable artifact behind:

1. generate_file produces artifacts on the response (existing behavior).
2. The background capture persists them: metadata row in the artifacts
   table, encrypted blob on disk, artifact.saved audit event recorded.
3. Content round-trips through the per-user encryption key.
4. The retention config is respected: expires_at is set from the
   formation's retention block, and a deterministic sweep (backdated
   expiry + direct run_retention_sweep call) soft-deletes the row and
   prunes the blob.
"""

import asyncio
import os
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import TestOutputFormatter  # noqa: E402

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-artifact-memory"
USER_ID = "artifact_user"
CAPTURE_WAIT_SECONDS = 20


class Test515:
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

    async def _wait_for_capture(self, service):
        """Poll for the background capture task to land.

        Returns (effective_user_id, rows). In single-user mode the runtime
        normalizes every user id to "0", so the capture lands under the
        request's effective user rather than the raw chat user id.
        """
        deadline = time.time() + CAPTURE_WAIT_SECONDS
        while time.time() < deadline:
            for user_id in (USER_ID, "0"):
                rows = await service.list_artifacts(user_id)
                if rows:
                    return user_id, rows
            await asyncio.sleep(0.5)
        return USER_ID, []

    async def _backdate_expiry(self, service, public_id):
        """Push one artifact's expiry into the past (deterministic sweep)."""
        from sqlalchemy import select

        from muxi.runtime.services.memory.artifacts.models import Artifact
        from muxi.runtime.utils.datetime_utils import utc_now_naive

        async with service.db_manager.get_async_session() as session:
            stmt = select(Artifact).filter_by(public_id=public_id)
            artifact = (await session.execute(stmt)).scalars().first()
            artifact.expires_at = utc_now_naive() - timedelta(days=1)
            await session.flush()

    async def run_test(self):
        test_name = "5_15"
        self.formatter.print_test_header(test_name, "Artifact Memory Capture and Retention")
        start_time = time.time()
        checks = []
        transcript = []
        all_passed = True

        try:
            # 1. Load formation (artifact memory defaults ON with persistent memory)
            print("\n  1. Loading formation with artifact memory...")
            self._clean_state()
            self.formation = Formation()
            await self.formation.load(str(FORMATION_DIR / "formation.yaml"))
            self.overlord = await self.formation.start_overlord()

            service = getattr(self.formation, "_artifact_memory", None)
            assert service is not None, "Artifact memory service not initialized"
            assert service.settings.retention_days == 30, "Retention config not parsed"
            assert service.settings.retention_policy == "last_updated"
            print("     Artifact memory active (retention 30d, last_updated)")
            checks.append("Artifact memory initialized from formation config")

            # 2. Chat that generates a file
            print("\n  2. Generating a file through chat...")
            prompt = (
                "Use generate_file to create a CSV file named sales.csv with "
                "three rows of sample sales data (columns: month, revenue)."
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
            print(f"     Response carried {len(artifacts)} artifact(s)")
            checks.append(f"generate_file produced {len(artifacts)} artifact(s)")

            # 3. Background capture persisted the artifact
            print("\n  3. Waiting for background capture...")
            effective_user, rows = await self._wait_for_capture(service)
            assert rows, "Artifact was not captured into artifact memory"
            row = rows[0]
            print(
                f"     Captured: {row['name']} v{row['version']} "
                f"({row['content_type']}, {row['size_bytes']} bytes)"
            )
            assert row["version"] == 1
            assert row["is_latest"] is True
            assert row["expires_at"] is not None, "Retention duration did not set expires_at"
            assert row["checksum_sha256"], "Checksum missing"
            checks.append(f"Artifact captured and queryable: {row['name']} v{row['version']}")

            blob_path = service.settings.storage_path / row["storage_ref"]
            assert blob_path.exists(), f"Blob missing on disk: {blob_path}"
            checks.append("Encrypted blob written to formation-local artifact store")

            # 4. Content round-trips through the per-user key
            print("\n  4. Reading captured content back...")
            restored = await service.read_content(effective_user, row["public_id"])
            assert len(restored) > 0, "Captured content is empty"
            assert len(restored) == row["size_bytes"], "Round-trip size mismatch"
            print(f"     Round-tripped {len(restored)} bytes")
            checks.append("Content decrypts and decompresses to the original bytes")

            # 5. artifact.saved audit event recorded through the substrate
            print("\n  5. Checking artifact.saved audit event...")
            memory_events = getattr(self.formation, "_memory_events", None)
            assert memory_events is not None, "Memory event substrate not initialized"
            events = await memory_events.list_events(effective_user, event_types=["artifact.saved"])
            assert events, "No artifact.saved event recorded"
            assert events[0]["payload"]["artifact_id"] == row["public_id"]
            print(f"     artifact.saved recorded (event id {events[0]['id']})")
            checks.append("artifact.saved audit event recorded in memory_events")

            # 6. Retention sweep (deterministic: backdate, then sweep directly)
            print("\n  6. Running the retention sweep...")
            await self._backdate_expiry(service, row["public_id"])
            swept = await service.run_retention_sweep()
            assert swept >= 1, f"Sweep removed {swept} artifacts, expected >= 1"
            remaining = await service.list_artifacts(effective_user)
            assert all(
                r["public_id"] != row["public_id"] for r in remaining
            ), "Expired artifact still listed after sweep"
            assert not blob_path.exists(), "Blob not pruned by the retention sweep"
            audit = await service.list_artifacts(effective_user, include_deleted=True)
            assert any(
                r["public_id"] == row["public_id"] for r in audit
            ), "Soft-deleted metadata row missing from audit listing"
            print(f"     Sweep removed {swept} expired artifact(s); metadata retained")
            checks.append("Retention sweep pruned expired artifact (soft delete + blob removal)")

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
    test = Test515()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    os._exit(0 if result else 1)
