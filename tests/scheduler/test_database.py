#!/usr/bin/env python3
"""
Test database initialization for the MUXI Scheduler.

Tests that the scheduler database is properly created and tables exist.
"""

import asyncio
import sys
import os
import sqlite3
from pathlib import Path

# Add the runtime path to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

async def test_scheduler_database():
    """Test scheduler database initialization."""
    
    print("🧪 Testing MUXI Scheduler Database Initialization...")
    
    try:
        # Import the JobManager which handles database initialization
        from services.scheduler.manager import JobManager
        
        print("✅ Step 1: Creating JobManager...")
        job_manager = JobManager()
        
        print(f"✅ Step 2: Database path: {job_manager.db_path}")
        
        print("✅ Step 3: Initializing database...")
        await job_manager.initialize()
        
        print("✅ Step 4: Verifying table exists...")
        # Check if the table was created
        async with job_manager._get_db_connection() as db:
            cursor = await db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='scheduled_jobs'
            """)
            table_exists = await cursor.fetchone()
            
            if table_exists:
                print("   ✓ scheduled_jobs table exists!")
                
                # Check table schema
                cursor = await db.execute("PRAGMA table_info(scheduled_jobs)")
                columns = await cursor.fetchall()
                
                print("   ✓ Table schema:")
                for col in columns:
                    print(f"     - {col[1]} ({col[2]})")
                
                # Check indexes
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='index' AND tbl_name='scheduled_jobs'
                """)
                indexes = await cursor.fetchall()
                
                print("   ✓ Indexes:")
                for idx in indexes:
                    print(f"     - {idx[0]}")
                    
            else:
                print("   ❌ scheduled_jobs table not found!")
                return False
        
        print("✅ Step 5: Testing basic operations...")
        
        # Test job creation
        job_id = await job_manager.create_job(
            user_id="test_user",
            formation_id="test_formation", 
            title="Test Job",
            original_prompt="test prompt",
            execution_prompt="execute test",
            cron_expression="0 9 * * *"
        )
        print(f"   ✓ Created test job: {job_id}")
        
        # Test job retrieval
        job = await job_manager.get_job(job_id)
        if job:
            print(f"   ✓ Retrieved job: {job['title']}")
        else:
            print("   ❌ Failed to retrieve job!")
            return False
        
        # Test job listing
        user_jobs = await job_manager.get_user_jobs("test_user")
        print(f"   ✓ Found {len(user_jobs)} jobs for test_user")
        
        # Test job statistics
        stats = await job_manager.get_job_statistics("test_user")
        print(f"   ✓ Job statistics: {stats}")
        
        # Cleanup: Delete test job
        deleted = await job_manager.delete_job(job_id)
        print(f"   ✓ Cleaned up test job: {deleted}")
        
        print("\n🎉 Database initialization and basic operations successful!")
        print(f"📁 Database file created at: {job_manager.db_path}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_scheduler_database())
    if success:
        print("\n✅ The scheduler database is properly initialized and working!")
        print("   The scheduled_jobs table has been created in SQLite.")
        print("   No PostgreSQL migration is needed - the scheduler uses SQLite by design.")
    else:
        print("\n❌ Database test failed!")
    
    sys.exit(0 if success else 1)