#!/usr/bin/env python3
"""
Minimal test to check if async Formation fixes MCP stdio error.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi import Formation  # noqa: E402


async def minimal_test():
    """Minimal test - just load and start."""
    print("Starting minimal async Formation test...")

    formation = Formation()

    # Load and start with async API
    await formation.load("test-formations/formation-mcp")
    print("✅ Formation loaded")

    overlord = await formation.start_overlord()
    print("✅ Overlord started")

    # The MCP stdio error usually appears right after start
    print("\nIf no async generator error appeared above, the fix worked!")

    # Quick cleanup
    await formation.stop_overlord()
    print("✅ Stopped")


if __name__ == "__main__":
    asyncio.run(minimal_test())
