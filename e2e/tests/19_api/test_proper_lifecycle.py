#!/usr/bin/env python3
"""Test proper formation lifecycle: load -> start_overlord -> stop_overlord."""

import asyncio
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation

def timeout_handler(signum, frame):
    print("\n❌ TIMEOUT")
    import os; os._exit(1)

signal.signal(signal.SIGALRM, timeout_handler)

async def test_proper_lifecycle():
    """Follow the same pattern as working tests."""
    try:
        print("1. Loading formation...")
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formation-api"))
        print("✅ Loaded\n")

        print("2. Starting overlord...")
        overlord = await formation.start_overlord()
        print(f"✅ Overlord started (formation_id: {overlord.formation_id})\n")

        print("3. Stopping overlord...")
        await formation.stop_overlord()
        print("✅ Overlord stopped\n")

        print("4. Returning from async function...")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    signal.alarm(30)

    print("="*60)
    print("TEST: Proper Formation Lifecycle")
    print("="*60)
    print()

    result = asyncio.run(test_proper_lifecycle())

    signal.alarm(0)
    print(f"\n✅ Script exited cleanly! Result: {result}")
    sys.exit(0 if result else 1)
