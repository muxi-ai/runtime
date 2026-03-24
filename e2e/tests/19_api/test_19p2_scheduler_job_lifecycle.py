#!/usr/bin/env python3
"""Test 19p2: Scheduler job lifecycle (create, update, pause, resume, delete).

Exercises the full CRUD + state-transition lifecycle for scheduled jobs,
covering bugs 1-3 from the scheduler bug report:
  Bug 1: Jobs must persist to the database (not in-memory dicts)
  Bug 2: user_id from X-Muxi-User-ID header must be stored
  Bug 3: PUT update, POST pause, POST resume endpoints must work
"""

import asyncio
import time
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestSchedulerJobLifecycle(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19p2_scheduler_job_lifecycle",
            test_description="Scheduler job lifecycle: create, update, pause, resume, delete",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "X-Muxi-User-ID": "lifecycle_test_user",
            "Content-Type": "application/json",
        }

    async def test_19p2_scheduler_job_lifecycle(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []

        formatter.print_test_header(
            test_name="test_19p2_scheduler_job_lifecycle",
            description="Scheduler job lifecycle: create, update, pause, resume, delete",
        )

        try:
            # ── Setup ──────────────────────────────────────────────────
            print("\n1. Setting up formation with scheduler + PostgreSQL...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(3)
            print("   Formation ready")

            async with httpx.AsyncClient(timeout=30.0) as client:

                # ── Step 1: Create a recurring job ─────────────────────
                print("\n2. POST /v1/scheduler/jobs (recurring)...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs",
                    headers=self.headers,
                    json={
                        "type": "recurring",
                        "schedule": "0 9 * * 1",
                        "message": "Generate weekly report",
                    },
                )
                assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
                body = r.json()
                assert body["success"] is True, f"Expected success=True: {body}"
                job_id = body["data"]["id"]
                print(f"   Created job: {job_id}")
                checks.append(f"POST create recurring job -> 201 (id={job_id})")

                # ── Step 2: Verify job appears in list ─────────────────
                print("\n3. GET /v1/scheduler/jobs (verify creation)...")
                r = await client.get(
                    f"{self.base_url}/scheduler/jobs", headers=self.headers
                )
                assert r.status_code == 200
                jobs = r.json()["data"]["jobs"]
                job_ids = [j["id"] for j in jobs]
                assert job_id in job_ids, f"Job {job_id} not in list: {job_ids}"
                print(f"   Job count: {len(jobs)}, target job present")
                checks.append("GET list jobs -> job present")

                # ── Step 3: Get single job ─────────────────────────────
                print(f"\n4. GET /v1/scheduler/jobs/{job_id}...")
                r = await client.get(
                    f"{self.base_url}/scheduler/jobs/{job_id}", headers=self.headers
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                job_data = r.json()["data"]
                print(f"   Job status: {job_data.get('status', 'N/A')}")
                checks.append("GET single job -> 200")

                # ── Step 4: Update job message ─────────────────────────
                print(f"\n5. PUT /v1/scheduler/jobs/{job_id} (update message)...")
                r = await client.put(
                    f"{self.base_url}/scheduler/jobs/{job_id}",
                    headers=self.headers,
                    json={"message": "Generate weekly sales report with charts"},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                updated = r.json()["data"]
                print(f"   Updated job: {updated.get('id', job_id)}")
                checks.append("PUT update job -> 200")

                # The update may have replaced the job (new ID) if the prompt
                # change was significant.  Use whatever ID came back.
                job_id = updated.get("id", job_id)

                # ── Step 5: Pause the job ──────────────────────────────
                print(f"\n6. POST /v1/scheduler/jobs/{job_id}/pause...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs/{job_id}/pause",
                    headers=self.headers,
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                paused = r.json()["data"]
                assert paused.get("status") == "PAUSED", f"Expected PAUSED: {paused}"
                print("   Job paused")
                checks.append("POST pause -> 200, status=PAUSED")

                # ── Step 6: Pause again (should 404 — already paused) ─
                print(f"\n7. POST /v1/scheduler/jobs/{job_id}/pause (already paused)...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs/{job_id}/pause",
                    headers=self.headers,
                )
                assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
                print("   Correctly rejected (not in ACTIVE state)")
                checks.append("POST pause again -> 404 (idempotency)")

                # ── Step 7: Resume the job ─────────────────────────────
                print(f"\n8. POST /v1/scheduler/jobs/{job_id}/resume...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs/{job_id}/resume",
                    headers=self.headers,
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                resumed = r.json()["data"]
                assert resumed.get("status") == "ACTIVE", f"Expected ACTIVE: {resumed}"
                print("   Job resumed")
                checks.append("POST resume -> 200, status=ACTIVE")

                # ── Step 8: Resume again (should 404 — already active) ─
                print(f"\n9. POST /v1/scheduler/jobs/{job_id}/resume (already active)...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs/{job_id}/resume",
                    headers=self.headers,
                )
                assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
                print("   Correctly rejected (not in PAUSED state)")
                checks.append("POST resume again -> 404 (idempotency)")

                # ── Step 9: Create a one-time job ──────────────────────
                future_dt = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                print(f"\n10. POST /v1/scheduler/jobs (one_time, {future_dt[:19]}Z)...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs",
                    headers=self.headers,
                    json={
                        "type": "one_time",
                        "schedule": future_dt,
                        "message": "One-time reminder",
                    },
                )
                assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
                onetime_id = r.json()["data"]["id"]
                print(f"   Created one-time job: {onetime_id}")
                checks.append("POST create one_time job -> 201")

                # ── Step 10: Delete the recurring job ──────────────────
                print(f"\n11. DELETE /v1/scheduler/jobs/{job_id}...")
                r = await client.delete(
                    f"{self.base_url}/scheduler/jobs/{job_id}",
                    headers=self.headers,
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("   Job deleted")
                checks.append("DELETE recurring job -> 200")

                # ── Step 11: Confirm deletion ──────────────────────────
                print(f"\n12. GET /v1/scheduler/jobs/{job_id} (should be 404)...")
                r = await client.get(
                    f"{self.base_url}/scheduler/jobs/{job_id}",
                    headers=self.headers,
                )
                assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
                print("   Confirmed deleted")
                checks.append("GET deleted job -> 404")

                # ── Step 12: Delete the one-time job ───────────────────
                print(f"\n13. DELETE /v1/scheduler/jobs/{onetime_id}...")
                r = await client.delete(
                    f"{self.base_url}/scheduler/jobs/{onetime_id}",
                    headers=self.headers,
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                checks.append("DELETE one_time job -> 200")

                # ── Step 13: Pause/resume non-existent job ─────────────
                print("\n14. POST pause/resume on non-existent job...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs/nonexistent/pause",
                    headers=self.headers,
                )
                assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs/nonexistent/resume",
                    headers=self.headers,
                )
                assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
                print("   Both returned 404")
                checks.append("Pause/resume nonexistent -> 404")

                # ── Step 14: Update non-existent job ───────────────────
                print("\n15. PUT update non-existent job...")
                r = await client.put(
                    f"{self.base_url}/scheduler/jobs/nonexistent",
                    headers=self.headers,
                    json={"message": "nope"},
                )
                assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
                print("   Returned 404")
                checks.append("PUT update nonexistent -> 404")

                # ── Step 15: Validation errors ─────────────────────────
                print("\n16. POST with invalid cron expression...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs",
                    headers=self.headers,
                    json={
                        "type": "recurring",
                        "schedule": "not a cron",
                        "message": "bad",
                    },
                )
                assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
                print("   Invalid cron -> 422")
                checks.append("POST invalid cron -> 422")

                print("\n17. POST with past datetime...")
                r = await client.post(
                    f"{self.base_url}/scheduler/jobs",
                    headers=self.headers,
                    json={
                        "type": "one_time",
                        "schedule": "2020-01-01T00:00:00Z",
                        "message": "past",
                    },
                )
                assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
                print("   Past datetime -> 422")
                checks.append("POST past datetime -> 422")

            # ── Done ───────────────────────────────────────────────────
            formatter.print_test_result(
                test_name="test_19p2_scheduler_job_lifecycle",
                success=True,
                checks=checks,
                transcript=[],
                duration=time.time() - start_time,
            )

        except Exception as e:
            formatter.print_test_result(
                test_name="test_19p2_scheduler_job_lifecycle",
                success=False,
                checks=[f"Failed: {e}"],
                transcript=[],
                duration=time.time() - start_time,
            )
            import traceback

            traceback.print_exc()
            raise
        finally:
            if self.formation:
                await self.cleanup_formation()


async def main():
    await TestSchedulerJobLifecycle().test_19p2_scheduler_job_lifecycle()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
