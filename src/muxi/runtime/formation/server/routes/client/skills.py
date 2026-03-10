"""
Skills endpoints.

Read-only access to formation skills, requiring client API key authentication.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...responses import (
    create_error_response,
    create_success_response,
)

router = APIRouter(tags=["Skills"])


@router.get(
    "/skills",
    summary="List loaded skills",
    operation_id="list_skills",
)
async def list_skills(request: Request) -> JSONResponse:
    """List all loaded skills with name, description, and scope."""
    formation = request.app.state.formation

    skill_manager = getattr(formation, "_skill_manager", None)
    if not skill_manager:
        return create_success_response(data={"skills": []})

    skills = skill_manager.get_all_skills_info()
    return create_success_response(data={"skills": skills})


@router.get(
    "/skills/{skill_name}",
    summary="Get skill metadata",
    operation_id="get_skill",
)
async def get_skill(request: Request, skill_name: str) -> JSONResponse:
    """Get metadata for a specific skill."""
    formation = request.app.state.formation

    skill_manager = getattr(formation, "_skill_manager", None)
    if not skill_manager:
        return create_error_response(
            message="Skills not configured",
            status_code=404,
        )

    skill = skill_manager.skills.get(skill_name)
    if not skill:
        return create_error_response(
            message=f"Skill '{skill_name}' not found",
            status_code=404,
        )

    resources = skill_manager._get_resources(skill_name)

    return create_success_response(
        data={
            "name": skill.name,
            "description": skill.description,
            "license": skill.license,
            "compatibility": skill.compatibility,
            "allowed_tools": skill.allowed_tools,
            "resources": resources,
        }
    )


@router.get(
    "/agents/{agent_id}/skills",
    summary="List skills available to an agent",
    operation_id="list_agent_skills",
)
async def list_agent_skills(request: Request, agent_id: str) -> JSONResponse:
    """List skills available to a specific agent (public + private)."""
    formation = request.app.state.formation

    skill_manager = getattr(formation, "_skill_manager", None)
    if not skill_manager:
        return create_success_response(data={"skills": []})

    available = skill_manager.get_available_skills(agent_id)
    skills = []
    for name in available:
        skill = skill_manager.skills.get(name)
        if skill:
            skills.append(
                {
                    "name": skill.name,
                    "description": skill.description,
                    "scope": "public" if name in skill_manager.public_skills else "private",
                }
            )

    return create_success_response(data={"skills": skills, "agent_id": agent_id})
