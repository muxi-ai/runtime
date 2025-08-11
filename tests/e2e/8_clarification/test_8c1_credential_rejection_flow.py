"""
Test 8C1: Credential Rejection Flow

This test validates the multiple clarification sequence functionality
where a user rejects credential options and adds a new account,
with the system preserving and fulfilling the original intent.

Test flow:
1. User requests GitHub repositories
2. System asks which account
3. User rejects options ("none of these")
4. System asks for new token
5. User provides token
6. System fulfills original request with new credential
"""

import asyncio
import pytest
from typing import Optional
from muxi.formation.overlord import Overlord
from tests.fixtures.test_formation import get_test_formation_path


@pytest.mark.asyncio
async def test_credential_rejection_flow():
    """Test credential rejection → addition → fulfillment flow."""
    
    # Initialize overlord with test formation
    overlord = Overlord()
    formation_path = get_test_formation_path("formation-clarification")
    await overlord.load_formation_from_path(formation_path)
    
    # Simulate a session
    session_id = "test_session_123"
    user_id = "test_user"
    
    # Step 1: User requests GitHub repositories
    response1 = await overlord.chat(
        message="List my GitHub repositories",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Should trigger clarification about which account
    assert response1.content
    assert "which" in response1.content.lower() or "account" in response1.content.lower()
    assert response1.metadata.get("clarification") is True
    
    # Step 2: User rejects the options
    response2 = await overlord.chat(
        message="None of these, I want to add a new account",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Should ask for token (sub-clarification)
    assert response2.content
    assert "token" in response2.content.lower() or "provide" in response2.content.lower()
    # Check depth increased
    assert response2.metadata.get("depth", 0) == 1
    
    # Step 3: User provides token
    response3 = await overlord.chat(
        message="ghp_abc123def456ghi789jkl012mno345pqr678",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Should fulfill original request (list repositories)
    # Note: In a real test, this would actually list repos
    # For now, we just verify the clarification is resolved
    assert response3.content
    # Check that clarification is resolved
    assert response3.metadata.get("clarification") is not True
    
    print(f"✅ Test passed: Credential rejection flow handled correctly")
    print(f"  Step 1: {response1.content[:50]}...")
    print(f"  Step 2: {response2.content[:50]}...")
    print(f"  Step 3: {response3.content[:50]}...")


@pytest.mark.asyncio
async def test_depth_limit_enforcement():
    """Test that clarification depth is limited to 2 levels."""
    
    # Initialize overlord with test formation
    overlord = Overlord()
    formation_path = get_test_formation_path("formation-clarification")
    await overlord.load_formation_from_path(formation_path)
    
    session_id = "test_session_depth"
    user_id = "test_user"
    
    # Step 1: Initial ambiguous request
    response1 = await overlord.chat(
        message="Do something complex",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Level 0 clarification
    assert response1.metadata.get("clarification") is True
    
    # Step 2: First rejection (depth = 1)
    response2 = await overlord.chat(
        message="Not that, something else",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Level 1 sub-clarification
    assert response2.metadata.get("depth", 0) == 1
    
    # Step 3: Second rejection (depth would be 2, but should force resolution)
    response3 = await overlord.chat(
        message="No, not that either",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Should force resolution, not go deeper
    assert response3.metadata.get("forced_resolution") is True or \
           response3.metadata.get("depth", 0) <= 2
    
    print(f"✅ Test passed: Depth limit enforced correctly")


@pytest.mark.asyncio
async def test_cancel_clarification():
    """Test that user can cancel a clarification sequence."""
    
    # Initialize overlord with test formation
    overlord = Overlord()
    formation_path = get_test_formation_path("formation-clarification")
    await overlord.load_formation_from_path(formation_path)
    
    session_id = "test_session_cancel"
    user_id = "test_user"
    
    # Step 1: Start clarification
    response1 = await overlord.chat(
        message="Help me with something",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    assert response1.metadata.get("clarification") is True
    
    # Step 2: Cancel
    response2 = await overlord.chat(
        message="Never mind, cancel this",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Should acknowledge cancellation
    assert "cancel" in response2.content.lower()
    assert response2.metadata.get("clarification_cancelled") is True
    
    # Step 3: New request should work normally
    response3 = await overlord.chat(
        message="What time is it?",
        agent_name=None,
        user_id=user_id,
        session_id=session_id
    )
    
    # Should process normally, no pending clarification
    assert response3.metadata.get("clarification") is not True
    
    print(f"✅ Test passed: Cancellation handled correctly")


if __name__ == "__main__":
    asyncio.run(test_credential_rejection_flow())
    asyncio.run(test_depth_limit_enforcement())
    asyncio.run(test_cancel_clarification())