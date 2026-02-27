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


async def safe_overlord_chat(overlord, message: str, user_id: str = "test_user", **kwargs):
    """Chat with overlord, catching common errors."""
    try:
        response = await overlord.chat(message, user_id=user_id, **kwargs)
        content = response.content if hasattr(response, "content") else str(response)
        return content
    except Exception as e:
        print(f"    Chat error: {e}")
        return f"ERROR: {e}"


async def safe_formation_load(formation_path: str):
    """Load a formation safely with error handling."""
    try:
        from muxi.runtime.formation.formation import Formation

        formation = Formation(formation_path)
        await formation.start()
        return formation
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
