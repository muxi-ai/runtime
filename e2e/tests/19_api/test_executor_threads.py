#!/usr/bin/env python3
"""Test if asyncio run_in_executor creates non-daemon threads."""

import asyncio
import threading

async def test():
    loop = asyncio.get_event_loop()
    # This creates a default ThreadPoolExecutor
    await loop.run_in_executor(None, lambda: None)

print("Before asyncio.run():")
print(f"  Threads: {[t.name for t in threading.enumerate()]}")

asyncio.run(test())

print("\nAfter asyncio.run():")
threads = [(t.name, t.daemon) for t in threading.enumerate()]
print(f"  Threads: {threads}")

non_daemon = [t for t in threading.enumerate() if not t.daemon and t != threading.main_thread()]
if non_daemon:
    print(f"\n❌ {len(non_daemon)} NON-DAEMON threads still running!")
    for t in non_daemon:
        print(f"   - {t.name}")
else:
    print("\n✅ All threads cleaned up")
