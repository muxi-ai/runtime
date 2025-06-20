"""MCP Logging client implementation."""

from typing import Dict, Any, List
from ..transports.base import BaseTransport
from .message_handler import MCPMessageHandler


class MCPLoggingClient:
    """MCP Logging client using logging protocol."""

    def __init__(self):
        """Initialize logging client."""
        self.message_handler = MCPMessageHandler()
        self.log_history: List[Dict[str, Any]] = []

    async def set_logging_level(
        self,
        transport: BaseTransport,
        level: str
    ) -> Dict[str, Any]:
        """Set logging level for MCP server.

        Args:
            transport: MCP transport to use for communication
            level: Logging level (debug, info, notice, warning, error, critical, alert, emergency)

        Returns:
            Set level response

        Raises:
            MCPRequestError: If set level fails
        """
        try:
            # Validate level
            valid_levels = [
                "debug", "info", "notice", "warning",
                "error", "critical", "alert", "emergency"
            ]

            if level.lower() not in valid_levels:
                raise ValueError(f"Invalid logging level: {level}. Must be one of: {', '.join(valid_levels)}")

            # Create logging/setLevel request
            request = self.message_handler.create_request("logging/setLevel", {
                "level": level.lower()
            })

            # Send request and get response
            response = await transport.send_message(request)

            # Validate response
            self.message_handler.validate_response(response)

            # Extract result
            result = response.get("result", {})

            return {
                "success": True,
                "level": level.lower(),
                "result": result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "level": level.lower()
            }

    def collect_logs(
        self,
        logs: List[Dict[str, Any]]
    ) -> None:
        """Collect logs from MCP server notifications.

        Args:
            logs: List of log entries to collect
        """
        for log_entry in logs:
            self._validate_log_entry(log_entry)
            self.log_history.append(log_entry)

        # Keep only last 1000 log entries
        if len(self.log_history) > 1000:
            self.log_history = self.log_history[-1000:]

    def _validate_log_entry(self, log_entry: Dict[str, Any]) -> None:
        """Validate log entry structure.

        Args:
            log_entry: Log entry to validate
        """
        required_fields = ["level", "data"]

        for field in required_fields:
            if field not in log_entry:
                # Add missing fields with defaults
                if field == "level":
                    log_entry["level"] = "info"
                elif field == "data":
                    log_entry["data"] = ""

        # Ensure level is valid
        valid_levels = [
            "debug", "info", "notice", "warning",
            "error", "critical", "alert", "emergency"
        ]

        if log_entry["level"] not in valid_levels:
            log_entry["level"] = "info"

        # Add timestamp if missing
        if "timestamp" not in log_entry:
            import time
            log_entry["timestamp"] = time.time()

    def get_logs(
        self,
        level_filter: str = None,
        limit: int = 100,
        since_timestamp: float = None
    ) -> List[Dict[str, Any]]:
        """Get collected logs with optional filtering.

        Args:
            level_filter: Filter by log level
            limit: Maximum number of logs to return
            since_timestamp: Only return logs after this timestamp

        Returns:
            Filtered list of log entries
        """
        logs = self.log_history

        # Filter by level
        if level_filter:
            logs = [log for log in logs if log.get("level") == level_filter.lower()]

        # Filter by timestamp
        if since_timestamp:
            logs = [log for log in logs if log.get("timestamp", 0) >= since_timestamp]

        # Sort by timestamp (most recent first)
        logs = sorted(logs, key=lambda x: x.get("timestamp", 0), reverse=True)

        # Apply limit
        return logs[:limit]

    def get_log_summary(self) -> Dict[str, Any]:
        """Get summary of collected logs.

        Returns:
            Log summary with counts and statistics
        """
        if not self.log_history:
            return {
                "total_logs": 0,
                "by_level": {},
                "latest_timestamp": None,
                "oldest_timestamp": None
            }

        # Count by level
        level_counts = {}
        timestamps = []

        for log in self.log_history:
            level = log.get("level", "unknown")
            level_counts[level] = level_counts.get(level, 0) + 1

            timestamp = log.get("timestamp")
            if timestamp:
                timestamps.append(timestamp)

        return {
            "total_logs": len(self.log_history),
            "by_level": level_counts,
            "latest_timestamp": max(timestamps) if timestamps else None,
            "oldest_timestamp": min(timestamps) if timestamps else None
        }

    def format_log_entry(self, log_entry: Dict[str, Any]) -> str:
        """Format a log entry for human readability.

        Args:
            log_entry: Log entry to format

        Returns:
            Formatted log string
        """
        level = log_entry.get("level", "info").upper()
        data = log_entry.get("data", "")
        timestamp = log_entry.get("timestamp")

        # Format timestamp
        if timestamp:
            import time
            time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
        else:
            time_str = "??:??:??"

        # Level emoji
        level_emoji = {
            "DEBUG": "🐛",
            "INFO": "ℹ️",
            "NOTICE": "📢",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨",
            "ALERT": "🔥",
            "EMERGENCY": "💥"
        }.get(level, "📝")

        return f"{time_str} {level_emoji} [{level}] {data}"

    def format_logs(
        self,
        logs: List[Dict[str, Any]],
        max_entries: int = 50
    ) -> str:
        """Format multiple log entries for display.

        Args:
            logs: List of log entries
            max_entries: Maximum number of entries to format

        Returns:
            Formatted logs string
        """
        if not logs:
            return "No logs available"

        # Limit entries
        display_logs = logs[:max_entries]

        lines = [f"📋 Log Entries ({len(display_logs)} shown, {len(logs)} total):"]

        for log in display_logs:
            formatted_entry = self.format_log_entry(log)
            lines.append(f"  {formatted_entry}")

        if len(logs) > max_entries:
            lines.append(f"  ... ({len(logs) - max_entries} more entries)")

        return "\n".join(lines)

    def export_logs(
        self,
        format_type: str = "json",
        level_filter: str = None,
        since_timestamp: float = None
    ) -> str:
        """Export logs in specified format.

        Args:
            format_type: Export format ("json", "csv", "text")
            level_filter: Filter by log level
            since_timestamp: Only export logs after this timestamp

        Returns:
            Exported logs as string
        """
        logs = self.get_logs(
            level_filter=level_filter,
            since_timestamp=since_timestamp,
            limit=None  # Get all matching logs
        )

        if format_type == "json":
            import json
            return json.dumps(logs, indent=2)

        elif format_type == "csv":
            import csv
            import io

            output = io.StringIO()
            if logs:
                writer = csv.DictWriter(output, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)

            return output.getvalue()

        elif format_type == "text":
            return self.format_logs(logs, max_entries=len(logs))

        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    def clear_logs(self, before_timestamp: float = None) -> int:
        """Clear collected logs.

        Args:
            before_timestamp: Only clear logs before this timestamp (None for all)

        Returns:
            Number of logs cleared
        """
        if before_timestamp is None:
            # Clear all logs
            cleared_count = len(self.log_history)
            self.log_history.clear()
            return cleared_count
        else:
            # Clear logs before timestamp
            original_count = len(self.log_history)
            self.log_history = [
                log for log in self.log_history
                if log.get("timestamp", 0) >= before_timestamp
            ]
            return original_count - len(self.log_history)

    def handle_log_notification(self, notification: Dict[str, Any]) -> None:
        """Handle incoming log notification from MCP server.

        Args:
            notification: Log notification message
        """
        # Extract log data from notification
        params = notification.get("params", {})

        if "level" in params and "data" in params:
            # Single log entry
            self.collect_logs([params])
        elif "logs" in params:
            # Multiple log entries
            self.collect_logs(params["logs"])

    def get_logging_configuration(self) -> Dict[str, Any]:
        """Get current logging configuration.

        Returns:
            Logging configuration details
        """
        summary = self.get_log_summary()

        return {
            "log_collection_enabled": True,
            "max_log_entries": 1000,
            "current_log_count": summary["total_logs"],
            "log_levels_seen": list(summary["by_level"].keys()),
            "oldest_log": summary["oldest_timestamp"],
            "newest_log": summary["latest_timestamp"]
        }
