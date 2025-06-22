#!/usr/bin/env python3
"""
Test PostgreSQL scheduled_jobs table.
"""

import psycopg2
import os
import sys
import urllib.parse

# Add root directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

def test_postgres_table():
    """Test that the scheduled_jobs table exists in PostgreSQL."""
    
    print("🧪 Testing PostgreSQL scheduled_jobs table...")
    
    try:
        # Connect to PostgreSQL
        database_url = "postgresql://ran@127.0.0.1/muxi_framework"
        parsed_url = urllib.parse.urlparse(database_url)
        
        conn = psycopg2.connect(
            host=parsed_url.hostname,
            port=parsed_url.port or 5432,
            user=parsed_url.username,
            password=parsed_url.password,
            dbname=parsed_url.path[1:]  # Remove leading slash
        )
        
        cursor = conn.cursor()
        
        print("✅ Connected to PostgreSQL database")
        
        # Check if table exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'scheduled_jobs'
        """)
        
        table_exists = cursor.fetchone()
        
        if table_exists:
            print("✅ scheduled_jobs table exists!")
            
            # Get table schema
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'scheduled_jobs'
                ORDER BY ordinal_position
            """)
            
            columns = cursor.fetchall()
            print("✅ Table schema:")
            for col in columns:
                print(f"   - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            
            # Check indexes
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'scheduled_jobs'
            """)
            
            indexes = cursor.fetchall()
            print("✅ Indexes:")
            for idx in indexes:
                print(f"   - {idx[0]}")
            
            # Test basic insert
            cursor.execute("""
                INSERT INTO scheduled_jobs (
                    user_id, formation_id, title, original_prompt, 
                    execution_prompt, cron_expression
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                "test_user", "test_formation", "Test Job",
                "test original prompt", "test execution prompt", "0 9 * * *"
            ))
            
            job_id = cursor.fetchone()[0]
            print(f"✅ Created test job with ID: {job_id}")
            
            # Test select
            cursor.execute("SELECT * FROM scheduled_jobs WHERE id = %s", (job_id,))
            job = cursor.fetchone()
            
            if job:
                print(f"✅ Retrieved job: {job[3]}")  # title is 4th column (index 3)
            
            # Clean up test job
            cursor.execute("DELETE FROM scheduled_jobs WHERE id = %s", (job_id,))
            print("✅ Cleaned up test job")
            
            conn.commit()
            
        else:
            print("❌ scheduled_jobs table not found!")
            return False
        
        cursor.close()
        conn.close()
        
        print("\n🎉 PostgreSQL scheduled_jobs table is working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_postgres_table()
    sys.exit(0 if success else 1)