# Audit API Implementation Plan

## Status: Ready to Implement

## Overview

Connect the existing `AuditLogger` class to the `/audit` API endpoints.

## Current State

- `AuditLogger` class exists in `src/muxi/runtime/formation/server/audit.py`
- Routes exist in `src/muxi/runtime/formation/server/routes/admin/audit.py` but return 501
- AuditLogger is never instantiated

## Implementation Steps

### Step 1: Create AuditLogger on Server Startup

**File:** `src/muxi/runtime/formation/server/server.py`

```python
from .audit import AuditLogger

class FormationServer:
    def __init__(self, formation: Formation):
        # ... existing code ...
        self.audit_logger = AuditLogger(formation_id=formation.id)
    
    async def start(self, ...):
        # ... existing code ...
        self.app.state.audit_logger = self.audit_logger
```

### Step 2: Update GET /audit Endpoint

**File:** `src/muxi/runtime/formation/server/routes/admin/audit.py`

```python
from datetime import datetime
from ..audit import AuditLogger
from ...responses import create_success_response

@router.get("/audit", response_model=APIResponse)
async def get_audit_log(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    audit_logger: AuditLogger = request.app.state.audit_logger
    
    # Parse since datetime if provided
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            return JSONResponse(
                content=create_error_response(
                    error_code="INVALID_PARAMETER",
                    message=f"Invalid ISO 8601 timestamp: {since}",
                    request_id=request_id,
                ).model_dump(),
                status_code=400,
            )
    
    entries = await audit_logger.get_entries(
        limit=limit,
        action=action,
        resource_type=resource_type,
        since=since_dt,
    )
    
    return JSONResponse(
        content=create_success_response(
            object_type="audit_log",
            event_type="audit.log.retrieved",
            data={"entries": entries, "count": len(entries)},
            request_id=request_id,
        ).model_dump(),
        status_code=200,
    )
```

### Step 3: Update DELETE /audit Endpoint

```python
@router.delete("/audit", response_model=APIResponse)
async def clear_audit_log(
    request: Request,
    confirm: str = Query(..., description="Must be 'CONFIRM' to proceed"),
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    
    if confirm != "CONFIRM":
        return JSONResponse(
            content=create_error_response(
                error_code="CONFIRMATION_REQUIRED",
                message="Must provide confirm=CONFIRM query parameter",
                request_id=request_id,
            ).model_dump(),
            status_code=400,
        )
    
    audit_logger: AuditLogger = request.app.state.audit_logger
    cleared_count = await audit_logger.clear(
        user="admin",
        request_id=request_id,
    )
    
    return JSONResponse(
        content=create_success_response(
            object_type="audit_log",
            event_type="audit.log.cleared",
            data={"cleared_entries": cleared_count},
            request_id=request_id,
        ).model_dump(),
        status_code=200,
    )
```

### Step 4: Add Shutdown Hook

**File:** `src/muxi/runtime/formation/server/server.py`

```python
async def stop(self):
    # ... existing cleanup ...
    if self.audit_logger:
        await self.audit_logger.shutdown()
```

## Testing

Update `e2e/tests/19_api/test_19a1_audit_logging.py` to expect 200 instead of 501.

## Future Enhancements (Phase 2)

1. Add audit logging to other admin routes (agents, secrets, scheduler)
2. Add middleware for automatic request logging
3. Add formation initialization audit events
