"""
Event streaming endpoints.

These endpoints provide SSE streams for async updates,
requiring client API key authentication.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["Events"])


@router.get("/events/{user_id}")
async def user_events(request: Request, user_id: str) -> StreamingResponse:
    """
    SSE stream for async updates for a specific user.

    Args:
        user_id: User ID to get events for

    Returns:
        Server-sent event stream
        
    Note:
        Client API key authentication is enforced at the router level
    """
    # TODO: Implement user event streaming
    raise HTTPException(status_code=501, detail="Event streaming not yet implemented")
