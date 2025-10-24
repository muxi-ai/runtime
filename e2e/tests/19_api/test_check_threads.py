#!/usr/bin/env python3
"""Check what threads are running after formation load."""

import asyncio
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation

async def test():
    print("Threads BEFORE load:")
    for t in threading.enumerate():
        print(f"  - {t.name} (daemon={t.daemon})")
    print()
    
    print("Loading formation...")
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formation-api"))
    print("✅ Loaded\n")
    
    print("Threads AFTER load:")
    for t in threading.enumerate():
        print(f"  - {t.name} (daemon={t.daemon})")
    print()
    
    # Check for non-daemon threads
    non_daemon = [t for t in threading.enumerate() if not t.daemon and t != threading.main_thread()]
    if non_daemon:
        print(f"❌ Found {len(non_daemon)} NON-DAEMON threads:")
        for t in non_daemon:
            print(f"   - {t.name}")
        print("\n   These will prevent process exit!")
        return False
    else:
        print("✅ All background threads are daemon threads")
        return True

if __name__ == "__main__":
    import signal
    signal.alarm(30)
    
    result = asyncio.run(test())
    signal.alarm(0)
    
    print(f"\nResult: {result}")
    print("Exiting...")
    sys.exit(0 if result else 1)
