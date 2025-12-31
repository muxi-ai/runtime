"""
Clean exit utility to suppress MCP async cleanup errors.
"""

import os
import sys
from typing import NoReturn


def clean_exit(code: int = 0) -> NoReturn:
    """
    Exit the process cleanly, suppressing MCP SDK async cleanup errors.

    This is a workaround for the MCP SDK's stdio_client async generator cleanup
    issue that occurs when the event loop is torn down at process exit.

    Args:
        code: Exit code (default: 0)
    """
    # Best-effort flush; ignore failures (e.g. streams already closed)
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.flush()
        except Exception:
            pass

    # Use os._exit to skip Python cleanup (including async generator cleanup)
    os._exit(code)
