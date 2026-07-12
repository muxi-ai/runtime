"""
Self-improvement (tuning) endpoints.

The MUXI.md file-pair API surface (Self-Improving Formation PRD, Phase 1
slice) plus the manual loop trigger, requiring admin API key auth:

- ``GET /tuning`` -- the live MUXI.md (the formation's CLAUDE.md).
- ``POST /tuning`` -- replace the live file (human upload; hand-editing
  the file on disk is equally legitimate -- the mtime-cached handle
  re-reads either way).
- ``POST /tuning/run`` -- trigger one tuning loop pass (admin/testing).

The pending-file endpoints (``/tuning/pending``) arrive with Phase 2's
tuner step.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .....datatypes.api import APIEventType, APIObjectType
from ...responses import APIResponse, create_error_response, create_success_response

router = APIRouter(tags=["Tuning"])


class TuningUpdate(BaseModel):
    """Replacement content for the live MUXI.md."""

    content: str


def _muxi_md(request: Request):
    """The overlord's MUXI.md handle, or None before overlord start."""
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    return getattr(overlord, "muxi_md", None) if overlord else None


@router.get("/tuning", response_model=APIResponse)
async def get_tuning(request: Request) -> JSONResponse:
    """Get the live MUXI.md content (null when the file does not exist)."""
    request_id = getattr(request.state, "request_id", None)
    muxi_md = _muxi_md(request)
    if muxi_md is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord not started", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    response = create_success_response(
        APIObjectType.TUNING,
        APIEventType.TUNING_RETRIEVED,
        {"content": muxi_md.read(), "path": muxi_md.resolve_path()},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/tuning", response_model=APIResponse)
async def replace_tuning(request: Request, update: TuningUpdate) -> JSONResponse:
    """Replace the live MUXI.md with the posted content."""
    request_id = getattr(request.state, "request_id", None)
    muxi_md = _muxi_md(request)
    if muxi_md is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord not started", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        path = muxi_md.write(update.content)
    except (ValueError, OSError) as e:
        response = create_error_response(
            "TUNING_WRITE_FAILED", f"Could not write MUXI.md: {e}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    response = create_success_response(
        APIObjectType.TUNING,
        APIEventType.TUNING_UPDATED,
        {"path": path, "bytes": len(update.content.encode("utf-8"))},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/tuning/run", response_model=APIResponse)
async def run_tuning(request: Request) -> JSONResponse:
    """Trigger one tuning loop pass now (admin/testing surface)."""
    request_id = getattr(request.state, "request_id", None)
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    tuning_service = getattr(overlord, "tuning_service", None) if overlord else None
    if tuning_service is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE",
            "Tuning is not active for this formation",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    model = getattr(overlord, "extraction_model", None) or getattr(overlord, "default_model", None)
    result = await tuning_service.run_once(model, trigger="manual")

    response = create_success_response(
        APIObjectType.TUNING_RUN, APIEventType.TUNING_RUN_COMPLETED, result, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
