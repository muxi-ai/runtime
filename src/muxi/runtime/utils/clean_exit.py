"""
Clean exit utility for MUXI applications using MCP.

This module provides a clean exit function that suppresses the known
MCP SDK async cleanup error that occurs during process exit.
"""

import os
import sys


def clean_exit(code: int = 0) -> None:
    """
    Exit the process cleanly, suppressing MCP SDK async cleanup errors.

    This function should be used instead of sys.exit() when your application
    uses MCP servers. It prevents the "Attempted to exit cancel scope in a
    different task than it was entered in" error that occurs due to a
    limitation in the MCP Python SDK.

    Args:
        code: Exit code (default: 0 for success)

    Example:
        from muxi.runtime.utils.clean_exit import clean_exit

        # Your application code here
        formation = Formation()
        formation.load("config.yaml")
        overlord = formation.start_overlord()

        # ... do work ...

        # Exit cleanly
        clean_exit(0)
    """
    # Flush all output streams
    sys.stdout.flush()
    sys.stderr.flush()

    # Use os._exit to bypass Python's cleanup, which triggers the MCP error
    os._exit(code)
