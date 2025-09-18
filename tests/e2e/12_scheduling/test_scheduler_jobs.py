#!/usr/bin/env python3
"""
MUXI Scheduler End-to-End Tests

Tests the scheduler service initialization and database cleanup.
Note: Scheduler MCP tools integration is not yet implemented,
so job creation through chat interface is not functional.
"""

import asyncio
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation
from src.muxi.utils.datetime_utils import utc_now


async def test_scheduler_jobs():
    """Run scheduler E2E tests."""
    print("\n" + "=" * 80)
    print("MUXI SCHEDULER SERVICE TEST")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formation-scheduling"
    test_results = {}

    try:
        # Initialize formation
        print("\nInitializing formation...")
        formation = Formation()
        await formation.load(str(formation_path))

        # Start overlord with scheduler
        print("Starting overlord with scheduler service...")
        overlord = await formation.start_overlord()

        # Test 1: Verify scheduler is running
        if hasattr(overlord, 'scheduler_service') and overlord.scheduler_service:
            print("✅ Scheduler service initialized")
            test_results["scheduler_init"] = True
        else:
            print("❌ Scheduler service not found")
            test_results["scheduler_init"] = False
            return 1

        # Test 2: Check worker task
        if overlord.scheduler_service._worker_task and not overlord.scheduler_service._worker_task.done():
            print("✅ Background worker running")
            test_results["worker_running"] = True
        else:
            print("❌ Background worker not running")
            test_results["worker_running"] = False

        # Test 3: Get status
        status = await overlord.scheduler_service.get_status()
        if status:
            print(f"✅ Status accessible: {status}")
            test_results["status_accessible"] = True
        else:
            print("❌ Status not accessible")
            test_results["status_accessible"] = False

        # Test 4: Direct API test
        try:
            job_id = await overlord.scheduler_service.create_job(
                user_id="1",  # Must be string
                title="Test Daily Reminder",
                original_prompt="Schedule a test reminder daily at 10am",
                schedule="daily at 10am",  # Natural language schedule
                exclusions=[]
            )
            print(f"✅ Created job: {job_id}")
            test_results["api_create"] = True

            # Delete the job
            await overlord.scheduler_service.delete_job(job_id, user_id="1")
            print(f"✅ Deleted job: {job_id}")
            test_results["api_delete"] = True
        except Exception as e:
            print(f"❌ API test failed: {e}")
            test_results["api_create"] = False
            test_results["api_delete"] = False

        # Results summary
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80)

        passed = sum(test_results.values())
        total = len(test_results)

        for name, result in test_results.items():
            print(f"{name}: {'✅ PASS' if result else '❌ FAIL'}")

        print(f"\nTotal: {passed}/{total} tests passed")

        print("\n" + "=" * 80)
        print("### Test Result:")
        if passed == total:
            print("  🎉 SUCCESS: All scheduler service tests passed!")
            for name in test_results:
                if test_results[name]:
                    print(f"  ✓ {name}")
        else:
            print(f"  ⚠️  {total - passed} test(s) failed")
            for name in test_results:
                if not test_results[name]:
                    print(f"  ✗ {name}")

        print("\n" + "=" * 80)
        print("### Chat transcript:")
        print("\n[Scheduler service test - no chat interaction]")
        print("[Direct API validates core functionality]")

        return 0 if passed == total else 1

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        if 'overlord' in locals() and hasattr(overlord, 'scheduler_service'):
            print("\nCleaning up...")
            try:
                # Clean database using job_manager's delete methods
                job_manager = overlord.scheduler_service.job_manager
                # Delete all jobs (which should cascade to audit)
                from src.muxi.services.db import DatabaseManager
                db = DatabaseManager()
                async with db.session() as session:
                    from sqlalchemy import delete
                    from src.muxi.services.scheduler.models import ScheduledJobAudit, ScheduledJob
                    await session.execute(delete(ScheduledJobAudit))
                    await session.execute(delete(ScheduledJob))
                    await session.commit()
                print("✓ Database cleaned")
            except Exception as e:
                print(f"⚠️  Cleanup failed: {e}")

            # Stop service
            await overlord.scheduler_service.stop()
            print("✓ Service stopped")


if __name__ == "__main__":
    sys.exit(asyncio.run(test_scheduler_jobs()))