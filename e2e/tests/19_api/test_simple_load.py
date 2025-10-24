#!/usr/bin/env python3
"""Simple test - just load and exit immediately."""

import asyncio
import sys
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation

# Set up signal handler for timeout
def timeout_handler(signum, frame):
    print("\n⏰ TIMEOUT - Force exiting")
    sys.exit(124)

signal.signal(signal.SIGALRM, timeout_handler)

async def simple_test():
    """Just load formation."""
    print("Loading formation...")
    formation = Formation()
    formation_path = Path(__file__).parent / "formation-api"
    
    # Set 30s alarm
    signal.alarm(30)
    
    await formation.load(str(formation_path))
    print("✅ Load complete!")
    
    # Cancel alarm
    signal.alarm(0)
    
    # Don't call stop, just return
    print("Returning...")
    return True

if __name__ == "__main__":
    result = asyncio.run(simple_test())
    print(f"✅ Exited cleanly: {result}")
    sys.exit(0)
