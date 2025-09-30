#!/usr/bin/env python3
"""Utility functions for memory tests to prevent hanging."""

import asyncio
import functools
from typing import Any, Optional, Callable, TypeVar, Coroutine
import sys

T = TypeVar('T')


async def with_timeout(coro: Coroutine[Any, Any, T], timeout: float, default: Optional[T] = None) -> T:
    """
    Execute an async coroutine with a timeout.

    Args:
        coro: The coroutine to execute
        timeout: Timeout in seconds
        default: Default value to return on timeout

    Returns:
        The result of the coroutine or default value on timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        print(f"  ⏱️ Operation timed out after {timeout}s")
        return default


def timeout_test(seconds: float = 30.0):
    """
    Decorator to add timeout to test methods.

    Args:
        seconds: Timeout in seconds (default 30)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                print(f"\n❌ Test timed out after {seconds} seconds")
                return False
        return wrapper
    return decorator


async def safe_formation_load(formation, config_path: str, timeout: float = 10.0) -> bool:
    """
    Safely load a formation with timeout and error handling.

    Args:
        formation: Formation instance
        config_path: Path to formation config
        timeout: Timeout in seconds

    Returns:
        True if loaded successfully, False otherwise
    """
    try:
        await asyncio.wait_for(formation.load(config_path), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        print(f"  ⏱️ Formation load timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"  ❌ Formation load failed: {e}")
        return False


async def safe_formation_shutdown(formation, timeout: float = 5.0) -> bool:
    """
    Safely shutdown a formation with timeout.

    Args:
        formation: Formation instance
        timeout: Timeout in seconds

    Returns:
        True if shutdown successfully, False otherwise
    """
    if not formation:
        return True

    try:
        if hasattr(formation, 'shutdown'):
            await asyncio.wait_for(formation.shutdown(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        print(f"  ⚠️ Formation shutdown timed out after {timeout}s")
        # Force cleanup
        if hasattr(formation, '_overlord'):
            formation._overlord = None
        return False
    except Exception as e:
        print(f"  ⚠️ Formation shutdown error: {e}")
        return False


async def safe_overlord_chat(overlord, message: str, user_id: str = "test", timeout: float = 10.0) -> Optional[str]:
    """
    Safely call overlord.chat with timeout.

    Args:
        overlord: Overlord instance
        message: Message to send
        user_id: User ID
        timeout: Timeout in seconds

    Returns:
        Response text or None on timeout/error
    """
    try:
        response = await asyncio.wait_for(
            overlord.chat(message, user_id=user_id, use_async=False),
            timeout=timeout
        )

        # Handle different response types
        if hasattr(response, "__aiter__"):
            # Async generator - collect with timeout
            result = ""
            async def collect():
                nonlocal result
                async for chunk in response:
                    result += chunk
            await asyncio.wait_for(collect(), timeout=5.0)
            return result
        elif hasattr(response, "content"):
            return response.content
        else:
            return str(response)

    except asyncio.TimeoutError:
        print(f"  ⏱️ Overlord chat timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"  ❌ Overlord chat error: {e}")
        return None


def run_with_timeout(timeout: float = 60.0):
    """
    Decorator to run entire test with a hard timeout.

    Args:
        timeout: Total test timeout in seconds
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            async def run():
                try:
                    return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                except asyncio.TimeoutError:
                    print(f"\n❌ ENTIRE TEST TIMED OUT after {timeout} seconds")
                    sys.exit(1)

            if asyncio.iscoroutinefunction(func):
                return asyncio.run(run())
            else:
                # For sync functions, just run with basic timeout
                import signal

                def timeout_handler(signum, frame):
                    print(f"\n❌ ENTIRE TEST TIMED OUT after {timeout} seconds")
                    sys.exit(1)

                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout))
                try:
                    result = func(*args, **kwargs)
                    signal.alarm(0)
                    return result
                except Exception:
                    signal.alarm(0)
                    raise

        return wrapper
    return decorator