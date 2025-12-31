"""
Health Status API for Observability Stream Destinations

This module provides HTTP API endpoints for monitoring and debugging
the health status of observability stream destinations.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .manager import HealthManager


class HealthStatusAPI:
    """
    HTTP API for health status monitoring and debugging.

    Provides endpoints for checking destination health, viewing status history,
    and debugging connectivity issues.
    """

    def __init__(self, health_manager: HealthManager):
        self.health_manager = health_manager

    async def get_health_summary(self) -> Dict[str, Any]:
        """
        Get overall health summary.

        Returns:
            Dictionary with overall health statistics
        """
        health_status = await self.health_manager.get_all_destinations_status()
        destinations = health_status.get("destinations", {})

        total_destinations = len(destinations)
        healthy_count = sum(1 for dest in destinations.values() if dest.get("healthy", True))
        unhealthy_count = total_destinations - healthy_count

        return {
            "status": "healthy" if unhealthy_count == 0 else "degraded",
            "last_checked": health_status.get("last_checked"),
            "summary": {
                "total_destinations": total_destinations,
                "healthy": healthy_count,
                "unhealthy": unhealthy_count,
                "health_percentage": (
                    round((healthy_count / total_destinations * 100), 2)
                    if total_destinations > 0
                    else 100
                ),
            },
            "destinations": destinations,
        }

    async def get_destination_health(self, destination: str) -> Dict[str, Any]:
        """
        Get health status for a specific destination.

        Args:
            destination: The destination URL/path

        Returns:
            Dictionary with detailed health information
        """
        dest_status = await self.health_manager.get_destination_status(destination)

        # Calculate uptime if unhealthy
        uptime_info = {}
        if not dest_status.get("healthy", True) and dest_status.get("since"):
            try:
                since_time = datetime.fromisoformat(dest_status["since"])
                downtime_duration = datetime.now() - since_time
                uptime_info = {
                    "downtime_seconds": int(downtime_duration.total_seconds()),
                    "downtime_human": self._format_duration(downtime_duration.total_seconds()),
                }
            except (ValueError, TypeError):
                pass

        return {
            "destination": destination,
            "healthy": dest_status.get("healthy", True),
            "last_error": dest_status.get("last_error"),
            "since": dest_status.get("since"),
            **uptime_info,
        }

    async def get_unhealthy_destinations(self) -> Dict[str, Any]:
        """
        Get list of all unhealthy destinations.

        Returns:
            Dictionary with unhealthy destinations and their errors
        """
        health_status = await self.health_manager.get_all_destinations_status()
        destinations = health_status.get("destinations", {})

        unhealthy = {}
        for dest, status in destinations.items():
            if not status.get("healthy", True):
                unhealthy[dest] = {
                    "last_error": status.get("last_error"),
                    "since": status.get("since"),
                    "downtime_seconds": self._calculate_downtime_seconds(status.get("since")),
                }

        return {
            "count": len(unhealthy),
            "destinations": unhealthy,
            "last_checked": health_status.get("last_checked"),
        }

    async def force_health_check(self, destination: Optional[str] = None) -> Dict[str, Any]:
        """
        Force an immediate health check for a destination or all destinations.

        Args:
            destination: Specific destination to check, or None for all

        Returns:
            Dictionary with check results
        """
        # This would trigger the health monitor to perform immediate checks
        # For now, return current status and update last_checked
        await self.health_manager.update_last_checked()

        if destination:
            result = await self.get_destination_health(destination)
            return {
                "action": "force_check",
                "destination": destination,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            summary = await self.get_health_summary()
            return {
                "action": "force_check_all",
                "result": summary,
                "timestamp": datetime.now().isoformat(),
            }

    async def reset_destination_health(self, destination: str) -> Dict[str, Any]:
        """
        Reset a destination's health status to healthy (manual override).

        Args:
            destination: The destination URL/path to reset

        Returns:
            Dictionary with reset confirmation
        """
        await self.health_manager.update_destination_health(
            destination, True, None, preserve_since=False
        )

        return {
            "action": "reset_health",
            "destination": destination,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
        }

    async def get_health_metrics(self) -> Dict[str, Any]:
        """
        Get health metrics for monitoring systems.

        Returns:
            Dictionary with metrics in Prometheus-like format
        """
        health_status = await self.health_manager.get_all_destinations_status()
        destinations = health_status.get("destinations", {})

        metrics = {
            "muxi_observability_destinations_total": len(destinations),
            "muxi_observability_destinations_healthy": sum(
                1 for dest in destinations.values() if dest.get("healthy", True)
            ),
            "muxi_observability_destinations_unhealthy": sum(
                1 for dest in destinations.values() if not dest.get("healthy", True)
            ),
            "muxi_observability_last_check_timestamp": self._iso_to_timestamp(
                health_status.get("last_checked")
            ),
        }

        # Per-destination metrics
        for dest, status in destinations.items():
            metrics[f'muxi_observability_destination_healthy{{destination="{dest}"}}'] = (
                1 if status.get("healthy", True) else 0
            )

            if not status.get("healthy", True) and status.get("since"):
                downtime_seconds = self._calculate_downtime_seconds(status.get("since"))
                metrics[
                    f'muxi_observability_destination_downtime_seconds{{destination="{dest}"}}'
                ] = downtime_seconds

        return {"metrics": metrics, "timestamp": datetime.now().isoformat()}

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}d {hours}h"

    def _calculate_downtime_seconds(self, since_str: Optional[str]) -> int:
        """Calculate downtime in seconds from 'since' timestamp."""
        if not since_str:
            return 0

        try:
            since_time = datetime.fromisoformat(since_str)
            downtime = datetime.now() - since_time
            return int(downtime.total_seconds())
        except (ValueError, TypeError):
            return 0

    def _iso_to_timestamp(self, iso_str: Optional[str]) -> float:
        """Convert ISO timestamp to Unix timestamp."""
        if not iso_str:
            return 0.0

        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.timestamp()
        except (ValueError, TypeError):
            return 0.0


# HTTP endpoint handlers (for integration with web framework)
class HealthEndpoints:
    """
    HTTP endpoint handlers for health status API.

    These can be integrated with FastAPI, Flask, or other web frameworks.
    """

    def __init__(self, health_api: HealthStatusAPI):
        self.health_api = health_api

    async def health_summary_handler(self) -> Dict[str, Any]:
        """GET /health - Overall health summary."""
        return await self.health_api.get_health_summary()

    async def destination_health_handler(self, destination: str) -> Dict[str, Any]:
        """GET /health/destination/{destination} - Specific destination health."""
        return await self.health_api.get_destination_health(destination)

    async def unhealthy_destinations_handler(self) -> Dict[str, Any]:
        """GET /health/unhealthy - List of unhealthy destinations."""
        return await self.health_api.get_unhealthy_destinations()

    async def force_check_handler(self, destination: Optional[str] = None) -> Dict[str, Any]:
        """POST /health/check - Force health check."""
        return await self.health_api.force_health_check(destination)

    async def reset_health_handler(self, destination: str) -> Dict[str, Any]:
        """POST /health/reset/{destination} - Reset destination health."""
        return await self.health_api.reset_destination_health(destination)

    async def metrics_handler(self) -> Dict[str, Any]:
        """GET /health/metrics - Health metrics for monitoring."""
        return await self.health_api.get_health_metrics()

    async def health_file_handler(self) -> Dict[str, Any]:
        """GET /health/file - Raw health file contents."""
        return await self.health_api.health_manager.get_all_destinations_status()
