"""
Integration tests for async SQLAlchemy implementation.

Tests the async database operations to ensure they work correctly
and provide the expected performance improvements.
"""

import asyncio
import time
from typing import List
import pytest
import tempfile

from muxi.runtime.services.db import DatabaseManager
from muxi.runtime.services.memory.long_term import LongTermMemory, User, Memory, Collection


class MockEmbeddingModel:
    """Mock embedding model for testing."""
    
    async def embed(self, text: str) -> List[float]:
        """Return a simple embedding based on text length."""
        # Simple embedding: normalize text length to 1536 dimensions
        embedding = [0.0] * 1536
        for i, char in enumerate(text[:1536]):
            embedding[i] = ord(char) / 255.0
        return embedding


@pytest.mark.asyncio
async def test_async_database_operations():
    """Test basic async database operations."""
    # Create temporary SQLite database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    # Initialize database manager
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    
    # Create tables
    from muxi.runtime.services.memory.long_term import Base as MemoryBase
    db_manager.create_tables(MemoryBase.metadata)
    
    # Create tables
    from muxi.runtime.services.memory.long_term import Base as MemoryBase
    db_manager.create_tables(MemoryBase.metadata)
    
    # Test async session creation
    async with db_manager.get_async_session() as session:
        # Create a test user
        user = await User.create(
            session,
            external_user_id="test_user",
            external_user_id_hash="test_hash",
            formation_id="test_formation",
            formation_id_hash="formation_hash"
        )
        assert user.id is not None
        
        # Query the user
        found_user = await User.get(
            session,
            external_user_id="test_user",
            formation_id="test_formation"
        )
        assert found_user is not None
        assert found_user.id == user.id
    
    # Cleanup
    db_manager.close()


@pytest.mark.asyncio
async def test_async_memory_operations():
    """Test async memory storage and retrieval."""
    # Create temporary SQLite database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    # Initialize components
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    
    # Create tables
    from muxi.runtime.services.memory.long_term import Base as MemoryBase
    db_manager.create_tables(MemoryBase.metadata)
    
    # Create tables
    from muxi.runtime.services.memory.long_term import Base as MemoryBase
    db_manager.create_tables(MemoryBase.metadata)
    embedding_model = MockEmbeddingModel()
    memory = LongTermMemory(
        db_manager=db_manager,
        formation_id="test_formation",
        embedding_model=embedding_model
    )
    
    # Test async memory operations
    start_time = time.time()
    
    # Add memories
    memory_ids = []
    for i in range(10):
        memory_id = await memory.add(
            content=f"Test memory {i}: This is a test of async database operations.",
            metadata={"index": i, "test": True},
            external_user_id="test_user"
        )
        memory_ids.append(memory_id)
    
    # Search memories
    results = await memory.search(
        query="test async database",
        limit=5,
        external_user_id="test_user"
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Verify results
    assert len(results) > 0
    assert len(results) <= 5
    assert all('text' in result for result in results)
    assert all('score' in result for result in results)
    
    print(f"Async operations completed in {duration:.3f} seconds")
    
    # Cleanup
    await db_manager.close_async()


@pytest.mark.asyncio
async def test_async_vs_sync_performance():
    """Compare performance of async vs sync operations."""
    # Create temporary SQLite database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    
    # Create tables
    from muxi.runtime.services.memory.long_term import Base as MemoryBase
    db_manager.create_tables(MemoryBase.metadata)
    
    # Test sync operations
    sync_start = time.time()
    with db_manager.get_session() as session:
        for i in range(50):
            user = User(
                external_user_id=f"sync_user_{i}",
                external_user_id_hash=f"sync_hash_{i}",
                formation_id="test_formation",
                formation_id_hash="formation_hash"
            )
            session.add(user)
        session.commit()
    sync_duration = time.time() - sync_start
    
    # Test async operations
    async_start = time.time()
    async with db_manager.get_async_session() as session:
        # Create users concurrently
        tasks = []
        for i in range(50):
            task = User.create(
                session,
                external_user_id=f"async_user_{i}",
                external_user_id_hash=f"async_hash_{i}",
                formation_id="test_formation",
                formation_id_hash="formation_hash"
            )
            tasks.append(task)
        await asyncio.gather(*tasks)
    async_duration = time.time() - async_start
    
    print(f"Sync operations: {sync_duration:.3f}s")
    print(f"Async operations: {async_duration:.3f}s")
    print(f"Speedup: {sync_duration/async_duration:.2f}x")
    
    # Async should be faster for concurrent operations
    assert async_duration < sync_duration * 1.5  # Allow some overhead
    
    # Cleanup
    await db_manager.close_async()


@pytest.mark.asyncio
async def test_async_model_mixin_methods():
    """Test AsyncModelMixin helper methods."""
    # Create temporary SQLite database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    
    # Create tables
    from muxi.runtime.services.memory.long_term import Base as MemoryBase
    db_manager.create_tables(MemoryBase.metadata)
    
    async with db_manager.get_async_session() as session:
        # Test create
        user = await User.create(
            session,
            external_user_id="mixin_test",
            external_user_id_hash="mixin_hash",
            formation_id="test_formation",
            formation_id_hash="formation_hash"
        )
        
        # Test get
        found = await User.get(session, id=user.id)
        assert found is not None
        assert found.external_user_id == "mixin_test"
        
        # Test update
        await found.update(session, external_user_id="updated_mixin_test")
        
        # Verify update
        updated = await User.get(session, id=user.id)
        assert updated.external_user_id == "updated_mixin_test"
        
        # Test get_all
        all_users = await User.get_all(session, formation_id="test_formation")
        assert len(all_users) >= 1
        
        # Test delete
        await updated.delete(session)
        
        # Verify deletion
        deleted = await User.get(session, id=user.id)
        assert deleted is None
    
    # Cleanup
    await db_manager.close_async()


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_async_database_operations())
    asyncio.run(test_async_memory_operations())
    asyncio.run(test_async_vs_sync_performance())
    asyncio.run(test_async_model_mixin_methods())
    print("All async database tests passed!")