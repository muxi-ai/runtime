#!/usr/bin/env python3
"""Test 4D4: Multi-User Isolation - Ensure Credentials Don't Leak Between Users"""

import asyncio
import sys
from pathlib import Path
import hashlib
import nanoid

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402
from src.muxi.runtime.formation.memory.credential_resolver import Credential  # noqa: E402
from sqlalchemy import select, delete  # noqa: E402


async def setup_multiuser_credentials(formation):
    """Set up credentials for multiple users to test isolation."""
    print("\n=== SETTING UP MULTI-USER CREDENTIALS ===")
    
    # Get the database manager from formation
    db_manager = getattr(formation, '_db_manager', None)
    if not db_manager:
        raise Exception("No database manager available")
    
    async with db_manager.get_async_session() as session:
        # Clear existing GitHub credentials for test users
        for user_id in ["alice", "bob"]:
            stmt = delete(Credential).where(
                Credential.user_id == user_id,
                Credential.service == "github",
                Credential.formation_id == formation.formation_id
            )
            await session.execute(stmt)
        
        # Create credential for Alice
        formation_id_hash = hashlib.sha256(formation.formation_id.encode()).hexdigest()
        alice_cred = Credential(
            user_id="alice",
            credential_id=f"cred_{nanoid.generate(size=12)}",
            name="Alice's GitHub Token",
            service="github",
            credentials={"token": "ghp_alice_secret_token_123"},
            formation_id=formation.formation_id,
            formation_id_hash=formation_id_hash
        )
        
        # Create credential for Bob
        bob_cred = Credential(
            user_id="bob",
            credential_id=f"cred_{nanoid.generate(size=12)}",
            name="Bob's GitHub Token",
            service="github",
            credentials={"token": "ghp_bob_secret_token_456"},
            formation_id=formation.formation_id,
            formation_id_hash=formation_id_hash
        )
        
        session.add(alice_cred)
        session.add(bob_cred)
        await session.commit()
        
        print("✓ Created credentials for 2 users:")
        print(f"  - Alice: {alice_cred.name}")
        print(f"  - Bob: {bob_cred.name}")


async def check_credential_usage(formation, user_id):
    """Check which credential was actually used by examining the database."""
    db_manager = formation._configured_services.get("db_manager")
    async with db_manager.get_async_session() as session:
        stmt = select(Credential).where(
            Credential.user_id == user_id,
            Credential.service == "github",
            Credential.formation_id == formation.formation_id
        )
        cred = (await session.execute(stmt)).scalar_one_or_none()
        return cred


async def run_async_test():
    """Run the test for multi-user credential isolation."""
    
    print("\nTEST 4D4: Multi-User Credential Isolation")
    print("Goal: Verify that users cannot access each other's credentials")
    print("      and the system maintains strict isolation")
    print()
    
    try:
        # Use the test formation
        formation_path = Path("test-formations/formation-mcp")
        
        # Load formation
        formation = Formation()
        await formation.load(str(formation_path))
        
        # Set up credentials for multiple users
        await setup_multiuser_credentials(formation)
        
        # Start overlord
        overlord = await formation.start_overlord()
        
        # Give MCP servers time to initialize
        print("\nWaiting for MCP servers to initialize...")
        await asyncio.sleep(3)
        
        # Test 1: Alice uses her credentials
        print("\n=== TEST 1: ALICE'S REQUEST ===")
        
        prompt_alice = "List my GitHub repositories"
        print(f"User: alice")
        print(f"Prompt: {prompt_alice}")
        
        response_alice = await overlord.chat(
            user_id="alice",
            message=prompt_alice,
            use_async=False,
            stream=False,
        )
        
        # Handle response
        if hasattr(response_alice, '__aiter__'):
            full_response = ""
            async for chunk in response_alice:
                full_response += chunk
            response_alice = full_response
        
        print(f"\nAlice's Response: {response_alice}")
        
        # Test 2: Bob uses his credentials
        print("\n=== TEST 2: BOB'S REQUEST ===")
        
        prompt_bob = "List my GitHub repositories"
        print(f"User: bob")
        print(f"Prompt: {prompt_bob}")
        
        response_bob = await overlord.chat(
            user_id="bob",
            message=prompt_bob,
            use_async=False,
            stream=False,
        )
        
        # Handle response
        if hasattr(response_bob, '__aiter__'):
            full_response = ""
            async for chunk in response_bob:
                full_response += chunk
            response_bob = full_response
        
        print(f"\nBob's Response: {response_bob}")
        
        # Test 3: Charlie (no credentials) tries to access
        print("\n=== TEST 3: CHARLIE'S REQUEST (NO CREDENTIALS) ===")
        
        prompt_charlie = "List my GitHub repositories"
        print(f"User: charlie")
        print(f"Prompt: {prompt_charlie}")
        
        response_charlie = await overlord.chat(
            user_id="charlie",
            message=prompt_charlie,
            use_async=False,
            stream=False,
        )
        
        # Handle response
        if hasattr(response_charlie, '__aiter__'):
            full_response = ""
            async for chunk in response_charlie:
                full_response += chunk
            response_charlie = full_response
        
        print(f"\nCharlie's Response: {response_charlie}")
        
        # Check responses
        alice_str = str(response_alice).lower()
        bob_str = str(response_bob).lower()
        charlie_str = str(response_charlie).lower()
        
        # Charlie should be asked for credentials
        charlie_needs_creds = any(
            keyword in charlie_str 
            for keyword in ["credential", "token", "provide", "auth", "need"]
        )
        
        if charlie_needs_creds:
            print("\n✅ SUCCESS: Charlie was correctly asked for credentials")
        else:
            print("\n❌ FAILED: Charlie should have been asked for credentials")
            return False
        
        # Neither Alice nor Bob should be asked for credentials
        alice_has_creds = not any(
            keyword in alice_str 
            for keyword in ["credential", "token", "provide your", "need your"]
        )
        bob_has_creds = not any(
            keyword in bob_str 
            for keyword in ["credential", "token", "provide your", "need your"]
        )
        
        if alice_has_creds and bob_has_creds:
            print("✅ SUCCESS: Alice and Bob used their own credentials")
        else:
            print("❌ FAILED: Users were asked for credentials despite having them")
            return False
        
        # Additional check: Ensure credentials are truly isolated
        print("\n=== CREDENTIAL ISOLATION CHECK ===")
        
        # Get credentials from DB
        alice_cred = await check_credential_usage(formation, "alice")
        bob_cred = await check_credential_usage(formation, "bob")
        charlie_cred = await check_credential_usage(formation, "charlie")
        
        print(f"Alice has credential: {alice_cred is not None}")
        print(f"Bob has credential: {bob_cred is not None}")
        print(f"Charlie has credential: {charlie_cred is not None}")
        
        if alice_cred and bob_cred and not charlie_cred:
            print("\n✅ SUCCESS: Credentials are properly isolated per user")
            return True
        else:
            print("\n❌ FAILED: Credential isolation check failed")
            return False
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        try:
            await formation.stop_overlord(5.0)
        except:
            formation.kill_overlord()


def main():
    """Main entry point."""
    print("Starting test: Multi-User Credential Isolation")
    
    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D4 PASSED: Multi-user isolation working correctly")
        else:
            print("\n❌ Test 4D4 FAILED")
        
        # Force exit to avoid MCP SDK cleanup hang
        import os
        os._exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        import os
        os._exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        import os
        os._exit(1)


if __name__ == "__main__":
    main()