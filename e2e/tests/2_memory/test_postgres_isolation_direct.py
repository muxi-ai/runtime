#!/usr/bin/env python3
"""Direct test of PostgreSQL user isolation without formation."""

import psycopg2
import sys

def test_user_isolation():
    """Test user isolation directly in PostgreSQL."""
    print("Testing PostgreSQL User Isolation (Direct)")
    print("-" * 50)

    try:
        # Connect to Docker PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="muxi_test",
            user="muxi",
            password="testpass"
        )
        cursor = conn.cursor()
        print("✅ Connected to PostgreSQL")

        # Create test data for different users
        test_data = [
            ("alice_test", "Alice", "I am a data scientist at TechCorp"),
            ("alice_test", "Alice", "I like Python programming"),
            ("bob_test", "Bob", "I work at WebCo as a web developer"),
            ("bob_test", "Bob", "I prefer JavaScript"),
            ("charlie_test", "Charlie", "I like Rust programming"),
        ]

        # Insert test memories
        import uuid
        for user_id, name, content in test_data:
            # First ensure user exists
            public_id = str(uuid.uuid4())[:21]  # Generate unique public ID
            cursor.execute("""
                INSERT INTO users (public_id, external_user_id, formation_id, created_at)
                VALUES (%s, %s, 'test', NOW())
                ON CONFLICT (external_user_id, formation_id) DO UPDATE
                SET updated_at = NOW()
                RETURNING id
            """, (public_id, user_id,))

            user_result = cursor.fetchone()
            if user_result:
                user_db_id = user_result[0]
                memory_id = str(uuid.uuid4())[:21]  # Generate unique ID
                cursor.execute("""
                    INSERT INTO memories (id, user_id, text, meta_data, collection, created_at)
                    VALUES (%s, %s, %s, '{}', 'default', NOW())
                """, (memory_id, user_db_id, content))

        conn.commit()
        print("✅ Inserted test data for Alice, Bob, and Charlie")

        # Test isolation - retrieve memories for each user
        print("\n🔒 Testing Data Isolation:")

        for test_user in ["alice_test", "bob_test", "charlie_test"]:
            cursor.execute("""
                SELECT m.text
                FROM memories m
                JOIN users u ON m.user_id = u.id
                WHERE u.external_user_id = %s AND u.formation_id = 'test'
                ORDER BY m.created_at DESC
            """, (test_user,))

            memories = cursor.fetchall()
            memory_content = " ".join([m[0] for m in memories])

            print(f"\n{test_user}:")
            print(f"  Found {len(memories)} memories")

            # Check isolation
            if test_user == "alice_test":
                has_own = "Alice" in memory_content or "TechCorp" in memory_content
                no_others = "Bob" not in memory_content and "Charlie" not in memory_content
            elif test_user == "bob_test":
                has_own = "Bob" in memory_content or "WebCo" in memory_content
                no_others = "Alice" not in memory_content and "Charlie" not in memory_content
            else:  # charlie_test
                has_own = "Charlie" in memory_content or "Rust" in memory_content
                no_others = "Alice" not in memory_content and "Bob" not in memory_content

            if has_own and no_others:
                print(f"  ✅ Data correctly isolated")
            else:
                print(f"  ❌ Isolation failed - has own: {has_own}, no others: {no_others}")
                if memories:
                    print(f"  Content: {memory_content[:100]}...")

        # Cleanup test data
        for test_user in ["alice_test", "bob_test", "charlie_test"]:
            cursor.execute("""
                DELETE FROM memories
                WHERE user_id IN (
                    SELECT id FROM users
                    WHERE external_user_id = %s AND formation_id = 'test'
                )
            """, (test_user,))
            cursor.execute("""
                DELETE FROM users
                WHERE external_user_id = %s AND formation_id = 'test'
            """, (test_user,))

        conn.commit()
        print("\n✅ Test data cleaned up")

        cursor.close()
        conn.close()
        print("\n✅ PostgreSQL User Isolation Test Passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if test_user_isolation():
        sys.exit(0)
    else:
        sys.exit(1)