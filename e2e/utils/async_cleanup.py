"""
Async task cleanup utilities for e2e tests.

This module provides utilities to properly clean up asyncio tasks
in tests, preventing "Task was destroyed but it is pending!" warnings
that occur when tests exit before fire-and-forget tasks complete.
"""

import asyncio
from typing import Optional


async def cleanup_pending_tasks(timeout: float = 5.0, verbose: bool = False) -> int:
    """
    Clean up all pending asyncio tasks before test completion.

    This should be called at the end of async tests to ensure all
    fire-and-forget tasks (like buffer memory writes, observability
    events, etc.) complete before the event loop closes.

    Args:
        timeout: Maximum seconds to wait for tasks to complete.
                 After timeout, tasks are cancelled.
        verbose: If True, print information about pending tasks.

    Returns:
        Number of tasks that were cleaned up.

    Example:
        async def test_something():
            # ... test code that creates fire-and-forget tasks ...

            # Cleanup before test ends
            await cleanup_pending_tasks(verbose=True)
    """
    # Get all tasks except the current one
    current_task = asyncio.current_task()
    all_tasks = asyncio.all_tasks()
    pending = [t for t in all_tasks if t != current_task and not t.done()]

    if not pending:
        if verbose:
            print("   ℹ️  No pending tasks to clean up")
        return 0

    if verbose:
        print(f"   ℹ️  Waiting for {len(pending)} pending task(s) to complete...")
        # Print task names for debugging
        for task in pending:
            task_name = task.get_name()
            coro = task.get_coro()
            coro_name = getattr(coro, '__name__', str(coro))
            print(f"      - {task_name}: {coro_name}")

    try:
        # Wait for tasks with timeout
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=timeout
        )

        if verbose:
            print(f"   ✓ All {len(pending)} task(s) completed successfully")

        return len(pending)

    except asyncio.TimeoutError:
        # Timeout reached - cancel remaining tasks
        still_pending = [t for t in pending if not t.done()]

        if verbose:
            print(f"   ⚠️  Timeout after {timeout}s - cancelling {len(still_pending)} task(s)")

        for task in still_pending:
            task.cancel()

        # Wait briefly for cancellations to process
        await asyncio.gather(*still_pending, return_exceptions=True)

        return len(pending)

    except Exception as e:
        # Unexpected error during cleanup
        if verbose:
            print(f"   ⚠️  Error during task cleanup: {e}")

        # Try to cancel all pending tasks as fallback
        for task in pending:
            if not task.done():
                task.cancel()

        await asyncio.gather(*pending, return_exceptions=True)
        return len(pending)


async def wait_for_background_tasks(
    category: Optional[str] = None,
    timeout: float = 2.0,
    verbose: bool = False
) -> int:
    """
    Wait specifically for fire-and-forget background tasks to complete.

    This is a lighter version of cleanup_pending_tasks() that only waits
    a short time for tasks to finish naturally, without forcing cancellation.
    Useful when you want background tasks to complete but don't want to
    block for long.

    Args:
        category: Optional category name for logging (e.g., "memory writes")
        timeout: Maximum seconds to wait (default: 2.0)
        verbose: If True, print progress information

    Returns:
        Number of tasks that completed during the wait

    Example:
        async def test_multi_turn():
            # ... test creates buffer memory writes ...

            # Give background tasks time to complete
            await wait_for_background_tasks("buffer memory", timeout=1.0)
    """
    current_task = asyncio.current_task()
    all_tasks = asyncio.all_tasks()
    pending = [t for t in all_tasks if t != current_task and not t.done()]

    if not pending:
        return 0

    initial_count = len(pending)
    category_str = f" ({category})" if category else ""

    if verbose:
        print(f"   ℹ️  Waiting for {initial_count} background task(s){category_str}...")

    try:
        # Wait for tasks with timeout, but don't cancel if timeout
        done, still_pending = await asyncio.wait(
            pending,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED
        )

        completed_count = len(done)

        if verbose:
            if still_pending:
                print(f"   ⚠️  {completed_count}/{initial_count} task(s) completed, "
                      f"{len(still_pending)} still pending")
            else:
                print(f"   ✓ All {completed_count} background task(s) completed")

        return completed_count

    except Exception as e:
        if verbose:
            print(f"   ⚠️  Error waiting for background tasks: {e}")
        return 0


def print_task_summary(verbose: bool = True) -> None:
    """
    Print a summary of all asyncio tasks (for debugging).

    Useful for understanding what tasks are running during test execution.

    Args:
        verbose: If True, print detailed information about each task

    Example:
        # During test debugging
        print_task_summary(verbose=True)
    """
    if not verbose:
        return

    current_task = asyncio.current_task()
    all_tasks = asyncio.all_tasks()

    done_tasks = [t for t in all_tasks if t.done()]
    pending_tasks = [t for t in all_tasks if not t.done() and t != current_task]

    print("\n📊 Task Summary:")
    print(f"   Total tasks: {len(all_tasks)}")
    print(f"   Done: {len(done_tasks)}")
    print(f"   Pending: {len(pending_tasks)}")
    print("   Current: 1 (this task)")

    if pending_tasks:
        print("\n   Pending tasks:")
        for task in pending_tasks:
            task_name = task.get_name()
            coro = task.get_coro()
            coro_name = getattr(coro, '__name__', str(coro))
            print(f"      - {task_name}: {coro_name}")

    print()


# Convenience function for common test cleanup pattern
async def standard_test_cleanup(
    formation,
    wait_for_tasks: bool = True,
    timeout: float = 5.0,
    verbose: bool = False
) -> None:
    """
    Standard cleanup pattern for formation-based tests.

    This combines formation shutdown with task cleanup in the proper order.

    Args:
        formation: The Formation instance to clean up
        wait_for_tasks: If True, wait for background tasks before shutdown
        timeout: Timeout for task cleanup
        verbose: Print cleanup progress

    Example:
        async def test_something():
            formation = Formation()
            await formation.load("formation.yaml")
            overlord = await formation.start_overlord()

            try:
                # ... test code ...
            finally:
                await standard_test_cleanup(formation, verbose=True)
    """
    if verbose:
        print("\n6. Cleaning up...")

    # First, give background tasks a chance to complete
    if wait_for_tasks:
        await wait_for_background_tasks(
            category="memory/observability",
            timeout=min(2.0, timeout / 2),
            verbose=verbose
        )

    # Stop the overlord and formation
    try:
        await formation.stop_overlord()
        formation.stop()
        if verbose:
            print("   ✓ Formation stopped")
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Formation shutdown error: {e}")

    # Final cleanup of any remaining tasks
    if wait_for_tasks:
        remaining = await cleanup_pending_tasks(
            timeout=timeout,
            verbose=verbose
        )

        if verbose and remaining > 0:
            print(f"   ✓ Cleaned up {remaining} remaining task(s)")
