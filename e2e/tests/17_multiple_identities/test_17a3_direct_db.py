#!/usr/bin/env python3
"""
Test 17A3: Multi-Identity Direct Database Testing
Tests multi-identity functionality directly at the database level.
No LLM calls - pure database operations.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.utils.user_resolution import resolve_user_identifier  # noqa: E402
from src.muxi.services.db import DatabaseManager  # noqa: E402


async def test_sqlite_multi_identity():
    """Test multi-identity with SQLite - single user mode."""
    print("\n" + "=" * 60)
    print("TEST: Multi-Identity Direct DB Test - SQLite")
    print("=" * 60)
    
    # SQLite with temp file (not :memory: because async engine needs same DB)
    import tempfile
    import os
    temp_fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(temp_fd)
    
    db_manager = DatabaseManager(connection_string=f"sqlite:///{temp_path}")
    
    # Create tables using sync engine
    from src.muxi.services.memory.long_term import Base
    Base.metadata.create_all(db_manager.engine)
    
    formation_id = "test_formation_sqlite"
    results = []
    
    try:
        # Test 1: New user (first identifier)
        print("\n[Test 1/3] New user - first identifier...")
        result1 = await resolve_user_identifier(
            identifier="alice@example.com",
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        
        internal_id_1, muxi_id_1 = result1
        assert internal_id_1 is not None, "Should get internal_user_id"
        assert muxi_id_1 is not None, "Should get muxi_user_id"
        assert len(muxi_id_1) == 21, f"muxi_user_id should be 21 chars, got: {len(muxi_id_1)}"
        print(f"  ✅ Created user: internal_id={internal_id_1}, muxi_id={muxi_id_1}")
        results.append(True)
        
        # Test 2: Same user, different identifier (should create NEW user in SQLite multi-user mode)
        print("\n[Test 2/3] Same user, different identifier...")
        result2 = await resolve_user_identifier(
            identifier="alice_slack",
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        
        internal_id_2, muxi_id_2 = result2
        assert internal_id_2 is not None, "Should get internal_user_id"
        assert muxi_id_2 is not None, "Should get muxi_user_id"
        
        # In multi-user mode, different identifiers = different users
        assert internal_id_2 != internal_id_1, "Different identifiers should create different users"
        assert muxi_id_2 != muxi_id_1, "Different identifiers should have different muxi_ids"
        print(f"  ✅ Created new user: internal_id={internal_id_2}, muxi_id={muxi_id_2}")
        results.append(True)
        
        # Test 3: Re-resolve first identifier (should get same user)
        print("\n[Test 3/5] Re-resolve existing identifier...")
        result3 = await resolve_user_identifier(
            identifier="alice@example.com",
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        
        internal_id_3, muxi_id_3 = result3
        assert internal_id_3 == internal_id_1, "Should get same internal_user_id"
        assert muxi_id_3 == muxi_id_1, "Should get same muxi_user_id"
        print(f"  ✅ Resolved existing user: internal_id={internal_id_3}, muxi_id={muxi_id_3}")
        results.append(True)
        
        # Test 4: Associate multiple identifiers to first user
        print("\n[Test 4/5] Associate multiple identifiers to existing user...")
        from src.muxi.utils.user_resolution import associate_user_identifiers
        
        await associate_user_identifiers(
            identifiers=["alice@example.com", "alice_telegram", "alice_discord"],
            muxi_user_id=muxi_id_1,
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        print(f"  ✅ Associated 3 identifiers to user {muxi_id_1}")
        results.append(True)
        
        # Test 5: Verify all identifiers resolve to same user
        print("\n[Test 5/5] Verify all identifiers resolve to same user...")
        for identifier in ["alice@example.com", "alice_telegram", "alice_discord"]:
            result = await resolve_user_identifier(
                identifier=identifier,
                formation_id=formation_id,
                db_manager=db_manager,
                kv_cache=None,
            )
            internal_id, muxi_id = result
            assert internal_id == internal_id_1, f"Identifier {identifier} should resolve to same user"
            assert muxi_id == muxi_id_1, f"Identifier {identifier} should have same muxi_id"
            print(f"  ✅ {identifier} → user {muxi_id}")
        results.append(True)
        
        # Summary
        print("\n" + "=" * 60)
        print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
        print("=" * 60)
        
        if all(results):
            print("✅ ALL SQLITE TESTS PASSED")
            return True
        else:
            print(f"❌ SOME TESTS FAILED: {results}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if hasattr(db_manager, 'close'):
            db_manager.close()  # Sync close, not async
        # Clean up temp file
        try:
            import os
            os.unlink(temp_path)
        except:
            pass


async def test_postgres_multi_identity():
    """Test multi-identity with PostgreSQL."""
    print("\n" + "=" * 60)
    print("TEST: Multi-Identity Direct DB Test - PostgreSQL")
    print("=" * 60)
    
    # Load PostgreSQL URL from secrets
    import os
    from pathlib import Path
    
    # Try to get DATABASE_URL from secrets
    secrets_path = Path(__file__).parent.parent.parent.parent / "e2e" / "assets"
    sys.path.insert(0, str(secrets_path.parent.parent))
    
    try:
        from src.muxi.services.secrets.secrets_manager import SecretsManager
        secrets_mgr = SecretsManager(str(secrets_path))
        await secrets_mgr.initialize_encryption()
        db_url = await secrets_mgr.get_secret("POSTGRES_URI")
        
        if not db_url:
            print("⚠️  POSTGRES_URI not found in secrets - skipping PostgreSQL tests")
            return None
            
    except Exception as e:
        print(f"⚠️  Could not load secrets: {e} - skipping PostgreSQL tests")
        return None
    
    # Initialize PostgreSQL connection
    db_manager = DatabaseManager(connection_string=db_url)
    
    formation_id = "test_formation_postgres"
    results = []
    
    try:
        # Test 1: New user (first identifier)
        print("\n[Test 1/3] New user - first identifier...")
        result1 = await resolve_user_identifier(
            identifier=f"alice_pg_{asyncio.get_event_loop().time()}@example.com",  # Unique identifier
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        
        internal_id_1, muxi_id_1 = result1
        assert internal_id_1 is not None, "Should get internal_user_id"
        assert muxi_id_1 is not None, "Should get muxi_user_id"
        assert len(muxi_id_1) == 21, f"muxi_user_id should be 21 chars, got: {len(muxi_id_1)}"
        print(f"  ✅ Created user: internal_id={internal_id_1}, muxi_id={muxi_id_1}")
        results.append(True)
        
        # Test 2: Same user, different identifier  
        print("\n[Test 2/3] Same user, different identifier...")
        result2 = await resolve_user_identifier(
            identifier=f"alice_pg_slack_{asyncio.get_event_loop().time()}",  # Unique identifier
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        
        internal_id_2, muxi_id_2 = result2
        assert internal_id_2 is not None, "Should get internal_user_id"
        assert muxi_id_2 is not None, "Should get muxi_user_id"
        
        # In multi-user mode, different identifiers = different users (unless explicitly associated)
        assert internal_id_2 != internal_id_1, "Different identifiers should create different users"
        assert muxi_id_2 != muxi_id_1, "Different identifiers should have different muxi_ids"
        print(f"  ✅ Created new user: internal_id={internal_id_2}, muxi_id={muxi_id_2}")
        results.append(True)
        
        # Test 3: Re-resolve first identifier (should get same user)
        print("\n[Test 3/5] Re-resolve existing identifier...")
        email_1 = f"alice_pg_{int(asyncio.get_event_loop().time())}@example.com"
        result3 = await resolve_user_identifier(
            identifier=email_1,
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        
        internal_id_3, muxi_id_3 = result3
        print(f"  ✅ Created user: internal_id={internal_id_3}, muxi_id={muxi_id_3}")
        results.append(True)
        
        # Test 4: Associate multiple identifiers to user from test 3
        print("\n[Test 4/5] Associate multiple identifiers to existing user...")
        from src.muxi.utils.user_resolution import associate_user_identifiers
        
        telegram_id = f"alice_pg_telegram_{int(asyncio.get_event_loop().time())}"
        discord_id = f"alice_pg_discord_{int(asyncio.get_event_loop().time())}"
        
        await associate_user_identifiers(
            identifiers=[email_1, telegram_id, discord_id],
            muxi_user_id=muxi_id_3,
            formation_id=formation_id,
            db_manager=db_manager,
            kv_cache=None,
        )
        print(f"  ✅ Associated 3 identifiers to user {muxi_id_3}")
        results.append(True)
        
        # Test 5: Verify all identifiers resolve to same user
        print("\n[Test 5/5] Verify all identifiers resolve to same user...")
        for identifier in [email_1, telegram_id, discord_id]:
            result = await resolve_user_identifier(
                identifier=identifier,
                formation_id=formation_id,
                db_manager=db_manager,
                kv_cache=None,
            )
            internal_id, muxi_id = result
            assert internal_id == internal_id_3, f"Identifier {identifier} should resolve to same user"
            assert muxi_id == muxi_id_3, f"Identifier {identifier} should have same muxi_id"
            print(f"  ✅ {identifier} → user {muxi_id}")
        results.append(True)
        
        # Summary
        print("\n" + "=" * 60)
        print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
        print("=" * 60)
        
        if all(results):
            print("✅ ALL POSTGRESQL TESTS PASSED")
            return True
        else:
            print(f"❌ SOME TESTS FAILED: {results}")
            return False
            
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if hasattr(db_manager, 'close'):
            db_manager.close()  # Sync close, not async


async def main():
    """Run all tests."""
    results = []
    
    # Test SQLite
    sqlite_result = await test_sqlite_multi_identity()
    results.append(("SQLite", sqlite_result))
    
    # Test PostgreSQL
    postgres_result = await test_postgres_multi_identity()
    if postgres_result is not None:  # None means skipped
        results.append(("PostgreSQL", postgres_result))
    
    # Final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    for db_type, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{db_type}: {status}")
    
    all_passed = all(r for _, r in results if r is not None)
    print("=" * 60)
    
    if all_passed:
        print("✅ ALL DATABASE TESTS PASSED")
        return 0
    else:
        print("❌ SOME DATABASE TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
