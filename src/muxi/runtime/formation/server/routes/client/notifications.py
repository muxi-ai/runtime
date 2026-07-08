"""
Proactive notification endpoints (Proactiveness Phase 1).

Lets clients (and formation tooling) send a text notification to a user
through the formation's notification routing:

    explicit channel(s) > user preferred channel > formation
    default_channel > webhook

Requires the formation to declare a 'proactive' block; formations without
one return 503 and are otherwise unaffected.
"""

from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .....datatypes.api import APIEventType, APIObjectType
from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
)

router = APIRouter(tags=["Notifications"])


class NotificationRequest(BaseModel):
    """Request model for sending a proactive notification."""

    user_id: str = Field(..., description="External user id to notify")
    message: str = Field(..., description="Notification text (v1 is text-only)")
    channels: Optional[List[str]] = Field(
        None,
        description="Optional explicit channels (declared names or the reserved "
        "'last', 'preferred', 'webhook'); overrides the user's preference",
    )


@router.post("/notifications", response_model=APIResponse, operation_id="send_notification")
async def send_notification(request: Request, body: NotificationRequest) -> JSONResponse:
    """
    Send a proactive notification to a user via the routing precedence.

    Returns the resolved channels plus which deliveries succeeded/failed.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    notification_router = getattr(overlord, "notification_router", None) if overlord else None
    if notification_router is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Proactive notifications are not configured for this formation "
            "(missing 'proactive' block)",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    if not body.message.strip():
        response = create_error_response(
            "INVALID_REQUEST",
            "'message' must be a non-empty string",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    # Single-user formations track all state under user "0" (same
    # normalization as the overlord chat path)
    user_id = body.user_id
    if not getattr(overlord, "is_multi_user", True):
        user_id = "0"

    result = await notification_router.notify(
        user_id=user_id,
        message=body.message,
        channels=body.channels,
        request_id=request_id,
        source="api",
    )

    response = create_success_response(
        APIObjectType.NOTIFICATION,
        APIEventType.NOTIFICATION_SENT,
        result,
        request_id,
    )
    status_code = 200 if result.get("delivered") else 502
    return JSONResponse(content=response.model_dump(), status_code=status_code)
