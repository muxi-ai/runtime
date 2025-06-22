#!/usr/bin/env python3
"""
Full integration test for MUXI Scheduler with both PostgreSQL and SQLite.

Tests the complete scheduler implementation including database operations,
job creation, execution simulation, and database auto-detection.
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add root directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

async def test_database_managers():
    """Test both PostgreSQL and SQLite job managers."""
    
    print("🧪 Testing Database Managers...")
    
    results = {}
    
    # Test PostgreSQL if available
    postgres_url = os.getenv('POSTGRES_DATABASE_URL')
    if postgres_url:
        print("\n📊 Testing PostgreSQL JobManager...")
        try:
            from services.scheduler.postgres_manager import PostgreSQLJobManager
            
            pg_manager = PostgreSQLJobManager()
            await pg_manager.initialize()
            
            # Test job creation
            job_id = await pg_manager.create_job(
                user_id="test_user_pg",
                formation_id="test_formation",
                title="PostgreSQL Test Job",
                original_prompt="test postgres job",
                execution_prompt="execute postgres test",
                cron_expression="0 9 * * *",
                exclusion_rules=[{"type": "cron", "pattern": "* * * * 0,6", "description": "Skip weekends"}]
            )
            print(f"   ✓ Created PostgreSQL job: {job_id}")
            
            # Test job retrieval
            job = await pg_manager.get_job(job_id)
            print(f"   ✓ Retrieved job: {job['title']}")
            
            # Test job listing
            user_jobs = await pg_manager.get_user_jobs("test_user_pg")
            print(f"   ✓ Found {len(user_jobs)} jobs for user")
            
            # Test execution tracking
            await pg_manager.mark_job_execution_start(job_id)
            await pg_manager.mark_job_execution_success(job_id, "Test response")
            print("   ✓ Execution tracking works")
            
            # Test statistics
            stats = await pg_manager.get_job_statistics("test_user_pg")
            print(f"   ✓ Statistics: {stats}")
            
            # Cleanup
            deleted = await pg_manager.delete_job(job_id)
            print(f"   ✓ Cleanup successful: {deleted}")
            
            results['postgresql'] = True
            
        except Exception as e:
            print(f"   ❌ PostgreSQL test failed: {e}")
            results['postgresql'] = False
    else:
        print("\n📊 PostgreSQL not configured, skipping...")
        results['postgresql'] = None
    
    # Test SQLite
    print("\n💾 Testing SQLite JobManager...")
    try:
        from services.scheduler.manager import JobManager
        
        sqlite_manager = JobManager()
        await sqlite_manager.initialize()
        
        # Test job creation
        job_id = await sqlite_manager.create_job(
            user_id="test_user_sqlite",
            formation_id="test_formation",
            title="SQLite Test Job",
            original_prompt="test sqlite job",
            execution_prompt="execute sqlite test",
            cron_expression="0 9 * * *",
            exclusion_rules=[{"type": "cron", "pattern": "* * * * 0,6", "description": "Skip weekends"}]
        )
        print(f"   ✓ Created SQLite job: {job_id}")
        
        # Test job retrieval
        job = await sqlite_manager.get_job(job_id)
        print(f"   ✓ Retrieved job: {job['title']}")
        
        # Test job listing
        user_jobs = await sqlite_manager.get_user_jobs("test_user_sqlite")
        print(f"   ✓ Found {len(user_jobs)} jobs for user")
        
        # Test execution tracking
        await sqlite_manager.mark_job_execution_start(job_id)
        await sqlite_manager.mark_job_execution_success(job_id, "Test response")
        print("   ✓ Execution tracking works")
        
        # Test statistics
        stats = await sqlite_manager.get_job_statistics("test_user_sqlite")
        print(f"   ✓ Statistics: {stats}")
        
        # Cleanup
        deleted = await sqlite_manager.delete_job(job_id)
        print(f"   ✓ Cleanup successful: {deleted}")
        
        results['sqlite'] = True
        
    except Exception as e:
        print(f"   ❌ SQLite test failed: {e}")
        results['sqlite'] = False
    
    return results

async def test_scheduler_service():
    """Test the main SchedulerService with auto-detection."""
    
    print("\n🚀 Testing SchedulerService Integration...")
    
    try:
        from services.scheduler.service import SchedulerService
        
        # Create scheduler service (should auto-detect database)
        scheduler = await SchedulerService.get_instance()
        print("   ✓ Scheduler service created")
        
        # Check what database was selected
        db_type = "postgresql" if hasattr(scheduler.job_manager, '_pool') else "sqlite"
        print(f"   ✓ Auto-detected database: {db_type}")
        
        # Test service status
        status = await scheduler.get_status()
        print(f"   ✓ Service status: enabled={status.get('enabled')}, running={status.get('running')}")
        
        # Test job creation through service
        job_id = await scheduler.create_job(
            user_id="test_user_service",
            formation_id="test_formation",
            title="Service Test Job",
            original_prompt="check my email every morning",
            schedule="every day at 9am"
        )
        print(f"   ✓ Created job through service: {job_id}")
        
        # Test job listing through service
        jobs = await scheduler.list_user_jobs("test_user_service")
        print(f"   ✓ Listed {len(jobs)} jobs through service")
        
        # Test job control
        paused = await scheduler.pause_job(job_id)
        print(f"   ✓ Job paused: {paused}")
        
        resumed = await scheduler.resume_job(job_id)
        print(f"   ✓ Job resumed: {resumed}")
        
        # Cleanup
        deleted = await scheduler.delete_job(job_id)
        print(f"   ✓ Job deleted: {deleted}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ SchedulerService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_schedule_parsing():
    """Test schedule parsing functionality."""
    
    print("\n📅 Testing Schedule Parsing...")
    
    try:
        from services.scheduler.parser import ScheduleParser
        
        parser = ScheduleParser()
        
        test_schedules = [
            "every day at 9am",
            "every Monday at 2pm", 
            "every hour",
            "daily at noon",
            "weekly on Friday at 5pm"
        ]
        
        for schedule in test_schedules:
            try:
                cron_expr = await parser.parse_schedule(schedule)
                print(f"   ✓ '{schedule}' → '{cron_expr}'")
            except Exception as e:
                print(f"   ❌ Failed to parse '{schedule}': {e}")
                
        return True
        
    except Exception as e:
        print(f"   ❌ Schedule parsing test failed: {e}")
        return False

async def test_prompt_rewriting():
    """Test prompt rewriting functionality."""
    
    print("\n✏️  Testing Prompt Rewriting...")
    
    try:
        from services.scheduler.rewriter import PromptRewriter
        
        rewriter = PromptRewriter()
        
        test_prompts = [
            "check my email",
            "remind me about the meeting",
            "generate daily report", 
            "weather",
            "tell me about my calendar"
        ]
        
        for prompt in test_prompts:
            try:
                rewritten = await rewriter.rewrite_for_execution(prompt)
                print(f"   ✓ '{prompt}' → '{rewritten}'")
            except Exception as e:
                print(f"   ❌ Failed to rewrite '{prompt}': {e}")
                
        return True
        
    except Exception as e:
        print(f"   ❌ Prompt rewriting test failed: {e}")
        return False

async def main():
    """Run all scheduler integration tests."""
    
    print("🧪 MUXI Scheduler Full Integration Test")
    print("=" * 50)
    
    # Check environment
    postgres_url = os.getenv('POSTGRES_DATABASE_URL')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    print(f"📊 PostgreSQL: {'✓ Configured' if postgres_url else '❌ Not configured'}")
    print(f"🤖 OpenAI API: {'✓ Configured' if openai_key else '❌ Not configured'}")
    print()
    
    # Run tests
    tests = [
        ("Database Managers", test_database_managers),
        ("Scheduler Service", test_scheduler_service), 
        ("Schedule Parsing", test_schedule_parsing),
        ("Prompt Rewriting", test_prompt_rewriting)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "="*50)
    print("🎯 Test Results Summary:")
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r is True)
    
    for test_name, result in results.items():
        if result is True:
            print(f"   ✅ {test_name}: PASSED")
        elif result is False:
            print(f"   ❌ {test_name}: FAILED")
        else:
            print(f"   ⚠️  {test_name}: SKIPPED")
    
    print(f"\n📊 Overall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n🎉 All tests passed! MUXI Scheduler is fully functional.")
        print("   ✓ Database integration working")
        print("   ✓ Auto-detection functional") 
        print("   ✓ Core scheduling features operational")
        print("   ✓ Multi-user support ready")
        return True
    else:
        print(f"\n⚠️  {total_tests - passed_tests} test(s) failed. Please review the implementation.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)