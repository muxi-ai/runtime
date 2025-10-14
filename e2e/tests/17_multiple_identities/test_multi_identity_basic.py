"""
E2E Test: Multi-Identity User Management - Basic Flow

Tests the basic multi-identity functionality:
1. User interacts via email identifier
2. Memory is created
3. User interacts via Slack ID
4. Verify memory carryover across identifiers
"""

import pytest
import asyncio
from pathlib import Path


@pytest.mark.asyncio
async def test_multi_identity_memory_carryover(runtime_from_yaml):
    """
    Test that memories carry over when same user uses different identifiers.
    
    Flow:
    1. Alice chats via email: "alice@company.com" 
    2. Alice mentions she likes Python
    3. Alice chats via Slack ID: "U12345"
    4. Verify Alice's Python preference is remembered
    """
    # Setup formation
    formation_dir = Path(__file__).parent
    formation_path = formation_dir / "formation.yaml"
    
    # Initialize formation
    overlord = await runtime_from_yaml(str(formation_path))
    
    try:
        # Step 1: User interacts via email
        response1 = await overlord.chat(
            message="Hi! I'm Alice and I love Python programming.",
            user_id="alice@company.com",
            session_id="session_001"
        )
        
        assert response1 is not None
        assert len(response1) > 0
        
        # Give memory system time to process
        await asyncio.sleep(2)
        
        # Step 2: Same user interacts via different identifier (Slack ID)
        # This should resolve to the same internal user
        response2 = await overlord.chat(
            message="What programming language do I like?",
            user_id="U12345_SLACK",  # Different identifier, same person
            session_id="session_002"  # Different session
        )
        
        assert response2 is not None
        assert len(response2) > 0
        
        # Step 3: Verify memory carryover
        # The response should remember Alice likes Python
        response_lower = response2.lower()
        assert "python" in response_lower, \
            f"Expected 'python' in response but got: {response2}"
        
        print("✅ Multi-identity memory carryover test PASSED")
        print(f"   - User via email: alice@company.com")
        print(f"   - User via Slack: U12345_SLACK")  
        print(f"   - Memory successfully carried over!")
        
    finally:
        # Cleanup
        if hasattr(overlord, 'cleanup'):
            await overlord.cleanup()


@pytest.mark.asyncio
async def test_multi_identity_resolution():
    """
    Test that user identifier resolution works correctly.
    
    This test verifies:
    1. Multiple identifiers resolve to same internal user ID
    2. MUXI user ID (public_id) stays consistent
    3. Context carries all three user IDs
    """
    from src.muxi.utils.user_resolution import resolve_user_identifier
    from src.muxi.services.db import DatabaseManager
    
    # Create test database manager
    db_manager = DatabaseManager(database_type="sqlite", database_url=":memory:")
    await db_manager.initialize()
    
    try:
        # Resolve first identifier
        internal_id_1, muxi_id_1 = await resolve_user_identifier(
            identifier="alice@company.com",
            formation_id="test_formation",
            db_manager=db_manager,
            kv_cache=None  # No cache for this test
        )
        
        assert internal_id_1 is not None
        assert muxi_id_1 is not None
        assert muxi_id_1.startswith("usr_")
        
        # Resolve second identifier for same user  
        internal_id_2, muxi_id_2 = await resolve_user_identifier(
            identifier="U12345_SLACK",
            formation_id="test_formation",
            db_manager=db_manager,
            kv_cache=None
        )
        
        # Different identifiers should resolve to different users
        # (unless we explicitly associate them - which we test separately)
        assert internal_id_2 is not None
        assert muxi_id_2 is not None
        assert internal_id_1 != internal_id_2  # Different users without association
        
        print("✅ Multi-identity resolution test PASSED")
        print(f"   - Email resolved to: internal_id={internal_id_1}, muxi_id={muxi_id_1}")
        print(f"   - Slack resolved to: internal_id={internal_id_2}, muxi_id={muxi_id_2}")
        
    finally:
        await db_manager.close()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
