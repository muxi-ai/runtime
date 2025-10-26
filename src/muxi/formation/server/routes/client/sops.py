"""
Standard Operating Procedures (SOP) endpoints.

These endpoints provide read-only access to formation-defined SOPs,
requiring client API key authentication.
"""

import re
from typing import Dict, Any, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    APIResponse,
    create_success_response,
    create_error_response,
)
from .....datatypes.api import APIEventType, APIObjectType

router = APIRouter(tags=["SOPs"])


def _extract_agents_from_sop(metadata: Dict[str, Any], content: str) -> List[str]:
    """
    Extract agent names from SOP metadata or content.

    Prefer metadata-first approach to avoid false positives from prose.
    Falls back to parsing content only when metadata is absent.

    Args:
        metadata: SOP frontmatter metadata dictionary
        content: SOP markdown content

    Returns:
        List of agent names used in the SOP
    """
    agents_used = []

    # First, try metadata fields
    if "agents" in metadata:
        agents_used = metadata["agents"]
    elif "routing" in metadata and "agents" in metadata.get("routing", {}):
        agents_used = metadata["routing"]["agents"]
    else:
        # Fallback: Parse from content (only YAML-structured key patterns)
        # Only detect "agent:" at line start (after optional whitespace) to avoid prose
        for line in content.split("\n"):
            # Match lines that start with optional whitespace followed by "agent:" as a key
            match = re.match(r'^\s*agent:\s*(.+?)\s*$', line, re.IGNORECASE)
            if match:
                agent_name = match.group(1).strip()
                # Validate: non-empty, alphanumeric/underscore/dash only
                if agent_name and re.match(r'^[a-zA-Z0-9_-]+$', agent_name):
                    if agent_name not in agents_used:
                        agents_used.append(agent_name)

    return agents_used


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
        # Safe check: strip once, verify non-empty, then check first char
        def is_numbered_line(line: str) -> bool:
            stripped = line.strip()
            return len(stripped) > 0 and stripped[0].isdigit()
        
        steps = sum(1 for line in content.split("\n") if is_numbered_line(line))

        # Extract agents used (from content or metadata)
        agents_used = _extract_agents_from_sop(metadata, content)

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

    # Validate sop_name to prevent path traversal attacks
    if not re.match(r'^[a-zA-Z0-9_-]+$', sop_name):
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                error_code="INVALID_REQUEST",
                message=f"Invalid SOP name {sop_name!r}: must contain only letters, numbers, hyphens, and underscores",
                request_id=request_id,
            ).model_dump(),
        )

    # Access the SOP system from the overlord
    overlord = formation._overlord
    if not hasattr(overlord, "sop_system") or not overlord.sop_system:
        # No SOPs configured
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                error_code="SOP_NOT_FOUND",
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
                error_code="SOP_NOT_FOUND",
                message=f"SOP '{sop_name}' not found",
                request_id=request_id,
            ).model_dump(),
        )

    # Get SOP data
    sop_data = sop_system.sops[sop_name]
    metadata = sop_data.get("metadata", {})
    content = sop_data.get("content", "")

    # Count steps (safe check: strip once, verify non-empty, then check first char)
    def is_numbered_line(line: str) -> bool:
        stripped = line.strip()
        return len(stripped) > 0 and stripped[0].isdigit()
    
    steps = sum(1 for line in content.split("\n") if is_numbered_line(line))

    # Extract agents used
    agents_used = _extract_agents_from_sop(metadata, content)

    # Extract references (files referenced in the SOP)
    references = []
    if "references" in metadata:
        references = metadata["references"]
    else:
        # Look for [file:...] patterns in content
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
