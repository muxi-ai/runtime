#!/usr/bin/env python3
"""
Test 12B3: Wait for Existing Job Execution
Just waits for existing scheduled jobs to execute without creating new ones.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_wait_for_execution():
    """Test that waits for existing jobs to execute."""
    print("\n" + "="*60)
    print("TEST 12B3: Wait for Existing Job Execution")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n[Info] Not creating new jobs - just waiting for existing jobs to execute")
        print("[Info] This test will wait 2 minutes to see if any jobs execute")

        # Try to access scheduler service to check existing jobs
        scheduler = overlord._scheduler if hasattr(overlord, '_scheduler') else None
        if scheduler and scheduler.job_manager:
            # Check existing jobs
            query = """
                SELECT id, execution_prompt, cron_expression, is_recurring, status
                FROM scheduled_jobs
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT 5
            """
            result = await scheduler.job_manager.db.execute_query(query)

            if result and len(result) > 0:
                print(f"\n[Found] {len(result)} pending job(s):")
                for job in result:
                    print(f"  - Job ID: {job['id']}")
                    print(f"    Execution Prompt: {job['execution_prompt']}")
                    print(f"    Cron: {job['cron_expression']}")
                    print(f"    Recurring: {job['is_recurring']}")
            else:
                print("\n[Info] No pending jobs found in database")

        # Wait 2 minutes for jobs to execute
        print("\n[Wait] Waiting 2 minutes for job execution...")
        await asyncio.sleep(120)

        # Check if any jobs executed
        if scheduler and scheduler.job_manager:
            query = """
                SELECT id, execution_prompt, execution_count, last_run_at, last_result
                FROM scheduled_jobs
                WHERE execution_count > 0
                ORDER BY last_run_at DESC
                LIMIT 5
            """
            result = await scheduler.job_manager.db.execute_query(query)

            if result and len(result) > 0:
                print(f"\n✅ Found {len(result)} job(s) that have executed:")
                for job in result:
                    print(f"  - Job ID: {job['id']}")
                    print(f"    Execution Prompt: {job['execution_prompt']}")
                    print(f"    Execution Count: {job['execution_count']}")
                    print(f"    Last Run: {job['last_run_at']}")
                    if job['last_result']:
                        print(f"    Last Result: {job['last_result'][:100]}...")
            else:
                print("\n⚠️ No jobs have executed yet")

        # Cleanup
        await formation.kill_overlord()

        print("\n✅ TEST COMPLETED: Checked existing job execution")
        return 0

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_wait_for_execution())
    sys.exit(exit_code)
