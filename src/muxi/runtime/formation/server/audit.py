"""
Audit logging system for Formation API.

This module provides audit logging for all formation-modifying operations,
tracking changes to agents, secrets, MCP servers, scheduler jobs, logging
destinations, async configuration, and memory operations.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import Request

from ...utils.user_dirs import get_user_dir

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit logger for tracking formation changes.

    Writes audit entries in JSONL format with human-readable messages.
    Thread-safe for concurrent writes.
    """

    def __init__(self, formation_id: str):
        """
        Initialize audit logger for a formation.

        Args:
            formation_id: Formation identifier
        """
        self.formation_id = formation_id
        self._lock = threading.Lock()
        self._total_entries = 0  # Cached counter for O(1) total_entries lookup
        self._pending_tasks: Set[asyncio.Task] = set()  # Track background write tasks

        # Determine audit log path: ~/.muxi/formations/{formation_id}/audit.log
        base_dir = get_user_dir()
        self.formation_dir = base_dir / "formations" / formation_id
        self.formation_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.formation_dir / "audit.log"

        # Create empty log file if it doesn't exist and initialize counter
        if not self.log_path.exists():
            self.log_path.touch()
        else:
            # Initialize counter by counting existing entries
            with open(self.log_path, "r") as f:
                self._total_entries = sum(1 for line in f if line.strip())

    def log(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        message: str,
        request_id: Optional[str] = None,
        user: str = "admin",
        ip: Optional[str] = None,
        result: str = "success",
        status_code: int = 200,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an audit entry.

        Args:
            action: Action performed (e.g., "agent.created", "secret.deleted")
            resource_type: Type of resource (agent, secret, mcp_server, etc.)
            resource_id: Identifier of the resource
            message: Human-readable message describing the action
            request_id: Request ID for tracing
            user: User who performed the action
            ip: IP address of the requester
            result: Result of the action (success, error)
            status_code: HTTP status code
            additional_data: Additional context data
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user": user,
            "ip": ip,
            "result": result,
            "status_code": status_code,
            "message": message,
        }

        if additional_data:
            entry["data"] = additional_data

        # Serialize entry once before I/O
        entry_json = json.dumps(entry) + "\n"

        # Perform file I/O off the event loop to avoid blocking
        def write_entry():
            with open(self.log_path, "a") as f:
                f.write(entry_json)

        # Run file write in thread pool and track the task
        task = asyncio.create_task(asyncio.to_thread(write_entry))
        self._pending_tasks.add(task)
        task.add_done_callback(self._task_done_callback)

        # Update in-memory counter (brief lock)
        with self._lock:
            self._total_entries += 1

    def log_from_request(
        self,
        request: Request,
        action: str,
        resource_type: str,
        resource_id: str,
        message: str,
        result: str = "success",
        status_code: int = 200,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an audit entry from a FastAPI request.

        Automatically extracts request_id, IP address, and user info.

        Args:
            request: FastAPI request object
            action: Action performed
            resource_type: Type of resource
            resource_id: Identifier of the resource
            message: Human-readable message
            result: Result of the action
            status_code: HTTP status code
            additional_data: Additional context data
        """
        request_id = getattr(request.state, "request_id", None)
        ip = request.client.host if request.client else None

        # Extract user from authentication context
        # Currently all admin API requests use "admin" user
        # When multi-admin support is added, extract from JWT/API key metadata
        user = getattr(request.state, "authenticated_user", "admin")

        self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            message=message,
            request_id=request_id,
            user=user,
            ip=ip,
            result=result,
            status_code=status_code,
            additional_data=additional_data,
        )

    async def get_entries(
        self,
        limit: int = 100,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit log entries with optional filtering.

        Args:
            limit: Maximum number of entries to return (most recent first)
            action: Filter by action type
            resource_type: Filter by resource type
            since: Return entries since this timestamp

        Returns:
            List of audit entries (most recent first)
        """
        if not self.log_path.exists():
            return []

        # Read entries off event loop with chunked processing
        def read_entries():
            entries = []
            with open(self.log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip malformed entries
                        continue
            return entries

        # Perform file read in thread pool (no lock needed for reads)
        entries = await asyncio.to_thread(read_entries)

        # Apply filters
        filtered = entries

        if action:
            filtered = [e for e in filtered if e.get("action") == action]

        if resource_type:
            filtered = [e for e in filtered if e.get("resource_type") == resource_type]

        if since:
            # Normalize since to UTC datetime
            if since.tzinfo is None:
                # Naive datetime - assume UTC
                since_utc = since.replace(tzinfo=timezone.utc)
            else:
                # Aware datetime - convert to UTC
                since_utc = since.astimezone(timezone.utc)
            
            # Filter using datetime comparison instead of string comparison
            def should_include(entry: Dict[str, Any]) -> bool:
                timestamp_str = entry.get("timestamp", "")
                if not timestamp_str:
                    return False
                
                try:
                    # Parse timestamp (handles multiple ISO formats)
                    # Remove trailing 'Z' and parse, then set UTC
                    ts = timestamp_str.rstrip("Z")
                    if "+" in ts or ts.count("-") > 2:
                        # Has timezone info - let fromisoformat handle it
                        event_dt = datetime.fromisoformat(ts)
                        if event_dt.tzinfo is None:
                            event_dt = event_dt.replace(tzinfo=timezone.utc)
                        else:
                            event_dt = event_dt.astimezone(timezone.utc)
                    else:
                        # No timezone info - assume UTC
                        event_dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
                    
                    return event_dt >= since_utc
                except (ValueError, AttributeError):
                    # Malformed timestamp - exclude entry
                    return False
            
            filtered = [e for e in filtered if should_include(e)]

        # Return most recent first
        filtered.reverse()

        # Apply limit
        return filtered[:limit]

    async def clear(self, user: str = "admin", request_id: Optional[str] = None) -> int:
        """
        Clear the audit log, leaving only a "cleared" entry.

        Args:
            user: User who cleared the log
            request_id: Request ID for tracing

        Returns:
            Number of entries that were cleared
        """
        # Get count from in-memory cache (O(1))
        with self._lock:
            count = self._total_entries

        # Create new log with only the "cleared" entry
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "action": "audit.cleared",
            "resource_type": "audit_log",
            "resource_id": self.formation_id,
            "user": user,
            "ip": None,
            "result": "success",
            "status_code": 200,
            "message": f"Audit log cleared by {user} ({count} entries removed)",
            "data": {"previous_entries_count": count},
        }

        entry_json = json.dumps(entry) + "\n"

        # Perform file write off event loop
        def write_cleared():
            with open(self.log_path, "w") as f:
                f.write(entry_json)

        await asyncio.to_thread(write_cleared)

        # Update in-memory counter (brief lock)
        with self._lock:
            self._total_entries = 1  # Only the cleared entry remains

        return count

    def _task_done_callback(self, task: asyncio.Task) -> None:
        """
        Callback for completed background write tasks.

        Logs any exceptions and removes task from tracking set.

        Args:
            task: The completed task
        """
        # Remove task from tracking set
        self._pending_tasks.discard(task)

        # Check for exceptions
        try:
            task.result()  # This will raise if the task failed
        except Exception as e:
            logger.error(
                "Audit log write failed for formation %s: %s",
                self.formation_id,
                e,
                exc_info=True
            )

    async def shutdown(self) -> None:
        """
        Wait for all pending audit log writes to complete.

        Should be called during application shutdown to ensure
        all log entries are written to disk.
        """
        if self._pending_tasks:
            logger.info(
                "Waiting for %d pending audit log writes to complete...",
                len(self._pending_tasks)
            )
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            logger.info("All pending audit log writes completed")

    def get_total_entries(self) -> int:
        """
        Get total number of entries in the audit log.

        Returns:
            Total entry count (O(1) via cached counter)
        """
        with self._lock:
            return self._total_entries
