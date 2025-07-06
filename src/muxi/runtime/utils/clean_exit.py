"""
Clean exit utility to suppress MCP async cleanup errors.
"""

import os
import sys


def clean_exit(code: int = 0) -> None:
    """
    Exit the process cleanly, suppressing MCP SDK async cleanup errors.

    This is a workaround for the MCP SDK's stdio_client async generator cleanup
    issue that occurs when the event loop is torn down at process exit.

    Args:
        code: Exit code (default: 0)
    """
    # Flush output streams
    sys.stdout.flush()
    sys.stderr.flush()

    # Use os._exit to skip Python cleanup (including async generator cleanup)
    os._exit(code)
