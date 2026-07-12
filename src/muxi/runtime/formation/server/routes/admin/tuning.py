"""
Self-improvement (tuning) endpoints.

The MUXI.md file-pair API surface (Self-Improving Formation PRD, Phase 1
slice) plus the manual loop trigger, requiring admin API key auth:

- ``GET /tuning`` -- the live MUXI.md (the formation's CLAUDE.md).
- ``POST /tuning`` -- replace the live file (human upload; hand-editing
  the file on disk is equally legitimate -- the mtime-cached handle
  re-reads either way).
- ``POST /tuning/run`` -- trigger one tuning loop pass (admin/testing).

The pending-suggestion surface (auto_apply: false review flow):

- ``GET /tuning/pending`` -- the tuner's suggested next version of the
  live file (PENDING-MUXI.md), null when none exists.
- ``PATCH /tuning/pending`` -- accept: promote pending to live.
- ``DELETE /tuning/pending`` -- dismiss: discard the suggestion; its
  learnings are content-hashed away and never re-proposed.

Partial acceptance = edit the pending content and POST it as live.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .....datatypes.api import APIEventType, APIObjectType
from .....services.tuning.muxi_md import MUXI_MD_MAX_BYTES
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

    content_bytes = len(update.content.encode("utf-8"))
    if content_bytes > MUXI_MD_MAX_BYTES:
        response = create_error_response(
            "TUNING_CONTENT_TOO_LARGE",
            f"MUXI.md content is {content_bytes} bytes; the bound is "
            f"{MUXI_MD_MAX_BYTES} bytes (it is injected into every turn)",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=413)

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


def _tuning_service(request: Request):
    """The overlord's tuning service, or None when tuning is inactive."""
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    return getattr(overlord, "tuning_service", None) if overlord else None


@router.get("/tuning/pending", response_model=APIResponse)
async def get_tuning_pending(request: Request) -> JSONResponse:
    """Get the pending MUXI.md suggestion (null when none exists)."""
    request_id = getattr(request.state, "request_id", None)
    muxi_md = _muxi_md(request)
    if muxi_md is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Overlord not started", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    response = create_success_response(
        APIObjectType.TUNING,
        APIEventType.TUNING_PENDING_RETRIEVED,
        {"content": muxi_md.read_pending(), "path": muxi_md.pending_path()},
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.patch("/tuning/pending", response_model=APIResponse)
async def apply_tuning_pending(request: Request) -> JSONResponse:
    """Accept the pending suggestion: promote it to the live MUXI.md."""
    request_id = getattr(request.state, "request_id", None)
    tuning_service = _tuning_service(request)
    if tuning_service is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Tuning is not active for this formation", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        result = tuning_service.apply_pending()
    except ValueError as e:
        response = create_error_response("TUNING_NO_PENDING", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=404)
    except OSError as e:
        response = create_error_response(
            "TUNING_WRITE_FAILED", f"Could not apply the suggestion: {e}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    response = create_success_response(
        APIObjectType.TUNING, APIEventType.TUNING_PENDING_APPLIED, result, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.delete("/tuning/pending", response_model=APIResponse)
async def dismiss_tuning_pending(request: Request) -> JSONResponse:
    """Dismiss the pending suggestion; its ideas are never re-proposed."""
    request_id = getattr(request.state, "request_id", None)
    tuning_service = _tuning_service(request)
    if tuning_service is None:
        response = create_error_response(
            "SERVICE_UNAVAILABLE", "Tuning is not active for this formation", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        result = tuning_service.dismiss_pending()
    except ValueError as e:
        response = create_error_response("TUNING_NO_PENDING", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.TUNING, APIEventType.TUNING_PENDING_DISMISSED, result, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


@router.post("/tuning/run", response_model=APIResponse)
async def run_tuning(request: Request) -> JSONResponse:
    """Trigger one tuning loop pass now (admin/testing surface)."""
    request_id = getattr(request.state, "request_id", None)
    formation = request.app.state.formation
    overlord = getattr(formation, "_overlord", None)
    tuning_service = _tuning_service(request)
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
