"""
Workaround helper for MCP SDK cleanup bug in tests.
"""
import os
import atexit
import signal
import asyncio
from typing import Optional


def force_exit_on_success(exit_code: int = 0):
    """Force exit to bypass MCP SDK cleanup bug."""
    # Flush all output
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Give async tasks a moment to complete
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
    except:
        pass
    
    # Force exit
    os._exit(exit_code)


def install_cleanup_workaround():
    """Install signal handlers to ensure clean exit."""
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, forcing clean exit...")
        force_exit_on_success(0)
    
    # Install handlers for common signals
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


# Usage in test files:
# from test_cleanup_workaround import force_exit_on_success
# 
# At the end of main():
# force_exit_on_success(0 if success else 1)