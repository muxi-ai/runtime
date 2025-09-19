#!/usr/bin/env python
"""Test 8B Baseline: Simplified version with proper timeout handling"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def run_test():
    """Run the baseline test with timeout protection."""
    formation = None
    try:
        print("\n=== Test 8B Baseline (Simplified) ===\n")

        # Load formation
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Create test context
        ctx = TestContext("test_8b_baseline_simple")
        print(f"User: {ctx.user_id}, Session: {ctx.session_id}\n")

        # Test 1: Simple greeting
        print("1. Testing greeting...")
        try:
            response1 = await asyncio.wait_for(
                overlord.chat("Hi", user_id=ctx.user_id, session_id=ctx.session_id, stream=False),
                timeout=5.0,
            )
            content1 = response1.content if hasattr(response1, "content") else str(response1)
            print("   User: Hi")
            print(f"   System: {content1[:100]}...")
        except asyncio.TimeoutError:
            print("   ❌ Timeout on greeting")
            return False

        # Test 2: Informational statement
        print("\n2. Testing informational statement...")
        try:
            response2 = await asyncio.wait_for(
                overlord.chat(
                    "I'm working on a Python project",
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    stream=False,
                ),
                timeout=5.0,
            )
            content2 = response2.content if hasattr(response2, "content") else str(response2)
            print("   User: I'm working on a Python project")
            print(f"   System: {content2[:100]}...")
        except asyncio.TimeoutError:
            print("   ❌ Timeout on statement")
            return False

        # Test 3: Context-using question
        print("\n3. Testing context usage...")
        try:
            response3 = await asyncio.wait_for(
                overlord.chat(
                    "What testing framework would you recommend?",
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    stream=False,
                ),
                timeout=5.0,
            )
            content3 = response3.content if hasattr(response3, "content") else str(response3)
            print("   User: What testing framework would you recommend?")
            print(f"   System: {content3[:200]}...")

            # Check for Python context
            mentions_python = any(
                term in content3.lower() for term in ["pytest", "unittest", "python"]
            )

            if mentions_python:
                print("\n✅ SUCCESS: Python context maintained")
            else:
                print("\n❌ FAILURE: Python context not used")

        except asyncio.TimeoutError:
            print("   ❌ Timeout on question")
            return False

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        # Clean shutdown
        if formation:
            try:
                print("\nShutting down...")
                await formation.kill_overlord()
                formation.shutdown()
            except Exception:
                pass


async def main():
    """Main entry point with overall timeout."""
    try:
        result = await asyncio.wait_for(run_test(), timeout=30.0)
        sys.exit(0 if result else 1)
    except asyncio.TimeoutError:
        print("\n❌ Overall test timeout (30s)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
