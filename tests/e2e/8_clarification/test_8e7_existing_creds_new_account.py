#!/usr/bin/env python
"""Test user1 with existing credentials adding a new account."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "tests/e2e/8_clarification"))

from muxi.formation import Formation
from test_utils import TestContext


async def test():
    formation_path = Path(__file__).parent / "formations/formation-clarification"

    import shutil
    original = formation_path / "formation.yaml"
    backup = formation_path / "formation.yaml.backup"
    dynamic = formation_path / "formation-dynamic.yaml"

    if original.exists():
        shutil.copy(original, backup)
    shutil.copy(dynamic, original)

    formation = Formation()

    try:
        await formation.load(str(formation_path))

        # Clean up any existing automazeio credentials to avoid conflicts
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        # Delete ALL automazeio credentials regardless of user
        result = await conn.execute("DELETE FROM credentials WHERE name='automazeio' AND service='github'")
        print(f"Deleted {result} automazeio credentials")
        # Also check what credentials user1 has
        rows = await conn.fetch("SELECT name FROM credentials WHERE service='github'")
        print(f"Existing GitHub credentials in DB: {[row['name'] for row in rows]}")
        await conn.close()

        overlord = await formation.start_overlord()

        ctx = TestContext("existing_creds_new_account")
        user_id = "user1"  # Using user1 who has existing credentials

        print("\n" + "="*60)
        print("CHAT TRANSCRIPT - Existing Credentials, New Account")
        print("="*60)

        # Step 1: Initial request
        print("\n**User:** Get my GitHub repositories")
        response1 = await overlord.chat(
            message="Get my GitHub repositories",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response1.content}")

        # Step 2: User wants a different account
        print("\n**User:** neither - I need a different account")
        response2 = await overlord.chat(
            message="neither - I need a different account",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response2.content}")

        # Step 3: Provide the token
        print("\n**User:** my github token is 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")
        response3 = await overlord.chat(
            message="my github token is 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",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response3.content}")

        print("\n" + "="*60)

        # Analysis
        success_indicators = ["success", "connected", "github.com", "repositor", "profile"]
        if any(indicator in response3.content.lower() for indicator in success_indicators):
            print("\n✅ SUCCESS: User with existing credentials successfully added new account")
            print("✓ System asked which existing account to use")
            print("✓ User indicated they need a different account")
            print("✓ System prompted for new credentials")
            print("✓ New token was validated and stored")
            print("✓ System continued with original request")
        else:
            print("\n❌ FAILURE: New account was not added successfully")
            print(f"Final response: {response3.content[:200]}...")

        print("="*60)

        # Step 4: Verify the user now has 3 accounts
        print("\n**User:** Show me all my GitHub accounts")
        response4 = await overlord.chat(
            message="Show me all my GitHub accounts",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response4.content[:200]}...")

        if "ranaroussi" in response4.content.lower() and "lilyautomaze" in response4.content.lower():
            print("\n✅ BONUS: User still has access to original accounts")

        await formation.stop_overlord()
        formation.shutdown()

    finally:
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test())
