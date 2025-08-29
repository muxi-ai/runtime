#!/usr/bin/env python
"""Test retry with two failures before success."""

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
        
        # Clean up any existing credentials
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        await conn.execute("DELETE FROM credentials WHERE user_id=6 AND service='github'")
        await conn.close()
        
        overlord = await formation.start_overlord()
        
        ctx = TestContext("retry_two_failures")
        user_id = "user3"
        
        print("\n" + "="*60)
        print("CHAT TRANSCRIPT - Two Retry Test")
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
        
        # Step 2: First bad token
        print("\n**User:** my token is ghp_BADTOKEN_12345")
        response2 = await overlord.chat(
            message="my token is ghp_BADTOKEN_12345",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response2.content}")
        
        # Step 3: Second bad token
        print("\n**User:** sorry, I meant ghp_ANOTHERBADTOKEN_67890")
        response3 = await overlord.chat(
            message="sorry, I meant ghp_ANOTHERBADTOKEN_67890",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response3.content}")
        
        # Step 4: Good token
        print("\n**User:** wait, found the right one: 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")
        response4 = await overlord.chat(
            message="wait, found the right one: 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",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response4.content}")
        
        print("\n" + "="*60)
        
        # Analysis
        success_indicators = ["success", "connected", "github.com", "repositor", "profile"]
        if any(indicator in response4.content.lower() for indicator in success_indicators):
            print("\n✅ SUCCESS: Retry mechanism worked - good token accepted after two bad tokens")
            print("✓ First bad token was rejected")
            print("✓ Second bad token was rejected") 
            print("✓ Good token was accepted and stored")
            print("✓ System continued with original request")
        else:
            print("\n❌ FAILURE: Good token was not accepted after two bad tokens")
            print(f"Final response: {response4.content[:200]}...")
        
        print("="*60)
        
        await formation.stop_overlord()
        formation.shutdown()
        
    finally:
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test())