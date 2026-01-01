#!/usr/bin/env python3
"""Test with no LLM cache."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation

async def test():
    print("Loading formation with caching disabled...")
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formation-nocache"))
    print("✅ Loaded!")

    # Try to exit immediately
    print("Exiting...")
    return True

if __name__ == "__main__":
    # Set a hard timeout
    import signal
    signal.alarm(20)

    result = asyncio.run(test())
    signal.alarm(0)
    print(f"✅ Result: {result}")
    sys.exit(0)
