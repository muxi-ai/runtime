"""
Trigger endpoints for webhook-like event handling.

These endpoints allow external systems to trigger formation actions
with template-based message generation from event data.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .....services import observability
from .....datatypes.api import APIObjectType, APIEventType
from .....utils.id_generator import generate_request_id
from .....utils.response_converter import extract_response_content
from ...responses import create_api_response, create_success_response, create_error_response, APIResponse
from ...utils import render_trigger_template, get_header_case_insensitive

router = APIRouter(tags=["Triggers"])


class TriggerRequest(BaseModel):
    """Model for trigger requests."""

    data: Dict[str, Any] = Field(..., description="Event data to pass to trigger template")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation grouping")
    use_async: Optional[bool] = Field(default=True, description="Process trigger asynchronously (default: true)")


@router.get("/triggers")
async def list_triggers(request: Request) -> APIResponse:
    """
    List available triggers for the formation.

    Returns:
        JSON with list of available trigger names
    """
    formation = request.app.state.formation

    # Get formation directory
    formation_path = formation.get_formation_path()
    if not formation_path:
        raise HTTPException(status_code=500, detail="Formation path not available")
    formation_dir = Path(formation_path)
    if formation_dir.is_file():
        formation_dir = formation_dir.parent

    # Get triggers directory
    triggers_dir = formation_dir / "triggers"

    # List all .md files in triggers directory
    try:
        if not triggers_dir.exists():
            trigger_names = []
        else:
            trigger_files = list(triggers_dir.glob("*.md"))
            trigger_names = sorted([f.stem for f in trigger_files])

        return create_api_response(
            object_type=APIObjectType.LIST,
            event_type=APIEventType.LIST_RETRIEVED,
            data={
                "formation_id": formation.formation_id,
                "triggers": trigger_names,
                "count": len(trigger_names),
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list triggers: {str(e)}",
        )


def _extract_data_placeholders(content: str) -> List[str]:
    """
    Extract ${{ data.xxx }} placeholders from trigger template.

    Args:
        content: Trigger template content

    Returns:
        List of unique data field paths (e.g., ["user.name", "event.type"])
    """
    # Match ${{ data.xxx }} patterns
    pattern = r'\$\{\{\s*data\.([a-zA-Z0-9_.]+)\s*\}\}'
    matches = re.findall(pattern, content)
    # Return unique, sorted list
    return sorted(set(matches))


@router.get("/triggers/{trigger_name}")
async def get_trigger(request: Request, trigger_name: str) -> JSONResponse:
    """
    Get detailed information about a specific trigger.

    Returns the trigger template content and metadata, including:
    - Full markdown content
    - Expected data placeholders (parsed from ${{ data.xxx }} patterns)

    **Read-only**: Triggers cannot be modified via API.

    Args:
        trigger_name: Name of the trigger (without .md extension)

    Returns:
        Trigger details with content and expected data fields
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Validate trigger_name to prevent path traversal attacks
    if not re.match(r'^[a-zA-Z0-9_-]+$', trigger_name):
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                error_code="INVALID_REQUEST",
                message=f"Invalid trigger name {trigger_name!r}: must contain only letters, numbers, hyphens, and underscores",
                request_id=request_id,
            ).model_dump(),
        )

    # Get formation directory
    formation_path = formation.get_formation_path()
    if not formation_path:
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                error_code="INTERNAL_ERROR",
                message="Formation path not available",
                request_id=request_id,
            ).model_dump(),
        )

    formation_dir = Path(formation_path)
    if formation_dir.is_file():
        formation_dir = formation_dir.parent

    # Load trigger template
    trigger_path = formation_dir / "triggers" / f"{trigger_name}.md"
    if not trigger_path.exists():
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                error_code="TRIGGER_NOT_FOUND",
                message=f"Trigger '{trigger_name}' not found",
                request_id=request_id,
            ).model_dump(),
        )

    try:
        content = trigger_path.read_text(encoding="utf-8")
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                error_code="INTERNAL_ERROR",
                message=f"Failed to read trigger template: {str(e)}",
                request_id=request_id,
            ).model_dump(),
        )

    # Extract expected data placeholders
    data_fields = _extract_data_placeholders(content)

    response_data = {
        "name": trigger_name,
        "content": content,
        "data_fields": data_fields if data_fields else None,
    }

    response = create_success_response(
        APIObjectType.TRIGGER,
        APIEventType.TRIGGER_RETRIEVED,
        response_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/triggers/{trigger_name}")
async def execute_trigger(
    trigger_name: str,
    request: Request,
    trigger_request: TriggerRequest,
    background_tasks: BackgroundTasks,
) -> APIResponse:
    """
    Execute a trigger with provided event data.

    Triggers are webhook-friendly request endpoints that render templates
    into chat messages and process them like any other request.

    Args:
        trigger_name: Name of the trigger template
        trigger_request: Trigger request data

    Headers:
        X-Muxi-User-Id: User ID for request context (optional, defaults to "0")

    Returns:
        Standard API response with request_id and status

    Examples:
        POST /v1/triggers/github-issue
        Headers: X-Muxi-User-Id: webhook-user
        Body: {
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
    formation_id = formation.formation_id

    # Generate request ID upfront
    request_id = generate_request_id()

    # Extract user_id from header (case-insensitive)
    user_id = get_header_case_insensitive(request.headers, "X-Muxi-User-Id") or "0"

    # Ensure overlord is running
    if not formation.is_overlord_running():
        raise HTTPException(status_code=503, detail="Overlord not available")

    # Get formation directory
    formation_path = formation.get_formation_path()
    if not formation_path:
        raise HTTPException(status_code=500, detail="Formation path not available")
    formation_dir = Path(formation_path)
    if formation_dir.is_file():
        formation_dir = formation_dir.parent

    # Load trigger template
    trigger_path = formation_dir / "triggers" / f"{trigger_name}.md"
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

    # Log trigger execution
    observability.observe(
        event_type=observability.ConversationEvents.REQUEST_RECEIVED,
        level=observability.EventLevel.INFO,
        data={
            "service": "formation_api_server",
            "endpoint": "/v1/triggers/{trigger_name}",
            "formation_id": formation_id,
            "trigger_name": trigger_name,
            "request_id": request_id,
            "user_id": user_id,
            "session_id": trigger_request.session_id,
            "use_async": trigger_request.use_async,
            "data_keys": list(trigger_request.data.keys()),
        },
        description=f"Trigger '{trigger_name}' request received",
    )

    # Get overlord for processing
    overlord = formation._overlord

    if trigger_request.use_async:
        # Process asynchronously
        async def process_async() -> None:
            """Background task to process trigger."""
            try:
                # Use overlord's chat method (non-streaming)
                # Bypass workflow approval for triggers (automated execution)
                await overlord.chat(
                    rendered_message,
                    user_id=user_id,
                    session_id=trigger_request.session_id,
                    request_id=request_id,
                    bypass_workflow_approval=True,
                )

                observability.observe(
                    event_type=observability.ConversationEvents.REQUEST_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={
                        "service": "formation_api_server",
                        "request_id": request_id,
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
                        "request_id": request_id,
                        "formation_id": formation_id,
                        "trigger_name": trigger_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Trigger '{trigger_name}' failed: {e}",
                )

        # Add to background tasks
        background_tasks.add_task(process_async)

        # Return standard async response
        return create_api_response(
            object_type=APIObjectType.REQUEST,
            event_type=APIEventType.REQUEST_PROCESSING,
            data={"status": "processing"},
            request_id=request_id,
        )

    else:
        # Process synchronously (non-streaming)
        try:
            # Use overlord's chat method (non-streaming for triggers)
            # Bypass workflow approval for triggers (automated execution)
            # Explicitly disable streaming to get actual content, not a generator
            response = await overlord.chat(
                rendered_message,
                user_id=user_id,
                session_id=trigger_request.session_id,
                request_id=request_id,
                bypass_workflow_approval=True,
                stream=False,
            )

            # Extract content from response (handles async generators, MuxiResponse, strings, etc.)
            response_content = await extract_response_content(response)

            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "service": "formation_api_server",
                    "request_id": request_id,
                    "formation_id": formation_id,
                    "trigger_name": trigger_name,
                },
                description=f"Trigger '{trigger_name}' completed synchronously",
            )

            return create_api_response(
                object_type=APIObjectType.REQUEST,
                event_type=APIEventType.REQUEST_COMPLETED,
                data={
                    "status": "completed",
                    "content": response_content  # LLM response text
                },
                request_id=request_id,
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "service": "formation_api_server",
                    "request_id": request_id,
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
