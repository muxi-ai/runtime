"""
Artifact read endpoints (Artifact Memory Phase 2, PRD "API Surface").

External read access to the user's stored artifacts for SDKs, the
Workspace file sidebar, and integrations:

- GET /artifacts                  list the user's latest artifacts
- GET /artifacts/{id}             one artifact's metadata + summary
- GET /artifacts/{id}/content     full content (decrypt + decompress),
                                  delivered as a standard streaming
                                  response (PRD open question 3)
- GET /artifacts/{id}/versions    the version chain

All endpoints are user-scoped: X-Muxi-User-ID is required and every read
goes through the same request middleware + RBAC pipeline as the memory
routes, so an identity rewrite or an RBAC denial applies here too. A
formation without artifact memory returns empty lists / 404s rather than
errors -- the read surface is inert, never broken.
"""

import re
from typing import Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .....datatypes.api import APIEventType, APIObjectType
from ...responses import APIResponse, create_error_response, create_success_response
from .memory import _get_user_id, _run_request_pipeline

router = APIRouter(tags=["Artifacts"])

# Streaming chunk size for content delivery (64 KiB).
CONTENT_CHUNK_BYTES = 64 * 1024

# Metadata keys exposed over the API (storage internals stay private).
_PUBLIC_FIELDS = (
    "public_id",
    "name",
    "version",
    "is_latest",
    "content_type",
    "category",
    "summary",
    "tags",
    "agent_id",
    "conversation_id",
    "size_bytes",
    "created_at",
    "updated_at",
    "last_accessed_at",
)


def _public_row(row: dict) -> dict:
    """Project one artifact row onto the public API shape."""
    data = {key: row.get(key) for key in _PUBLIC_FIELDS}
    data["id"] = data.pop("public_id")
    return data


def _content_disposition(name: str) -> str:
    """RFC 6266 Content-Disposition for an artifact name.

    Artifact names are agent-generated, so they are untrusted header
    input: control characters (CR/LF header injection), quotes, and
    backslashes are stripped from the quoted ASCII fallback, and the
    original name rides the ``filename*`` UTF-8 form fully
    percent-encoded (which cannot carry raw control bytes).
    """
    raw = str(name)
    ascii_fallback = re.sub(r"[^\x20-\x7e]", "_", raw).replace('"', "").replace("\\", "")
    if not ascii_fallback.strip():
        ascii_fallback = "artifact"
    encoded = quote(raw, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


async def _artifact_request_context(
    request: Request,
    x_user_id: Optional[str],
    endpoint: str,
) -> Tuple[Optional[object], Optional[str], Optional[str], Optional[JSONResponse]]:
    """Shared preamble: user id, service resolution, identity pipeline.

    Returns ``(service, user_id, request_id, error_response)``. ``service``
    is None (with no error) when artifact memory is not configured -- the
    caller decides between an empty list and a 404.
    """
    formation = request.app.state.formation
    request_id = getattr(request.state, "request_id", None)

    user_id, error_response = _get_user_id(x_user_id, request_id)
    if error_response:
        return None, None, request_id, error_response

    # Same identity pipeline as the memory reads (middleware may rewrite
    # the identity; RBAC may reject).
    user_id, _permissions, error_response = await _run_request_pipeline(
        formation, user_id, request_id, endpoint
    )
    if error_response:
        return None, None, request_id, error_response

    # Resolve the artifact memory service through the overlord, exactly
    # like the other client routes resolve their services: the overlord
    # is handed the service as ``artifact_memory`` at boot and is the
    # live serving-time attachment point (``formation._artifact_memory``
    # is an initialization-time detail, not the serving contract).
    overlord = getattr(formation, "_overlord", None)
    service = getattr(overlord, "artifact_memory", None) if overlord else None
    if service is not None and not getattr(service, "enabled", False):
        service = None
    return service, user_id, request_id, None


@router.get("/artifacts", response_model=APIResponse, operation_id="list_artifacts")
async def list_artifacts(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of artifacts to return"),
) -> JSONResponse:
    """
    List the user's artifacts (latest versions, most recently accessed
    first).
    """
    service, user_id, request_id, error_response = await _artifact_request_context(
        request, x_user_id, "/v1/artifacts"
    )
    if error_response:
        return error_response

    if service is None:
        response = create_success_response(
            APIObjectType.ARTIFACT_LIST,
            APIEventType.ARTIFACT_LIST,
            {"artifacts": [], "count": 0, "total": 0},
            request_id,
        )
        return JSONResponse(content=response.model_dump(), status_code=200)

    try:
        rows = await service.list_manifest(user_id, limit=limit)
        total = await service.count_artifacts(user_id)
        data = {
            "artifacts": [_public_row(row) for row in rows],
            "count": len(rows),
            "total": total,
        }
        response = create_success_response(
            APIObjectType.ARTIFACT_LIST, APIEventType.ARTIFACT_LIST, data, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=200)
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to list artifacts: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)


@router.get(
    "/artifacts/{artifact_id}", response_model=APIResponse, operation_id="get_artifact_metadata"
)
async def get_artifact_metadata(
    request: Request,
    artifact_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """Get one artifact's metadata and summary."""
    service, user_id, request_id, error_response = await _artifact_request_context(
        request, x_user_id, "/v1/artifacts/{id}"
    )
    if error_response:
        return error_response

    row = None
    if service is not None:
        try:
            row = await service.get_metadata(user_id, artifact_id)
        except Exception as e:
            response = create_error_response(
                "INTERNAL_ERROR", f"Failed to retrieve artifact: {str(e)}", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    if row is None:
        response = create_error_response(
            "NOT_FOUND", f"Artifact '{artifact_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    response = create_success_response(
        APIObjectType.ARTIFACT, APIEventType.ARTIFACT_RETRIEVED, _public_row(row), request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)


# operation_id deliberately differs from the built-in get_artifact_content
# tool so the MCP-exposed API tool namespace cannot shadow the built-in.
@router.get("/artifacts/{artifact_id}/content", operation_id="download_artifact_content")
async def download_artifact_content(
    request: Request,
    artifact_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
    version: Optional[int] = Query(None, ge=1, description="Specific version (default: the id)"),
):
    """
    Get one artifact's full content (decrypted and decompressed),
    streamed with the artifact's own content type.
    """
    service, user_id, request_id, error_response = await _artifact_request_context(
        request, x_user_id, "/v1/artifacts/{id}/content"
    )
    if error_response:
        return error_response

    row = None
    if service is not None:
        try:
            row = await service.resolve_version(user_id, artifact_id, version)
        except Exception as e:
            response = create_error_response(
                "INTERNAL_ERROR", f"Failed to resolve artifact: {str(e)}", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    if row is None:
        response = create_error_response(
            "NOT_FOUND", f"Artifact '{artifact_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    try:
        # read_content verifies the checksum and refreshes last_accessed_at
        # (and the last_accessed retention expiry) on the exact version read.
        #
        # KNOWN LIMITATION: read_content buffers the whole decrypted
        # payload in memory (decrypt + gunzip are whole-blob operations
        # in the Phase 1 pipeline), so the chunked response below bounds
        # CLIENT delivery, not server memory. Peak server usage is
        # ~one decoded artifact per in-flight download, capped by
        # artifacts.max_size_mb (default 50MB). A storage-level streaming
        # read (chunked AES-GCM framing) is the future fix when the
        # retrieval platform lands.
        content = await service.read_content(user_id, row["public_id"])
    except Exception as e:
        response = create_error_response(
            "INTERNAL_ERROR", f"Failed to read artifact content: {str(e)}", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=500)

    def _iter_chunks():
        for offset in range(0, len(content), CONTENT_CHUNK_BYTES):
            end = offset + CONTENT_CHUNK_BYTES
            yield content[offset:end]

    return StreamingResponse(
        _iter_chunks(),
        media_type=row["content_type"],
        headers={
            "Content-Disposition": _content_disposition(row["name"]),
            "Content-Length": str(len(content)),
            "X-Muxi-Artifact-Id": row["public_id"],
            "X-Muxi-Artifact-Version": str(row["version"]),
        },
    )


@router.get(
    "/artifacts/{artifact_id}/versions",
    response_model=APIResponse,
    operation_id="get_artifact_versions",
)
async def get_artifact_versions(
    request: Request,
    artifact_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-Muxi-User-ID"),
) -> JSONResponse:
    """Get one artifact's version history (newest version first)."""
    service, user_id, request_id, error_response = await _artifact_request_context(
        request, x_user_id, "/v1/artifacts/{id}/versions"
    )
    if error_response:
        return error_response

    chain = []
    if service is not None:
        try:
            chain = await service.get_history(user_id, artifact_id)
        except Exception as e:
            response = create_error_response(
                "INTERNAL_ERROR", f"Failed to retrieve versions: {str(e)}", None, request_id
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    if not chain:
        response = create_error_response(
            "NOT_FOUND", f"Artifact '{artifact_id}' not found", None, request_id
        )
        return JSONResponse(content=response.model_dump(), status_code=404)

    data = {
        "name": chain[0]["name"],
        "versions": [_public_row(row) for row in chain],
        "count": len(chain),
    }
    response = create_success_response(
        APIObjectType.ARTIFACT, APIEventType.ARTIFACT_VERSIONS_RETRIEVED, data, request_id
    )
    return JSONResponse(content=response.model_dump(), status_code=200)
