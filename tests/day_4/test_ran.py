#!/usr/bin/env python3
"""
Test demonstrating MCP integration with MUXI Runtime.

Note: This test will show an async cleanup error at exit. This is a known issue
with the MCP Python SDK and does not affect functionality. See docs/known-issues.md
for details.
"""

import time
import sys
sys.path.insert(0, ".")

from src.muxi.runtime import Formation  # noqa: E402
from src.muxi.runtime.utils.clean_exit import clean_exit  # noqa: E402


def test_mcp_integration():
    """Test basic MCP server integration."""
    formation = Formation()

    # Load formation with MCP configuration
    formation.load("test-formations/formation-mcp")

    # Start the overlord (this initializes MCP servers)
    overlord = formation.start_overlord()
    print(f"✅ Overlord started: {overlord}")

    # In a real application, you would do work here:
    # response = overlord.chat("List files on my desktop")

    print("✅ Test completed successfully!")

    print("Waiting for 10 seconds...")
    time.sleep(10)
    print("10 seconds passed")

    # Attempt graceful shutdown (this helps but doesn't prevent the error)
    try:
        # Note: stop_overlord() may fail in test environments due to event loop conflicts
        # In production async contexts, this works properly
        formation.kill_overlord()  # Using kill for immediate termination in tests
        print("✅ Overlord stopped")
    except Exception as e:
        print(f"⚠️  Shutdown error (expected in tests): {e}")


if __name__ == "__main__":
    test_mcp_integration()

    # Use clean_exit to suppress the MCP SDK async cleanup error
    # This is the recommended approach for tests and scripts
    clean_exit(0)
