#!/usr/bin/env python3
"""
Test 12A4: Verify Job Execution
Tests that scheduled jobs actually execute at the scheduled time.
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_verify_job_execution():
    """Test that scheduled jobs actually execute."""
    print("\n" + "="*60)
    print("TEST 12A4: Verify Job Execution")
    print("="*60)

    formation_path = Path(__file__).parent / "formation-scheduling"

    try:
        # Initialize and start formation
        print("\n[Setup] Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        # Schedule a job for 10 seconds from now
        run_at = datetime.now() + timedelta(seconds=10)
        print(f"\n[Test] Scheduling test job for {run_at.strftime('%H:%M:%S')} (10 seconds from now)")

        # Use a clear scheduling request
        test_prompt = f"generate a test message with timestamp {datetime.now().isoformat()}"
        schedule_request = f"In 10 seconds, {test_prompt}"

        response = await overlord.chat(
            schedule_request,
            user_id="test_execution_user",
            session_id="test_execution_session",
            use_async=False,
            stream=False
        )

        content = response.content if hasattr(response, 'content') else str(response)
        print(f"Scheduling response: {content[:200]}...")

        # Extract job ID
        import re
        job_id_match = re.search(r'job[_\-][a-zA-Z0-9]+', content)
        if not job_id_match:
            print("❌ Failed to extract job ID from response")
            return 1

        job_id = job_id_match.group(0)
        print(f"✅ Job scheduled with ID: {job_id}")

        # Wait for job to execute (10 seconds + 5 second buffer)
        print("\n[Waiting] Waiting 15 seconds for job to execute...")
        await asyncio.sleep(15)

        # Query the database to check job execution status
        # We need to access the scheduler service's database
        scheduler = overlord.services.get('scheduler')
        if scheduler and scheduler.job_manager:
            print("\n[Verification] Checking job execution status...")

            # Get job details from database
            query = """
                SELECT id, status, last_run_at, execution_count, last_result
                FROM scheduled_jobs
                WHERE id = %s
            """
            result = await scheduler.job_manager.db.execute_query(
                query, (job_id,)
            )

            if result and len(result) > 0:
                job = result[0]
                print(f"Job Status: {job['status']}")
                print(f"Execution Count: {job['execution_count']}")
                print(f"Last Run: {job['last_run_at']}")

                # Check if job executed
                if job['execution_count'] > 0:
                    print("✅ SUCCESS: Job executed successfully!")

                    # For one-time jobs, status should be 'completed'
                    if job['status'] == 'completed':
                        print("✅ One-time job marked as completed")

                    # Check last result
                    if job['last_result']:
                        print(f"Execution result: {job['last_result'][:100]}...")

                    success = True
                else:
                    print("❌ FAILED: Job did not execute within timeout period")
                    print("   Possible reasons:")
                    print("   - Scheduler worker not running")
                    print("   - Check interval too long (default is 1 minute)")
                    print("   - Job scheduled for wrong time")
                    success = False
            else:
                print(f"❌ Job {job_id} not found in database")
                success = False
        else:
            print("⚠️ Warning: Could not access scheduler service for verification")
            print("   Falling back to indirect verification...")

            # Try to check through overlord's chat history
            # This is less reliable but might show if the job executed
            success = False

        # Cleanup
        await formation.kill_overlord()
        # formation.shutdown()  # Not async, commented out to avoid issues

        if success:
            print("\n✅ TEST PASSED: Job execution verified")
            return 0
        else:
            print("\n❌ TEST FAILED: Job execution could not be verified")
            return 1

    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_verify_job_execution())
    sys.exit(exit_code)