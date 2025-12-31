#!/usr/bin/env python3
"""Test if calling formation.stop() fixes the hang."""

import asyncio
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation

# Timeout handler
def timeout_handler(signum, frame):
    print("\n❌ TIMEOUT - still hanging even with stop()")
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)

async def test_with_stop():
    """Load formation and explicitly call stop()."""
    print("1. Loading formation...")
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formation-api"))
    print("✅ Formation loaded\n")

    print("2. Calling formation.stop()...")
    formation.stop()  # Explicit cleanup
    print("✅ Stop() completed\n")

    print("3. Returning from async function...")
    return True

if __name__ == "__main__":
    signal.alarm(30)  # 30s timeout

    print("="*60)
    print("TEST: Explicit formation.stop() call")
    print("="*60)
    print()

    result = asyncio.run(test_with_stop())

    signal.alarm(0)  # Cancel alarm
    print("✅ Script exited cleanly!")
    print(f"   Result: {result}")
    sys.exit(0)
