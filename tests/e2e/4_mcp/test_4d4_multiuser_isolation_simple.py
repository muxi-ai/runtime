#!/usr/bin/env python3
"""Test 4D4: Multi-User Isolation - Simplified version that tests credential isolation"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import os  # noqa: E402
os.environ["POSTGRES_DATABASE_URL"] = "postgresql://ran:@localhost:5432/muxi_framework"  # noqa: E402

from muxi.formation.memory.credential_resolver import CredentialResolver, Credential, User  # noqa: E402
from muxi.services.db import get_database_manager  # noqa: E402
from sqlalchemy import select  # noqa: E402


async def test_credential_isolation():
    """Test that credentials are properly isolated between users."""

    print("\n" + "="*80)
    print("TEST 4D4: Multi-User Credential Isolation (Simplified)")
    print("Goal: Verify credential storage and retrieval is isolated per user")
    print("="*80)

    # Get database manager
    db_manager = get_database_manager()

    # Create credential resolver
    formation_id = "test_formation_4d4"
    credential_resolver = CredentialResolver(
        async_session_maker=db_manager.AsyncSession,
        formation_id=formation_id
    )

    print("\n1. Setting up test credentials...")

    # Store credentials for different users
    await credential_resolver.store_credential(
        user_id="alice_4d4_test",
        service="github",
        credentials={"token": "alice_secret_token"},
        credential_name="alice_github"
    )
    print("   ✅ Stored credential for alice_4d4_test")

    await credential_resolver.store_credential(
        user_id="bob_4d4_test",
        service="github",
        credentials={"token": "bob_secret_token"},
        credential_name="bob_github"
    )
    print("   ✅ Stored credential for bob_4d4_test")

    print("\n2. Testing credential retrieval and isolation...")

    # Test 1: Alice can retrieve her credential
    alice_cred = await credential_resolver.resolve("alice_4d4_test", "github")
    if alice_cred and alice_cred.get("token") == "alice_secret_token":
        print("   ✅ Alice retrieved her own credential correctly")
    else:
        print("   ❌ Alice could not retrieve her credential")
        return False

    # Test 2: Bob can retrieve his credential
    bob_cred = await credential_resolver.resolve("bob_4d4_test", "github")
    if bob_cred and bob_cred.get("token") == "bob_secret_token":
        print("   ✅ Bob retrieved his own credential correctly")
    else:
        print("   ❌ Bob could not retrieve his credential")
        return False

    # Test 3: Charlie has no credential
    charlie_cred = await credential_resolver.resolve("charlie_4d4_test", "github")
    if charlie_cred is None:
        print("   ✅ Charlie correctly has no credential")
    else:
        print("   ❌ Charlie somehow has a credential (security issue!)")
        return False

    # Test 4: Verify credentials are different
    if alice_cred.get("token") != bob_cred.get("token"):
        print("   ✅ Alice and Bob have different credentials (isolated)")
    else:
        print("   ❌ Alice and Bob have the same credential (not isolated!)")
        return False

    print("\n3. Testing database-level isolation...")

    # Check database directly
    async with db_manager.get_async_session() as session:
        # Count total GitHub credentials
        stmt = (
            select(Credential)
            .join(User, Credential.user_id == User.id)
            .where(
                User.formation_id == formation_id,
                Credential.service == "github"
            )
        )
        result = await session.execute(stmt)
        all_creds = result.scalars().all()

        print(f"   Total GitHub credentials for formation {formation_id}: {len(all_creds)}")

        # Verify each user's credential
        for external_user_id in ["alice_4d4_test", "bob_4d4_test"]:
            stmt = (
                select(Credential)
                .join(User, Credential.user_id == User.id)
                .where(
                    User.external_user_id == external_user_id,
                    User.formation_id == formation_id,
                    Credential.service == "github"
                )
            )
            result = await session.execute(stmt)
            user_creds = result.scalars().all()

            if len(user_creds) == 1:
                print(f"   ✅ {external_user_id} has exactly 1 GitHub credential")
            else:
                print(f"   ❌ {external_user_id} has {len(user_creds)} GitHub credentials (expected 1)")
                return False

    print("\n4. Testing credential update isolation...")

    # Update Alice's credential
    await credential_resolver.store_credential(
        user_id="alice_4d4_test",
        service="github",
        credentials={"token": "alice_new_token"},
        credential_name="alice_github_updated"
    )

    # Verify Alice's credential was updated
    alice_new_cred = await credential_resolver.resolve("alice_4d4_test", "github")
    bob_unchanged = await credential_resolver.resolve("bob_4d4_test", "github")

    if alice_new_cred.get("token") == "alice_new_token" and bob_unchanged.get("token") == "bob_secret_token":
        print("   ✅ Alice's credential updated without affecting Bob's")
    else:
        print("   ❌ Credential update affected other users")
        return False

    print("\n5. Testing credential deletion isolation...")

    # Delete Alice's credential
    await credential_resolver.delete_credential("alice_4d4_test", "github")

    # Verify deletion
    alice_deleted = await credential_resolver.resolve("alice_4d4_test", "github")
    bob_still_exists = await credential_resolver.resolve("bob_4d4_test", "github")

    if alice_deleted is None and bob_still_exists is not None:
        print("   ✅ Alice's credential deleted without affecting Bob's")
    else:
        print("   ❌ Credential deletion affected other users")
        return False

    # Clean up Bob's credential
    await credential_resolver.delete_credential("bob_4d4_test", "github")

    return True


async def main():
    """Run the test."""
    print("Starting Test 4D4: Multi-User Credential Isolation (Simplified)")

    try:
        success = await test_credential_isolation()

        print("\n" + "="*80)
        if success:
            print("✅ Test 4D4 PASSED: Multi-user credential isolation working correctly!")
            print("\nSummary:")
            print("  ✓ Each user can store their own credentials")
            print("  ✓ Users can only access their own credentials")
            print("  ✓ Credentials are isolated at the database level")
            print("  ✓ Updates to one user's credentials don't affect others")
            print("  ✓ Deletions are isolated per user")
        else:
            print("❌ Test 4D4 FAILED: Credential isolation issues detected")
        print("="*80)

        # Clean up
        db_manager = get_database_manager()
        await db_manager.close_async()

        # Force exit
        import os
        os._exit(0 if success else 1)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        import os
        os._exit(1)


if __name__ == "__main__":
    asyncio.run(main())
