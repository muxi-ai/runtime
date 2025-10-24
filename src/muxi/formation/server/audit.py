"""
Audit logging system for Formation API.

This module provides audit logging for all formation-modifying operations,
tracking changes to agents, secrets, MCP servers, scheduler jobs, logging
destinations, async configuration, and memory operations.
"""

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Request

from ...utils.user_dirs import get_user_dir


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

        # Determine audit log path: ~/.muxi/formations/{formation_id}/audit.log
        base_dir = get_user_dir()
        self.formation_dir = base_dir / "formations" / formation_id
        self.formation_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.formation_dir / "audit.log"

        # Create empty log file if it doesn't exist
        if not self.log_path.exists():
            self.log_path.touch()

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

        # Thread-safe append to log file
        with self._lock:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

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

        # TODO: Extract user from authentication context when multi-user is implemented
        user = "admin"

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

    def get_entries(
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

        entries = []

        # Read all entries from log file (thread-safe)
        with self._lock:
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

        # Apply filters
        filtered = entries

        if action:
            filtered = [e for e in filtered if e.get("action") == action]

        if resource_type:
            filtered = [e for e in filtered if e.get("resource_type") == resource_type]

        if since:
            since_iso = since.isoformat() + "Z" if not since.tzinfo else since.isoformat()
            filtered = [e for e in filtered if e.get("timestamp", "") >= since_iso]

        # Return most recent first
        filtered.reverse()

        # Apply limit
        return filtered[:limit]

    def clear(self, user: str = "admin", request_id: Optional[str] = None) -> int:
        """
        Clear the audit log, leaving only a "cleared" entry.

        Args:
            user: User who cleared the log
            request_id: Request ID for tracing

        Returns:
            Number of entries that were cleared
        """
        # Acquire lock once for entire operation to prevent race conditions
        # (another thread could append between counting and writing)
        with self._lock:
            # Count entries before clearing
            count = 0
            if self.log_path.exists():
                with open(self.log_path, "r") as f:
                    count = sum(1 for line in f if line.strip())

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

            # Write the cleared entry (atomically with counting)
            with open(self.log_path, "w") as f:
                f.write(json.dumps(entry) + "\n")

        return count

    def get_total_entries(self) -> int:
        """
        Get total number of entries in the audit log.

        Returns:
            Total entry count
        """
        if not self.log_path.exists():
            return 0

        with self._lock:
            with open(self.log_path, "r") as f:
                return sum(1 for line in f if line.strip())
