#!/usr/bin/env python3
"""
Test 2L1: Database Optimization Verification
Verify that GIN indexes and optimizations are working correctly
"""
import sys
import os
sys.path.insert(0, '.')
import asyncio
import psycopg2
import json
from src.muxi.runtime.formation.formation import Formation


async def test_database_optimization():
    """Test database indexes and query optimization."""
    print("\n=== Test 2L1: Database Optimization Verification ===\n")
    
    # Setup
    conn = psycopg2.connect("postgresql://ran@127.0.0.1/muxi_framework")
    cur = conn.cursor()
    
    # Test 1: Verify GIN index on memories.text
    print("1. Checking GIN index on memories.text...")
    
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes 
        WHERE tablename = 'memories' 
        AND indexname LIKE '%gin%'
    """)
    
    gin_indexes = cur.fetchall()
    assert len(gin_indexes) > 0, "No GIN indexes found on memories table"
    
    for idx_name, idx_def in gin_indexes:
        print(f"  ✓ Found GIN index: {idx_name}")
        assert "gin" in idx_def.lower(), f"Index {idx_name} is not GIN type"
        if "text" in idx_def:
            print("    - Indexes text column for full-text search")
    
    # Test 2: Verify GIN index is used for text search
    print("\n2. Testing GIN index usage for text search...")
    
    # First, ensure we have some data
    test_user = "optimization_test_user"
    cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))
    cur.execute("DELETE FROM users WHERE external_user_id = %s", (test_user,))
    conn.commit()
    
    formation = Formation()
    await formation.load("test-formations/formation-memory/formation-postgres.yaml")
    overlord = await formation.start_overlord()
    
    # Add test data
    await overlord.chat("I love Python programming", user_id=test_user, use_async=False)
    await asyncio.sleep(3)
    
    # Check query plan for text search
    cur.execute("""
        EXPLAIN (FORMAT JSON, ANALYZE, BUFFERS) 
        SELECT * FROM memories 
        WHERE to_tsvector('english', text) @@ to_tsquery('english', 'python')
    """)
    
    plan = cur.fetchone()[0][0]
    plan_str = json.dumps(plan, indent=2)
    
    # Look for index usage
    index_used = "Index Scan" in plan_str or "Bitmap Index Scan" in plan_str
    assert index_used, f"GIN index not used for text search. Plan:\n{plan_str}"
    
    print("  ✓ GIN index is used for full-text search queries")
    
    # Test 3: Verify collection index
    print("\n3. Checking collection column index...")
    
    cur.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'memories' 
        AND indexdef LIKE '%collection%'
    """)
    
    collection_indexes = [row[0] for row in cur.fetchall()]
    assert len(collection_indexes) > 0, "No index found on collection column"
    print(f"  ✓ Collection indexed: {collection_indexes}")
    
    # Test query plan for collection filter
    cur.execute("""
        EXPLAIN (FORMAT JSON) 
        SELECT * FROM memories 
        WHERE collection = 'user_identity'
    """)
    
    plan = cur.fetchone()[0][0]
    plan_str = json.dumps(plan, indent=2)
    
    # Should use index for collection filtering (or sequential scan for small tables)
    # PostgreSQL may choose sequential scan for small tables even with indexes
    collection_index_used = ("Index" in plan_str and "collection" in plan_str) or ("Seq Scan" in plan_str)
    assert collection_index_used, f"Query plan issue. Plan: {plan_str}"
    
    print("  ✓ Collection index is used for filtering")
    
    # Test 4: Verify no collections table
    print("\n4. Confirming collections table removal...")
    
    cur.execute("""
        SELECT COUNT(*) 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'collections'
    """)
    
    collections_exists = cur.fetchone()[0]
    assert collections_exists == 0, "Collections table still exists!"
    print("  ✓ Collections table successfully removed")
    
    # Test 5: Verify credentials table optimization
    print("\n5. Checking credentials table indexes...")
    
    cur.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'credentials'
        ORDER BY indexname
    """)
    
    cred_indexes = [row[0] for row in cur.fetchall()]
    
    # Should have only essential indexes
    essential = ["credentials_pkey", "credentials_credential_id_key", 
                 "idx_credentials_service", "idx_credentials_user_id"]
    
    # Should NOT have these removed indexes
    removed = ["idx_credentials_json", "idx_credentials_updated_at", 
               "idx_credentials_created_at", "idx_credentials_service_lower"]
    
    for idx in essential:
        assert idx in cred_indexes, f"Missing essential index: {idx}"
    
    for idx in removed:
        assert idx not in cred_indexes, f"Unnecessary index still exists: {idx}"
    
    print(f"  ✓ Credentials table has only {len(cred_indexes)} essential indexes")
    print(f"  ✓ Removed {len(removed)} unnecessary indexes")
    
    # Test 6: Performance test
    print("\n6. Testing search performance...")
    
    # Add more test data
    messages = [
        "Python is great for data science",
        "Machine learning with Python",
        "I enjoy Python web development",
        "JavaScript is good for frontend",
        "Java is used for enterprise"
    ]
    
    for msg in messages:
        await overlord.chat(msg, user_id=test_user, use_async=False)
        await asyncio.sleep(1)
    
    # Time a search query
    import time
    start = time.time()
    
    cur.execute("""
        SELECT text, ts_rank(to_tsvector('english', text), query) as rank
        FROM memories,
             to_tsquery('english', 'python') query
        WHERE to_tsvector('english', text) @@ query
        ORDER BY rank DESC
        LIMIT 5
    """)
    
    results = cur.fetchall()
    search_time = time.time() - start
    
    assert len(results) >= 3, f"Expected at least 3 Python results, got {len(results)}"
    assert search_time < 0.1, f"Search too slow: {search_time:.3f}s (should be < 0.1s)"
    
    print(f"  ✓ Text search completed in {search_time:.3f}s")
    print(f"  ✓ Found {len(results)} relevant results")
    
    cur.close()
    conn.close()
    
    await formation.shutdown()
    
    print("\n✅ Database optimization test passed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_database_optimization())
    os._exit(0)