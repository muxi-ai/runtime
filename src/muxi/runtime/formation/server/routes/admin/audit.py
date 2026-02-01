"""
Audit log endpoints.

These endpoints provide access to the formation audit trail,
requiring admin API key authentication.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIEventType,
    APIObjectType,
    APIResponse,
    create_error_response,
    create_success_response,
)

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

    Returns audit trail of formation initialization and runtime operations.

    **Tracked Operations:**
    - Initialization: agent.registered, mcp.server.registered, etc.
    - Runtime: secret.created, secret.deleted, memory.buffer.cleared
    """
    request_id = getattr(request.state, "request_id", None)

    # Get audit logger from app state
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if not audit_logger:
        response = create_error_response(
            error_code="SERVICE_UNAVAILABLE",
            message="Audit logging not initialized",
            request_id=request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Parse since timestamp if provided
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            response = create_error_response(
                error_code="INVALID_PARAMETER",
                message=f"Invalid timestamp format: {since}. Use ISO 8601 format.",
                request_id=request_id,
            )
            return JSONResponse(content=response.model_dump(), status_code=400)

    # Get entries
    entries = await audit_logger.get_entries(
        limit=limit,
        action=action,
        resource_type=resource_type,
        since=since_dt,
    )

    result = {
        "entries": entries,
        "total_entries": len(entries),
        "limit": limit,
    }

    response = create_success_response(
        APIObjectType.AUDIT_LOG, APIEventType.AUDIT_RETRIEVED, result, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/audit", response_model=APIResponse)
async def clear_audit_log(
    request: Request,
    confirm: str | None = Query(
        None, description="Required confirmation string to prevent accidental deletion"
    ),
) -> JSONResponse:
    """
    Clear the audit log file.

    Requires confirm="yes" query parameter to prevent accidental deletion.
    """
    request_id = getattr(request.state, "request_id", None)

    # Require confirmation
    if confirm != "clear-audit-log":
        response = create_error_response(
            error_code="INVALID_REQUEST",
            message="Confirmation required: add ?confirm=clear-audit-log to delete",
            request_id=request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Get audit logger from app state
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if not audit_logger:
        response = create_error_response(
            error_code="SERVICE_UNAVAILABLE",
            message="Audit logging not initialized",
            request_id=request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    # Get user from request state
    user = getattr(request.state, "authenticated_user", "admin")

    # Clear the log
    cleared_count = await audit_logger.clear(user=user, request_id=request_id)

    result = {
        "previous_entries_count": cleared_count,
        "cleared_by": user,
        "message": f"Audit log cleared ({cleared_count} entries removed)",
    }

    response = create_success_response(
        APIObjectType.AUDIT_LOG, APIEventType.AUDIT_CLEARED, result, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
