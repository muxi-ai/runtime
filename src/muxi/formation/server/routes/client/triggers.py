"""
Trigger endpoints for webhook-like event handling.

These endpoints allow external systems to trigger formation actions
with template-based message generation from event data.
"""

from typing import Dict, Any, Optional
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .....services import observability
from ...utils import render_trigger_template

router = APIRouter(tags=["Triggers"])


class TriggerRequest(BaseModel):
    """Model for trigger requests."""

    data: Dict[str, Any] = Field(..., description="Event data to pass to trigger template")
    user_id: Optional[str] = Field(default="0", description="User ID for request context")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation grouping")
    use_async: Optional[bool] = Field(default=True, description="Process trigger asynchronously (default: true)")


class TriggerResponse(BaseModel):
    """Model for trigger response."""

    status: str = Field(..., description="Status: 'queued' for async, 'completed' for sync")
    trigger_id: str = Field(..., description="ID of the trigger execution")
    job_id: Optional[str] = Field(None, description="Job ID for async triggers")
    message: Optional[str] = Field(None, description="Rendered message for sync triggers")


@router.post("/formations/{formation_id}/triggers/{trigger_name}")
async def execute_trigger(
    formation_id: str,
    trigger_name: str,
    request: Request,
    trigger_request: TriggerRequest,
    background_tasks: BackgroundTasks,
) -> TriggerResponse:
    """
    Execute a trigger with provided event data.

    Triggers are formation-scoped templates that convert external events
    into formation chat messages. Templates use ${{ data.* }} syntax
    for data substitution.

    Args:
        formation_id: ID of the formation
        trigger_name: Name of the trigger template
        trigger_request: Trigger request data

    Returns:
        TriggerResponse with execution status and IDs

    Examples:
        POST /v1/formations/my-formation/triggers/github-issue
        {
            "data": {
                "issue": {
                    "number": 123,
                    "title": "Bug in login",
                    "author": "user"
                }
            },
            "use_async": true
        }
    """
    formation = request.app.state.formation

    # Verify formation ID matches
    if formation.formation_id != formation_id:
        raise HTTPException(
            status_code=404,
            detail=f"Formation '{formation_id}' not found. Current formation: '{formation.formation_id}'",
        )

    # Ensure overlord is running
    if not formation.is_overlord_running():
        raise HTTPException(status_code=503, detail="Overlord not available")

    # Load trigger template
    trigger_path = formation.formation_dir / "triggers" / f"{trigger_name}.md"
    if not trigger_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Trigger template '{trigger_name}' not found at: {trigger_path}",
        )

    try:
        template = trigger_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read trigger template: {str(e)}",
        )

    # Render template with provided data
    try:
        rendered_message = render_trigger_template(template, trigger_request.data)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Template rendering failed: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error rendering template: {str(e)}",
        )

    # Generate trigger execution ID
    import uuid
    trigger_id = f"trigger_{uuid.uuid4().hex[:12]}"

    # Log trigger execution
    observability.observe(
        event_type=observability.ConversationEvents.REQUEST_RECEIVED,
        level=observability.EventLevel.INFO,
        data={
            "service": "formation_api_server",
            "endpoint": "/api/formations/{formation_id}/triggers/{trigger_name}",
            "formation_id": formation_id,
            "trigger_name": trigger_name,
            "trigger_id": trigger_id,
            "user_id": trigger_request.user_id,
            "session_id": trigger_request.session_id,
            "use_async": trigger_request.use_async,
            "data_keys": list(trigger_request.data.keys()),
        },
        description=f"Trigger '{trigger_name}' executed",
    )

    # Get overlord for processing
    overlord = formation._overlord

    if trigger_request.use_async:
        # Process asynchronously
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        async def process_async():
            """Background task to process trigger."""
            try:
                # Use overlord's chat method (non-streaming)
                response = await overlord.chat(
                    rendered_message,
                    user_id=trigger_request.user_id,
                    session_id=trigger_request.session_id,
                    request_id=trigger_id,
                )

                observability.observe(
                    event_type=observability.ConversationEvents.RESPONSE_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "formation_api_server",
                        "trigger_id": trigger_id,
                        "job_id": job_id,
                        "formation_id": formation_id,
                        "trigger_name": trigger_name,
                    },
                    description=f"Trigger '{trigger_name}' completed",
                )

            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "service": "formation_api_server",
                        "trigger_id": trigger_id,
                        "job_id": job_id,
                        "formation_id": formation_id,
                        "trigger_name": trigger_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Trigger '{trigger_name}' failed: {e}",
                )

        # Add to background tasks
        background_tasks.add_task(process_async)

        return TriggerResponse(
            status="queued",
            trigger_id=trigger_id,
            job_id=job_id,
        )

    else:
        # Process synchronously
        try:
            # Use overlord's chat method (non-streaming for sync triggers)
            response = await overlord.chat(
                rendered_message,
                user_id=trigger_request.user_id,
                session_id=trigger_request.session_id,
                request_id=trigger_id,
            )

            observability.observe(
                event_type=observability.ConversationEvents.RESPONSE_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "trigger_id": trigger_id,
                    "formation_id": formation_id,
                    "trigger_name": trigger_name,
                },
                description=f"Trigger '{trigger_name}' completed synchronously",
            )

            return TriggerResponse(
                status="completed",
                trigger_id=trigger_id,
                message=rendered_message,
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation_api_server",
                    "trigger_id": trigger_id,
                    "formation_id": formation_id,
                    "trigger_name": trigger_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Trigger '{trigger_name}' failed: {e}",
            )
            raise HTTPException(
                status_code=500,
                detail=f"Trigger execution failed: {str(e)}",
            )


@router.get("/formations/{formation_id}/triggers")
async def list_triggers(formation_id: str, request: Request) -> JSONResponse:
    """
    List available triggers for a formation.

    Args:
        formation_id: ID of the formation

    Returns:
        JSON with list of available trigger names
    """
    formation = request.app.state.formation

    # Verify formation ID matches
    if formation.formation_id != formation_id:
        raise HTTPException(
            status_code=404,
            detail=f"Formation '{formation_id}' not found. Current formation: '{formation.formation_id}'",
        )

    # Get triggers directory
    triggers_dir = formation.formation_dir / "triggers"

    if not triggers_dir.exists():
        return JSONResponse(
            content={
                "formation_id": formation_id,
                "triggers": [],
                "count": 0,
            }
        )

    # List all .md files in triggers directory
    try:
        trigger_files = list(triggers_dir.glob("*.md"))
        trigger_names = [f.stem for f in trigger_files]

        return JSONResponse(
            content={
                "formation_id": formation_id,
                "triggers": sorted(trigger_names),
                "count": len(trigger_names),
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list triggers: {str(e)}",
        )
