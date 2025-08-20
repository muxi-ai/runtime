#!/usr/bin/env python
"""Debug test for 8B baseline timeout issue"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from muxi import Formation
sys.path.insert(0, str(Path(__file__).parent / "tests" / "e2e" / "8_clarification"))
from test_utils import TestContext


async def run_test():
    """Run minimal test to reproduce timeout."""
    formation = None
    try:
        print("\n=== Test 8B Debug ===\n")
        
        # Load formation
        formation_path = Path(__file__).parent / "tests/e2e/8_clarification/formations/formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create test context
        ctx = TestContext("test_8b_debug")
        print(f"User: {ctx.user_id}, Session: {ctx.session_id}\n")
        
        # Test 1: Simple greeting (works)
        print("1. Testing greeting...")
        response1 = await asyncio.wait_for(
            overlord.chat("Hi", user_id=ctx.user_id, session_id=ctx.session_id, stream=False),
            timeout=5.0
        )
        content1 = response1.content if hasattr(response1, 'content') else str(response1)
        print(f"   ✓ Response received: {content1[:50]}...")
        
        # Test 2: Statement (works)
        print("\n2. Testing statement...")
        response2 = await asyncio.wait_for(
            overlord.chat("I'm working on Python", user_id=ctx.user_id, session_id=ctx.session_id, stream=False),
            timeout=5.0
        )
        content2 = response2.content if hasattr(response2, 'content') else str(response2)
        print(f"   ✓ Response received: {content2[:50]}...")
        
        # Test 3: Context question (hangs)
        print("\n3. Testing context question (this may hang)...")
        print("   Adding debug logging to overlord...")
        
        # Monkey patch to add debug logging
        original_process = overlord._process_sync_chat
        async def debug_process(*args, **kwargs):
            print(f"   DEBUG: _process_sync_chat called with skip_clarification={kwargs.get('skip_clarification', False)}")
            result = await original_process(*args, **kwargs)
            print(f"   DEBUG: _process_sync_chat completed")
            return result
        overlord._process_sync_chat = debug_process
        
        try:
            response3 = await asyncio.wait_for(
                overlord.chat("What testing framework?", user_id=ctx.user_id, session_id=ctx.session_id, stream=False),
                timeout=10.0
            )
            content3 = response3.content if hasattr(response3, 'content') else str(response3)
            print(f"   ✓ Response received: {content3[:50]}...")
        except asyncio.TimeoutError:
            print("   ❌ TIMEOUT - Request hung for 10 seconds")
            
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if formation:
            print("\nShutting down...")
            await formation.kill_overlord()
            formation.shutdown()


if __name__ == "__main__":
    result = asyncio.run(run_test())
    sys.exit(0 if result else 1)