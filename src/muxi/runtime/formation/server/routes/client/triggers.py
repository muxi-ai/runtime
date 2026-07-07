"""
Trigger endpoints for webhook-like event handling.

These endpoints allow external systems to trigger formation actions
with template-based message generation from event data.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .....datatypes.api import APIEventType, APIObjectType
from .....services import observability
from .....utils.id_generator import generate_request_id
from .....utils.response_converter import extract_response_content
from ....background.transformers import (
    TransformerConfig,
    deliver_via_transformer,
    extract_parse_values,
    load_transformer,
    parse_trigger_frontmatter,
)
from ...responses import (
    APIResponse,
    create_api_response,
    create_error_response,
    create_success_response,
)
from ...utils import get_header_case_insensitive, render_trigger_template

router = APIRouter(tags=["Triggers"])


def _default_agent_name(formation) -> Optional[str]:
    """Best-effort default agent name for transformer template variables."""
    agents = formation.config.get("agents") or []
    for agent in agents:
        if isinstance(agent, dict) and agent.get("default"):
            return agent.get("name") or agent.get("id")
    if agents and isinstance(agents[0], dict):
        return agents[0].get("name") or agents[0].get("id")
    return None


class TriggerRequest(BaseModel):
    """Model for trigger requests."""

    data: Dict[str, Any] = Field(..., description="Event data to pass to trigger template")
    session_id: Optional[str] = Field(
        default=None, description="Session ID for conversation grouping"
    )
    use_async: Optional[bool] = Field(
        default=True, description="Process trigger asynchronously (default: true)"
    )


@router.get("/triggers", operation_id="list_triggers")
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
    pattern = r"\$\{\{\s*data\.([a-zA-Z0-9_.]+)\s*\}\}"
    matches = re.findall(pattern, content)
    # Return unique, sorted list
    return sorted(set(matches))


@router.get("/triggers/{trigger_name}", operation_id="get_trigger")
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
    if not re.match(r"^[a-zA-Z0-9_-]+$", trigger_name):
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


@router.post("/triggers/{trigger_name}", operation_id="execute_trigger")
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

    # GBAC Phase 3: a trigger fires only when the requesting user's groups
    # permit it. Per the PRD's channel table, API/webhook callers get a 403
    # with a generic message. No-op when the formation has no groups/
    # directory. The membership lookup is TTL-cached by the resolver.
    resolver = formation.permission_resolver
    if resolver is not None:
        from .....services.gbac import enforcement as gbac_enforcement

        # Normalize the identifier the same way the overlord chat path does
        permissions = await resolver.resolve(str(user_id).lower().strip())
        if not permissions.is_allowed("triggers", trigger_name):
            gbac_enforcement.observe_denied(
                "triggers",
                trigger_name,
                permissions=permissions,
                user_id=user_id,
                formation_id=formation_id,
                channel="api",
            )
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions to execute this trigger",
            )

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

    # Parse optional YAML frontmatter (outbound routing: webhook/transformer,
    # inbound extraction: parse). Triggers without frontmatter pass through
    # unchanged and take the exact same code path as before.
    try:
        trigger_meta, template = parse_trigger_frontmatter(template)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid frontmatter in trigger '{trigger_name}': {str(e)}",
        )

    # Fail fast on malformed/missing transformer config before any LLM work
    transformer_config: Optional[TransformerConfig] = None
    if trigger_meta.get("transformer"):
        try:
            transformer_config = load_transformer(formation_dir, trigger_meta["transformer"])
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid transformer for trigger '{trigger_name}': {str(e)}",
            )
    webhook_override: Optional[str] = trigger_meta.get("webhook")

    # Extract platform request values (message/user_id/context) per parse spec
    try:
        parsed_request = extract_parse_values(trigger_meta.get("parse"), trigger_request.data)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid parse spec in trigger '{trigger_name}': {str(e)}",
        )

    # The parsed platform user (e.g. Slack user id) scopes conversation and
    # memory; the header user remains the authenticated principal for GBAC.
    chat_user_id = parsed_request.get("user_id") or user_id

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

    async def deliver_transformed(response: Any, response_content: str) -> None:
        """Format the agent response with the trigger's transformer and deliver it."""
        if transformer_config is None:  # Callers only schedule this when a transformer exists
            return
        try:
            await deliver_via_transformer(
                webhook_manager=overlord.webhook_manager,
                secrets_manager=formation.secrets_manager,
                transformer=transformer_config,
                response_content=response_content,
                response=response,
                request_message=parsed_request.get("message"),
                request_user_id=chat_user_id,
                request_files=parsed_request.get("files"),
                context=parsed_request.get("context"),
                agent_name=_default_agent_name(formation),
                request_id=request_id,
                formation_id=formation_id,
                fallback_webhook_url=getattr(overlord, "async_webhook_url", None),
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.WEBHOOK_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "request_id": request_id,
                    "formation_id": formation_id,
                    "trigger_name": trigger_name,
                    "type": "transformer",
                    "transformer": transformer_config.name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Transformer delivery for trigger '{trigger_name}' failed: {e}",
            )

    if trigger_request.use_async:
        # Process asynchronously
        async def process_async() -> None:
            """Background task to process trigger."""
            try:
                if transformer_config is not None:
                    # Transformer routing: run the request to completion here
                    # (forced sync, non-streaming) so the final content can be
                    # formatted and delivered to the transformer endpoint.
                    response = await overlord.chat(
                        rendered_message,
                        user_id=chat_user_id,
                        session_id=trigger_request.session_id,
                        request_id=request_id,
                        bypass_workflow_approval=True,
                        use_async=False,
                        stream=False,
                    )
                elif webhook_override is not None:
                    # Webhook routing: force async so the standard MUXI
                    # payload is always delivered to the override URL.
                    await overlord.chat(
                        rendered_message,
                        user_id=chat_user_id,
                        session_id=trigger_request.session_id,
                        request_id=request_id,
                        bypass_workflow_approval=True,
                        use_async=True,
                        webhook_url=webhook_override,
                    )
                else:
                    # Default routing: unchanged trigger behavior
                    # Use overlord's chat method (non-streaming)
                    # Bypass workflow approval for triggers (automated execution)
                    await overlord.chat(
                        rendered_message,
                        user_id=chat_user_id,
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

                if transformer_config is not None:
                    response_content = await extract_response_content(response)
                    await deliver_transformed(response, response_content)

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
                user_id=chat_user_id,
                session_id=trigger_request.session_id,
                request_id=request_id,
                bypass_workflow_approval=True,
                stream=False,
                webhook_url=webhook_override,
            )

            # Extract content from response (handles async generators, MuxiResponse, strings, etc.)
            response_content = await extract_response_content(response)

            # Deliver the formatted response to the transformer endpoint in
            # the background; the caller still receives the standard payload.
            if transformer_config is not None:
                background_tasks.add_task(deliver_transformed, response, response_content)

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
                data={"status": "completed", "content": response_content},  # LLM response text
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
