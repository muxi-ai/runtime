#!/usr/bin/env python3
"""Test to verify database records are created properly"""

import sys
from pathlib import Path
import os
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import asyncio

from muxi.services.db import get_database_manager
from muxi.services.memory.long_term import LongTermMemory, User, Memory
from muxi.services.secrets.secrets_manager import SecretsManager
from sqlalchemy import select, func

# Create mock LLM for embedding
class MockLLM:
    async def embed(self, text):
        # Return a simple mock embedding
        return [0.1] * 1536

async def main():
    # Get Postgres URI from secrets
    secrets = SecretsManager(str(Path(__file__).parent / "formations" / "formation-memory"))
    postgres_uri = await secrets.get_secret("POSTGRES_URI")

    print(f"Connecting to database...")

    # Create database manager
    db_manager = get_database_manager(postgres_uri)

    # Create LongTermMemory
    print("Creating LongTermMemory instance...")
    ltm = LongTermMemory(
        formation_id="test_formation",
        db_manager=db_manager,
        embedding_model=MockLLM()
    )

    print("\n=== Adding test data ===")

    # Add memories for multiple users
    print("\nAdding memory for user1...")
    memory_id1 = await ltm.add(
        content="My name is Alice and I work at TechCorp",
        metadata={"type": "personal_info"},
        external_user_id="user1"
    )
    print(f"✓ Added memory ID: {memory_id1}")

    print("\nAdding another memory for user1...")
    memory_id2 = await ltm.add(
        content="I love Python programming",
        metadata={"type": "preference"},
        external_user_id="user1"
    )
    print(f"✓ Added memory ID: {memory_id2}")

    print("\nAdding memory for user2...")
    memory_id3 = await ltm.add(
        content="My name is Bob and I work at WebCo",
        metadata={"type": "personal_info"},
        external_user_id="user2"
    )
    print(f"✓ Added memory ID: {memory_id3}")

    print("\nAdding memory for user3...")
    memory_id4 = await ltm.add(
        content="My name is Charlie and I like Rust",
        metadata={"type": "personal_info"},
        external_user_id="user3"
    )
    print(f"✓ Added memory ID: {memory_id4}")

    # Now check what's in the database
    print("\n=== Verifying database contents ===")

    with ltm.Session() as session:
        # Check users table
        print("\n--- USERS TABLE ---")
        users = session.query(User).all()
        print(f"Total users: {len(users)}")
        for user in users:
            print(f"  User ID: {user.id}, External ID: {user.external_user_id}, Formation: {user.formation_id}")

        # Check memories table
        print("\n--- MEMORIES TABLE ---")
        memories = session.query(Memory).all()
        print(f"Total memories: {len(memories)}")
        for mem in memories:
            print(f"  Memory ID: {mem.id}, User ID: {mem.user_id}, Collection: {mem.collection}")
            print(f"    Content: {mem.text[:50]}...")
            print(f"    Has embedding: {'Yes' if mem.embedding is not None else 'No'}")

        # Check memory count per user
        print("\n--- MEMORY COUNT PER USER ---")
        user_memory_counts = session.query(
            User.external_user_id,
            func.count(Memory.id).label('memory_count')
        ).join(Memory).group_by(User.external_user_id).all()

        for user_id, count in user_memory_counts:
            print(f"  User {user_id}: {count} memories")

    print("\n=== Testing search functionality ===")

    # Test search for each user
    print("\nSearching for user1...")
    results1 = await ltm.search(
        query="work",
        external_user_id="user1"
    )
    print(f"User1 search results: {len(results1)}")
    for r in results1:
        print(f"  - {r['text'][:50]}...")

    print("\nSearching for user2...")
    results2 = await ltm.search(
        query="work",
        external_user_id="user2"
    )
    print(f"User2 search results: {len(results2)}")
    for r in results2:
        print(f"  - {r['text'][:50]}...")

    print("\n✅ Database verification completed!")

if __name__ == "__main__":
    asyncio.run(main())
    os._exit(0)
