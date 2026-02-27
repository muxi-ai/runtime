"""Shared test utilities for memory e2e tests."""

import asyncio
import functools
import os


def timeout_test(seconds: float):
    """Decorator that wraps an async test method with a timeout."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                print(f"    TIMEOUT: {func.__name__} exceeded {seconds}s")
                return False, {"error": f"Timeout after {seconds}s"}
        return wrapper
    return decorator


def with_timeout(seconds: float):
    """Alias for timeout_test."""
    return timeout_test(seconds)


async def safe_overlord_chat(overlord, message: str, user_id: str = "test_user", timeout: float = 30.0, **kwargs):
    """Chat with overlord, catching common errors."""
    try:
        coro = overlord.chat(message, user_id=user_id, **kwargs)
        response = await asyncio.wait_for(coro, timeout=timeout)
        content = response.content if hasattr(response, "content") else str(response)
        return content
    except asyncio.TimeoutError:
        print(f"    Chat timeout after {timeout}s")
        return f"ERROR: timeout after {timeout}s"
    except Exception as e:
        print(f"    Chat error: {e}")
        return f"ERROR: {e}"


async def safe_formation_load(formation_or_path, formation_path: str = None, timeout: float = 30.0):
    """Load a formation safely with error handling.

    Can be called as:
        safe_formation_load("path/to/formation")
        safe_formation_load(formation_obj, "path/to/formation", timeout=10.0)
    """
    try:
        if isinstance(formation_or_path, str) and formation_path is None:
            from muxi.runtime.formation.formation import Formation
            formation = Formation(formation_or_path)
            await asyncio.wait_for(formation.start(), timeout=timeout)
            return formation
        else:
            formation = formation_or_path
            await asyncio.wait_for(formation.load(formation_path), timeout=timeout)
            return formation
    except asyncio.TimeoutError:
        print(f"    Formation load timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"    Formation load error: {e}")
        return None


async def safe_formation_shutdown(formation, timeout: float = 15.0):
    """Shut down a formation safely, handling hangs and background tasks."""
    if not formation:
        return
    try:
        if hasattr(formation, "stop_overlord"):
            try:
                await asyncio.wait_for(formation.stop_overlord(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        if hasattr(formation, "_observability_manager") and formation._observability_manager:
            try:
                await formation._observability_manager.stop()
            except Exception:
                pass
        try:
            formation.stop()
        except Exception:
            pass
    except Exception:
        pass
