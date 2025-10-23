"""
Audit log endpoints.

These endpoints provide access to the formation audit trail,
requiring admin API key authentication.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse

from ...audit import AuditLogger
from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["Audit"])


@router.get("/audit", response_model=APIResponse)
async def get_audit_log(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of entries to return"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(
        None,
        description="Filter by resource type",
        regex="^(agent|secret|mcp_server|scheduler_job|logging_destination|async|memory)$",
    ),
    since: Optional[str] = Query(None, description="Return entries since this ISO 8601 timestamp"),
) -> JSONResponse:
    """
    Get audit log entries with optional filtering.

    Returns audit trail of all formation-modifying operations.
    Results are returned in reverse chronological order (most recent first).

    **Log Location:** `~/.muxi/formations/{formation_id}/audit.log`

    **Format:** JSONL (one JSON object per line) with human-readable message field

    **Tracked Operations:**
    - Agent create/update/delete
    - Secret create/delete
    - MCP server create/update/delete
    - Scheduler job create/delete and config changes
    - Logging destination create/update/delete and config changes
    - Async config changes (webhook URL, etc.)
    - Memory delete operations (admin)

    Args:
        limit: Maximum number of entries to return (default: 100, max: 1000)
        action: Filter by action type (e.g., "agent.created", "secret.deleted")
        resource_type: Filter by resource type
        since: Return entries since this ISO 8601 timestamp

    Returns:
        Audit log entries with metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Initialize audit logger
    audit_logger = AuditLogger(formation.formation_id)

    # Parse since parameter
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=create_error_response(
                    error_code="INVALID_REQUEST",
                    message=f"Invalid ISO 8601 timestamp: {since}",
                    request_id=request_id,
                ).model_dump(),
            )

    # Get entries
    entries = audit_logger.get_entries(
        limit=limit,
        action=action,
        resource_type=resource_type,
        since=since_dt,
    )

    # Get total count
    total_entries = audit_logger.get_total_entries()

    response_data = {
        "entries": entries,
        "count": len(entries),
        "total_entries": total_entries,
    }

    response = create_success_response(
        APIObjectType.AUDIT_LOG,
        APIEventType.AUDIT_RETRIEVED,
        response_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/audit", response_model=APIResponse)
async def clear_audit_log(
    request: Request,
    confirm: str = Query(..., description="Required confirmation string to prevent accidental deletion"),
) -> JSONResponse:
    """
    Clear the audit log file.

    **Use with caution!** This action is irreversible.

    **This action itself is audited** - creates a final entry documenting
    who cleared the log and when, then resets the log to contain only that entry.

    Requires explicit confirmation parameter `confirm=clear-audit-log` to prevent
    accidental deletion.

    Args:
        confirm: Must be exactly "clear-audit-log" to proceed

    Returns:
        Confirmation of log clearing with previous entry count
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate confirmation
    if confirm != "clear-audit-log":
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                error_code="INVALID_REQUEST",
                message="Confirmation required: add ?confirm=clear-audit-log",
                request_id=request_id,
            ).model_dump(),
        )

    # Initialize audit logger
    audit_logger = AuditLogger(formation.formation_id)

    # Clear the log (this creates a "cleared" entry)
    previous_count = audit_logger.clear(user="admin", request_id=request_id)

    response_data = {
        "message": "Audit log cleared successfully",
        "previous_entries_count": previous_count,
        "cleared_by": "admin",
    }

    response = create_success_response(
        APIObjectType.AUDIT_LOG,
        APIEventType.AUDIT_CLEARED,
        response_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
