"""
Health Manager for Observability Stream Destinations

This module provides centralized health status management using a shared
.status file with atomic operations and proper locking.
"""

import json
import asyncio
import aiofiles
import aiofiles.os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from ....utils.user_dirs import get_observability_dir


class HealthManager:
    """
    Manages health status for observability stream destinations.

    Uses a centralized .status file with atomic operations to track
    the health status of all configured destinations.
    """

    def __init__(self, health_file_path: Optional[str] = None):
        if health_file_path:
            self.health_file = Path(health_file_path)
        else:
            # Default location in health directory
            self.health_file = f"{get_observability_dir()}/health.json"

        self._lock = asyncio.Lock()

    async def load_health_status(self) -> Dict[str, Any]:
        """Load health status from file with file locking."""
        async with self._lock:
            try:
                if not self.health_file.exists():
                    # Create default status file
                    default_status = {
                        "last_checked": datetime.now().isoformat(),
                        "destinations": {},
                    }
                    await self._write_health_file(default_status)
                    return default_status

                async with aiofiles.open(self.health_file, "r") as f:
                    content = await f.read()
                    return json.loads(content)

            except Exception as e:
                print(f"Error loading health status: {e}")
                # Return default on error
                return {"last_checked": datetime.now().isoformat(), "destinations": {}}

    async def update_destination_health(
        self,
        destination: str,
        healthy: bool,
        last_error: Optional[str] = None,
        preserve_since: bool = False,
    ) -> None:
        """
        Update health status for a specific destination.

        Args:
            destination: The destination URL/path
            healthy: Whether the destination is healthy
            last_error: Error message if unhealthy
            preserve_since: Whether to preserve existing "since" timestamp
        """
        async with self._lock:
            health_status = await self.load_health_status()

            current_dest = health_status["destinations"].get(destination, {})
            was_healthy = current_dest.get("healthy", True)

            # Prepare new status
            new_status = {"healthy": healthy, "last_error": last_error}

            # Handle "since" timestamp logic
            if not healthy and was_healthy and not preserve_since:
                # Transition from healthy -> unhealthy
                new_status["since"] = datetime.now().isoformat()
            elif not healthy and not was_healthy and preserve_since:
                # Keep existing "since" timestamp
                new_status["since"] = current_dest.get("since")
            elif healthy and not was_healthy:
                # Transition from unhealthy -> healthy (remove since)
                pass  # Don't include "since" field

            health_status["destinations"][destination] = new_status
            await self._write_health_file(health_status)

    async def update_last_checked(self) -> None:
        """Update the global last_checked timestamp."""
        async with self._lock:
            health_status = await self.load_health_status()
            health_status["last_checked"] = datetime.now().isoformat()
            await self._write_health_file(health_status)

    async def is_destination_healthy(self, destination: str) -> bool:
        """
        Check if a destination is marked as healthy.

        Args:
            destination: The destination URL/path

        Returns:
            True if healthy, False if unhealthy. Defaults to True for new destinations.
        """
        health_status = await self.load_health_status()
        dest_status = health_status["destinations"].get(destination, {})
        return dest_status.get("healthy", True)  # Default to healthy if not found

    async def get_healthy_destinations(self, all_destinations: list) -> list:
        """
        Filter destinations to only healthy ones.

        Args:
            all_destinations: List of all destination URLs/paths

        Returns:
            List of only healthy destinations
        """
        health_status = await self.load_health_status()
        healthy_destinations = []

        for destination in all_destinations:
            dest_status = health_status["destinations"].get(destination, {})
            if dest_status.get("healthy", True):  # Default to healthy
                healthy_destinations.append(destination)

        return healthy_destinations

    async def get_destination_status(self, destination: str) -> Dict[str, Any]:
        """
        Get detailed status for a specific destination.

        Args:
            destination: The destination URL/path

        Returns:
            Dictionary with health status details
        """
        health_status = await self.load_health_status()
        return health_status["destinations"].get(destination, {"healthy": True, "last_error": None})

    async def get_all_destinations_status(self) -> Dict[str, Any]:
        """
        Get status for all destinations.

        Returns:
            Complete health status dictionary
        """
        return await self.load_health_status()

    async def _write_health_file(self, health_status: Dict[str, Any]) -> None:
        """
        Write health status to file atomically.

        Uses temporary file + rename for atomic operation to prevent corruption.
        """
        # Write to temporary file first, then rename (atomic operation)
        temp_file = self.health_file.with_suffix(".tmp")

        try:
            async with aiofiles.open(temp_file, "w") as f:
                await f.write(json.dumps(health_status, indent=2))

            # Atomic rename
            await aiofiles.os.rename(temp_file, self.health_file)

        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                try:
                    await aiofiles.os.remove(temp_file)
                except OSError:
                    pass  # Ignore cleanup errors
            raise e
