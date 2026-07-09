"""
Knowledge management endpoints.

Admin-key endpoints for the reasoning-RAG knowledge system. Today this is
the per-agent tree rebuild trigger - the runtime side of the CLI's
``muxi knowledge rebuild`` (the CLI subcommand lives in the CLI repo and
calls this endpoint).
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .....datatypes.api import APIEventType, APIObjectType
from ...responses import (
    APIResponse,
    create_error_response,
    create_success_response,
)

router = APIRouter(tags=["Knowledge"])


class KnowledgeRebuildRequest(BaseModel):
    """Model for a per-agent knowledge tree rebuild request.

    ``agent_id`` limits the rebuild to one agent (omit for all agents);
    ``source_id`` limits it to one agent-tree source slug (omit for all
    of the agent's agent-tree sources).
    """

    agent_id: Optional[str] = None
    source_id: Optional[str] = None


@router.post(
    "/knowledge/rebuild", response_model=APIResponse, operation_id="rebuild_knowledge_trees"
)
async def rebuild_knowledge_trees(
    request: Request, rebuild: KnowledgeRebuildRequest
) -> JSONResponse:
    """
    Force-rebuild persistent per-agent knowledge trees.

    Walks the formation's agents (or the one named by ``agent_id``) and
    rebuilds every source declaring an ``agent_tree:`` block, regardless of
    its ``regenerate`` trigger. Agents without agent-tree sources report an
    empty result rather than an error.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    overlord = getattr(formation, "_overlord", None)
    agents = getattr(overlord, "agents", None) if overlord else None
    if not agents:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "No agents are available on this formation",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    if rebuild.agent_id and rebuild.agent_id not in agents:
        response = create_error_response(
            "AGENT_NOT_FOUND",
            f"Agent '{rebuild.agent_id}' not found",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    targets = {rebuild.agent_id: agents[rebuild.agent_id]} if rebuild.agent_id else dict(agents)

    reports = {}
    try:
        for agent_id, agent in targets.items():
            handler = getattr(agent, "knowledge_handler", None)
            if handler is None or not getattr(handler, "_agent_tree_sources", None):
                reports[agent_id] = {"rebuilt": [], "failed": [], "skipped": []}
                continue
            reports[agent_id] = await handler.rebuild_agent_trees(source_id=rebuild.source_id)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to rebuild knowledge trees: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    data = {"agents": reports, "source_id": rebuild.source_id}
    response = create_success_response(
        APIObjectType.KNOWLEDGE, APIEventType.KNOWLEDGE_TREES_REBUILT, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
