"""
Audit log endpoints.

These endpoints provide access to the formation audit trail,
requiring admin API key authentication.

NOTE: Audit logging is not yet implemented. See docs/features/audit-logging.md
for the implementation plan.
"""

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ...responses import APIResponse, create_error_response

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

    **Status: Not Yet Implemented**

    Will return audit trail of formation initialization and runtime operations.
    See docs/features/audit-logging.md for the implementation plan.

    **Planned Tracked Operations:**
    - Initialization: agent.registered, mcp.server.registered, etc.
    - Runtime: secret.created, secret.deleted, memory.buffer.cleared
    """
    request_id = getattr(request.state, "request_id", None)

    response = create_error_response(
        error_code="NOT_IMPLEMENTED",
        message="Audit logging is not yet implemented. See docs/features/audit-logging.md",
        request_id=request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=501)


@router.delete("/audit", response_model=APIResponse)
async def clear_audit_log(
    request: Request,
    confirm: str | None = Query(None, description="Required confirmation string to prevent accidental deletion"),
) -> JSONResponse:
    """
    Clear the audit log file.

    **Status: Not Yet Implemented**

    See docs/features/audit-logging.md for the implementation plan.
    """
    request_id = getattr(request.state, "request_id", None)

    response = create_error_response(
        error_code="NOT_IMPLEMENTED",
        message="Audit logging is not yet implemented. See docs/features/audit-logging.md",
        request_id=request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=501)
