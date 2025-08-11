#!/usr/bin/env python3
"""Test to verify SQLite database records are created properly"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import asyncio
import os
import sqlite3
import json

from muxi.services.memory.sqlite import SQLiteMemory

# Create mock LLM for embedding
class MockLLM:
    async def get_embedding(self, text):
        # Return a simple mock embedding
        return [0.1] * 1536

async def main():
    # Use SQLite database
    """
    Runs an end-to-end test of the SQLiteMemory class, including database creation, memory insertion, direct table verification, search queries, and retrieval of recent memories.

    This coroutine creates a new SQLite database, adds sample memory records with mock embeddings, verifies the contents via direct SQL queries, tests search functionality, and prints results for manual inspection. The database file is removed and recreated to ensure a clean test environment.
    """
    db_path = "test_sqlite_memory.db"

    # Remove existing database file
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    print(f"Creating SQLite database: {db_path}")

    # Create SQLiteMemory
    print("Creating SQLiteMemory instance...")
    sqlite_memory = SQLiteMemory(
        db_path=db_path,
        formation_id="test_formation",
        dimension=1536,
        default_collection="default"
    )

    # Set embedding provider
    sqlite_memory.embedding_provider = MockLLM()

    print("\n=== Adding test data ===")

    # SQLite is single-user mode
    print("\nAdding memory (single-user mode)...")
    await sqlite_memory.add(
        content="My name is Alice and I work at TechCorp",
        metadata={"type": "personal_info"}
    )
    print("✓ Added memory 1")

    print("\nAdding another memory...")
    await sqlite_memory.add(
        content="I love Python programming",
        metadata={"type": "preference"}
    )
    print("✓ Added memory 2")

    print("\nAdding third memory...")
    await sqlite_memory.add(
        content="I work on AI agent frameworks",
        metadata={"type": "work"}
    )
    print("✓ Added memory 3")

    # Now check what's in the database
    print("\n=== Verifying database contents ===")

    # Direct SQLite queries
    conn = sqlite3.connect(db_path)

    # Check collections table
    print("\n--- COLLECTIONS TABLE ---")
    cursor = conn.execute("SELECT * FROM collections")
    collections = cursor.fetchall()
    print(f"Total collections: {len(collections)}")
    for coll in collections:
        print(f"  Collection ID: {coll[0]}, Name: {coll[1]}, Description: {coll[2]}")

    # Check memories table
    print("\n--- MEMORIES TABLE ---")
    cursor = conn.execute("SELECT id, collection, text, metadata, created_at FROM memories")
    memories = cursor.fetchall()
    print(f"Total memories: {len(memories)}")
    for mem in memories:
        metadata = json.loads(mem[3]) if mem[3] else {}
        print(f"  Memory ID: {mem[0]}, Collection: {mem[1]}")
        print(f"    Content: {mem[2][:50]}...")
        print(f"    Metadata: {metadata}")
        print(f"    Created: {mem[4]}")

    conn.close()

    print("\n=== Testing search functionality ===")

    # Test search
    print("\nSearching for 'work'...")
    results = await sqlite_memory.search(query="work", limit=5)
    print(f"Search results: {len(results)}")
    for r in results:
        print(f"  - {r['content'][:50]}... (score: {r['score']:.3f})")

    print("\nSearching for 'Python'...")
    results2 = await sqlite_memory.search(query="Python", limit=5)
    print(f"Search results: {len(results2)}")
    for r in results2:
        print(f"  - {r['content'][:50]}... (score: {r['score']:.3f})")

    print("\n=== Testing recent memories ===")
    recent = sqlite_memory.get_recent_memories(limit=10)
    print(f"Recent memories: {len(recent)}")
    for r in recent:
        print(f"  - {r['text'][:50]}...")

    print(f"\n✅ SQLite database verification completed!")
    print(f"Database file: {os.path.abspath(db_path)}")

if __name__ == "__main__":
    asyncio.run(main())
    os._exit(0)
