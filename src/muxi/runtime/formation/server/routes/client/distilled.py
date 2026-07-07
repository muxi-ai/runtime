"""
Distilled memory intake endpoints (Memory Distillery Phase 3b).

POST /v1/memories/distilled accepts SIGNED batches of pre-distilled memory
events from a registered on-premises distillery. Authentication is layered:

1. API key (this router is mounted with the dual-key dependency, so a
   valid client or admin key is required, mirroring the PRD's formation
   API key).
2. Ed25519 batch signature over the RAW request body, bound to the
   X-Distillery-ID and X-Distillery-Timestamp headers and checked against
   the registered distillery's public key -- fail-closed, with replay
   protection (signature_max_age_seconds window).

The handler reads the raw body itself (no pydantic body model) because the
signature covers the exact bytes on the wire; parsing happens only after
authentication succeeds.

Error semantics (PRD "Authentication & Trust Model"):
- Missing/invalid headers, unknown distillery, stale timestamp, or a bad
  signature -> 401 (one indistinct message; an observability alert fires).
- Revoked distillery -> 410 Gone.
- Daily quota exceeded -> 429.
- Malformed envelope -> 400/422 with a precise message.
- Per-event problems are NEVER endpoint errors: partial acceptance returns
  indexed rejection reasons alongside the accepted count.
"""

import secrets
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .....datatypes.api import APIEventType, APIObjectType
from .....services.memory.distillery import (
    DistilleryAuthError,
    DistilleryRateLimitError,
    DistilleryRevokedError,
    DistilleryUnavailableError,
)
from .....utils.fastjson import json
from ....background.request_tracker import RequestStatus
from ...responses import APIResponse, create_error_response, create_success_response
from ...utils import distillery_service_or_error

router = APIRouter(tags=["Memory"])

# RequestTracker statuses -> the status vocabulary distilleries see
# (identical mapping to the ingestion status endpoint).
_DISTILLED_STATUS_MAP = {
    RequestStatus.PENDING: "queued",
    RequestStatus.PROCESSING: "processing",
    RequestStatus.RUNNING: "processing",
    RequestStatus.AWAITING_CLARIFICATION: "processing",
    RequestStatus.COMPLETED: "completed",
    RequestStatus.FAILED: "failed",
    RequestStatus.CANCELLED: "failed",
}


@router.post(
    "/memories/distilled", response_model=APIResponse, operation_id="ingest_distilled_memories"
)
async def ingest_distilled_memories(request: Request) -> JSONResponse:
    """
    Accept one signed batch of pre-distilled memory events.

    Headers: X-Distillery-ID, X-Distillery-Signature (base64 Ed25519 over
    the raw body bound to id + timestamp), X-Distillery-Timestamp (unix
    seconds). Body: the distilled batch contract (batch_id, embedding_mode,
    events[]).

    Valid events are appended to the memory event substrate immediately
    (idempotent on (source="distillery", source_id); retries never
    duplicate). Projections + embeddings run in a background job pollable
    at GET /v1/memories/distilled/{processing_id}.
    """
    request_id = getattr(request.state, "request_id", None)

    service, error_response = distillery_service_or_error(request, request_id)
    if error_response:
        return error_response

    body = await request.body()
    try:
        distillery = await service.authenticate(
            request.headers.get("X-Distillery-ID"),
            request.headers.get("X-Distillery-Signature"),
            request.headers.get("X-Distillery-Timestamp"),
            body,
        )
    except DistilleryAuthError as e:
        response = create_error_response("UNAUTHORIZED", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=401)
    except DistilleryRevokedError as e:
        response = create_error_response("GONE", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=410)
    except DistilleryUnavailableError as e:
        response = create_error_response("SERVICE_UNAVAILABLE", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=503)

    try:
        batch = json.loads(body)
    except Exception:
        response = create_error_response(
            "INVALID_REQUEST", "Request body is not valid JSON", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=400)

    meta, error_message = service.validate_batch(batch, distillery)
    if error_message:
        response = create_error_response("INVALID_PARAMS", error_message, None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=422)

    try:
        outcome = await service.submit(distillery, meta)
    except DistilleryRateLimitError as e:
        response = create_error_response("RATE_LIMITED", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=429)
    except DistilleryUnavailableError as e:
        response = create_error_response("SERVICE_UNAVAILABLE", str(e), None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=503)
    except Exception as e:
        # Unexpected accept-path failure: appended events are idempotent,
        # so a full-batch retry is always safe.
        response = create_error_response(
            "INTERNAL_ERROR",
            f"Failed to accept distilled batch: {str(e)}",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    if outcome["processing_id"]:
        outcome["status_url"] = f"/v1/memories/distilled/{outcome['processing_id']}"
    response = create_success_response(
        APIObjectType.MEMORY_DISTILLATION,
        APIEventType.MEMORY_DISTILLED_ACCEPTED,
        outcome,
        request_id,
    )
    status_code = 202 if outcome["accepted"] else 200
    return JSONResponse(content=response.model_dump(), status_code=status_code)


@router.get(
    "/memories/distilled/{processing_id}",
    response_model=APIResponse,
    operation_id="get_distilled_status",
)
async def get_distilled_status(request: Request, processing_id: str) -> JSONResponse:
    """
    Poll a distilled batch's projection job.

    Status lifecycle: queued -> processing -> completed | failed.
    Completed jobs report per-event dispositions (projected / recorded /
    failed) and whether shipped pre-computed vectors were used. Results
    are retained for a short TTL after completion.

    Ownership: with AdminKey any job is visible; with ClientKey the
    X-Distillery-ID header must match the distillery that submitted the
    batch (the job belongs to the distillery principal, not a user).
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    service, error_response = distillery_service_or_error(request, request_id)
    if error_response:
        return error_response

    overlord = getattr(formation, "_overlord", None)
    state = await overlord.request_tracker.get_request(processing_id)
    if state is None:
        response = create_error_response(
            "NOT_FOUND",
            f"Unknown or expired processing_id '{processing_id}' "
            "(completed results are retained for 5 minutes)",
            None,
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    # Ownership check: admin key sees everything; otherwise the caller
    # must present the submitting distillery's id. Uses the same header
    # comparison as the memory routes' admin detection.
    api_keys = getattr(formation, "_api_keys", {})
    admin_key = api_keys.get("admin", "")
    provided_admin_key = request.headers.get("x-muxi-admin-key")
    is_admin = bool(
        provided_admin_key and admin_key and secrets.compare_digest(provided_admin_key, admin_key)
    )
    distillery_id = (request.headers.get("X-Distillery-ID") or "").strip()
    if not is_admin and state.user_id != f"distillery:{distillery_id}":
        response = create_error_response(
            "FORBIDDEN", "Processing job does not belong to this distillery", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=403)

    data: Dict[str, Any] = {
        "processing_id": processing_id,
        "status": _DISTILLED_STATUS_MAP.get(state.status, state.status.value),
        "created_at": state.get_created_timestamp(),
    }
    if state.end_time:
        data["completed_at"] = state.end_time
    if state.error:
        data["error"] = state.error
    if isinstance(state.result, dict):
        data.update(state.result)

    response = create_success_response(
        APIObjectType.MEMORY_DISTILLATION,
        APIEventType.MEMORY_DISTILLED_STATUS,
        data,
        request_id,
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
