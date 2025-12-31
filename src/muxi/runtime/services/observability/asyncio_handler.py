"""
Custom asyncio exception handler that avoids recursion.

Python's default asyncio exception handler uses the logging module,
which can cause RecursionError when called from background threads.
This custom handler writes directly to stderr instead.
"""

import sys
import traceback
from typing import Any, Dict
import asyncio


def safe_asyncio_exception_handler(
    loop: asyncio.AbstractEventLoop,
    context: Dict[str, Any]
) -> None:
    """
    Custom asyncio exception handler that avoids using logging.

    The default handler calls logger.error() which can recurse when
    called from background threads during event emission. This handler
    writes directly to stderr to prevent the recursion.

    Args:
        loop: The asyncio event loop instance
        context: Exception context dictionary containing:
                 - 'exception': The exception instance (if any)
                 - 'message': Human-readable error message
                 - Other contextual information

    Note:
        This handler is intentionally defensive and will never raise
        exceptions, even if the handler itself fails.
    """
    try:
        exception = context.get('exception')
        message = context.get('message', 'Unknown asyncio exception')

        # Write directly to stderr to avoid logging recursion
        sys.stderr.write(f"\n⚠️  Asyncio exception: {message}\n")

        if exception:
            sys.stderr.write(f"Exception type: {type(exception).__name__}\n")
            sys.stderr.write(f"Exception: {str(exception)[:200]}\n")

            # Print traceback if available
            if hasattr(exception, '__traceback__') and exception.__traceback__:
                sys.stderr.write("Traceback:\n")
                traceback.print_exception(exception, limit=10, file=sys.stderr)

        sys.stderr.flush()

    except Exception as e:
        # Last resort - if even this handler fails
        sys.stderr.write(f"\n🔥 Exception handler itself failed: {e}\n")
        sys.stderr.flush()
