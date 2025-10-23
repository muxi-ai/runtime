"""
Standard Operating Procedures (SOP) endpoints.

These endpoints provide read-only access to formation-defined SOPs,
requiring client API key authentication.
"""

from typing import Dict, List, Any
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["SOPs"])


@router.get("/sops", response_model=APIResponse)
async def list_sops(request: Request) -> JSONResponse:
    """
    List all available Standard Operating Procedures.

    SOPs are workflow templates stored in `formation_path/sops/` directory.
    They define multi-step procedures with agent routing for complex operations.

    **Read-only**: SOPs are formation-defined and cannot be modified via API.
    They must be updated in the formation YAML files and redeployed.

    Returns:
        List of available SOPs with metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Access the SOP system from the overlord
    overlord = formation._overlord
    if not hasattr(overlord, "sop_system") or not overlord.sop_system:
        # No SOPs configured
        response_data = {"sops": [], "count": 0}
        response = create_success_response(
            APIObjectType.SOP_LIST,
            APIEventType.SOPS_LIST,
            response_data,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    sop_system = overlord.sop_system
    sops_list = []

    for sop_name, sop_data in sop_system.sops.items():
        # Extract metadata from SOP
        metadata = sop_data.get("metadata", {})
        content = sop_data.get("content", "")

        # Count steps (simple heuristic: count numbered lines)
        steps = sum(1 for line in content.split("\n") if line.strip() and line.strip()[0].isdigit())

        # Extract agents used (from content or metadata)
        agents_used = []
        if "agents" in metadata:
            agents_used = metadata["agents"]
        else:
            # Parse from content (look for "Agent:" lines)
            for line in content.split("\n"):
                if "agent:" in line.lower():
                    # Extract agent name
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        agent_name = parts[1].strip()
                        if agent_name and agent_name not in agents_used:
                            agents_used.append(agent_name)

        sop_entry = {
            "name": sop_name,
            "title": metadata.get("title", sop_name),
            "type": metadata.get("type", "template"),
            "steps": steps if steps > 0 else None,
            "agents_used": agents_used if agents_used else None,
        }

        sops_list.append(sop_entry)

    response_data = {"sops": sops_list, "count": len(sops_list)}

    response = create_success_response(
        APIObjectType.SOP_LIST,
        APIEventType.SOPS_LIST,
        response_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.get("/sops/{sop_name}", response_model=APIResponse)
async def get_sop_details(request: Request, sop_name: str) -> JSONResponse:
    """
    Get detailed information about a specific Standard Operating Procedure.

    Returns the SOP metadata and content, including:
    - Full markdown content
    - Frontmatter metadata
    - Referenced files (if any)
    - Execution mode (template vs guide)

    **Read-only**: SOPs cannot be modified via API.

    Args:
        sop_name: Name of the SOP (without .md extension)

    Returns:
        SOP details with full content and metadata
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    # Access the SOP system from the overlord
    overlord = formation._overlord
    if not hasattr(overlord, "sop_system") or not overlord.sop_system:
        # No SOPs configured
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                error_code="RESOURCE_NOT_FOUND",
                message=f"SOP '{sop_name}' not found",
                request_id=request_id,
            ).model_dump(),
        )

    sop_system = overlord.sop_system

    # Check if SOP exists
    if sop_name not in sop_system.sops:
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                error_code="RESOURCE_NOT_FOUND",
                message=f"SOP '{sop_name}' not found",
                request_id=request_id,
            ).model_dump(),
        )

    # Get SOP data
    sop_data = sop_system.sops[sop_name]
    metadata = sop_data.get("metadata", {})
    content = sop_data.get("content", "")

    # Count steps
    steps = sum(1 for line in content.split("\n") if line.strip() and line.strip()[0].isdigit())

    # Extract agents used
    agents_used = []
    if "agents" in metadata:
        agents_used = metadata["agents"]
    else:
        # Parse from content
        for line in content.split("\n"):
            if "agent:" in line.lower():
                parts = line.split(":", 1)
                if len(parts) > 1:
                    agent_name = parts[1].strip()
                    if agent_name and agent_name not in agents_used:
                        agents_used.append(agent_name)

    # Extract references (files referenced in the SOP)
    references = []
    if "references" in metadata:
        references = metadata["references"]
    else:
        # Look for [file:...] patterns in content
        import re

        file_pattern = r"\[file:([^\]]+)\]"
        matches = re.findall(file_pattern, content)
        references = [f"file:{match}" for match in matches]

    response_data = {
        "name": sop_name,
        "title": metadata.get("title", sop_name),
        "type": metadata.get("type", "template"),
        "content": content,
        "metadata": metadata,
        "references": references if references else None,
        "agents_used": agents_used if agents_used else None,
        "steps": steps if steps > 0 else None,
    }

    response = create_success_response(
        APIObjectType.SOP,
        APIEventType.SOP_RETRIEVED,
        response_data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
