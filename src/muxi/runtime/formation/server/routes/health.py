"""
Health check and status endpoints.

These endpoints provide basic server health information
and formation status without requiring authentication.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ....services import observability

router = APIRouter(tags=["Health"])


def _check_formation_health(formation) -> bool:
    """
    Check if the formation is healthy.

    Args:
        formation: The formation instance to check

    Returns:
        bool: True if formation is healthy, False otherwise
    """
    try:
        # Check if formation is loaded
        if not hasattr(formation, "config") or formation.config is None:
            return False
        return True
    except Exception as e:
        # Log the exception for debugging
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            data={
                "error": str(e),
                "error_type": type(e).__name__,
                "function": "_check_formation_health",
            },
            description=f"Error checking formation health: {str(e)}",
        )
        return False


@router.get("/")
async def root_status(request: Request) -> HTMLResponse:
    """
    Root endpoint that returns an HTML status page.

    Returns:
        HTML page showing server status (Up/Down)
    """
    # Check if the formation is healthy
    formation = request.app.state.formation
    is_healthy = _check_formation_health(formation)

    # Determine status, color, and status code
    if is_healthy:
        status = "Up"
        color = "green"
        status_code = 200
    else:
        status = "Down"
        color = "red"
        status_code = 503

    # Generate HTML response
    html_content = f"""<!DOCTYPE html>
<html style="margin:0; padding:0; height:100%; color:white">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>{status}</title>
</head>
<body style="margin:0; padding:0; height:100%; color:white">
<table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td align="center" bgcolor="{color}">{status}</td></tr>
</table>
</body>
</html>"""

    return HTMLResponse(content=html_content, status_code=status_code)


@router.get("/v1")
async def v1_status(request: Request) -> HTMLResponse:
    """
    v1 endpoint that returns the same HTML status page as root.

    Returns:
        HTML page showing server status (Up/Down)
    """
    # Reuse the same logic as root_status
    return await root_status(request)


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """
    Basic health check endpoint.

    Returns:
        Simple health response per API spec (not wrapped in envelope)
    """
    import time

    formation = request.app.state.formation

    # Check if the formation is healthy
    is_healthy = _check_formation_health(formation)

    # Get uptime
    server = getattr(formation, '_server', None)
    uptime_seconds = 0
    if server and hasattr(server, '_start_time'):
        uptime_seconds = int(time.time() - server._start_time)

    # Build simple health response per spec
    health_data = {
        "status": "healthy" if is_healthy else "unhealthy",
        "version": (
            formation.config.get("version", "1.0.0")
            if is_healthy and hasattr(formation, "config") and isinstance(formation.config, dict)
            else "1.0.0"
        ),
        "uptime_seconds": uptime_seconds,
    }

    status_code = 200 if is_healthy else 503
    return JSONResponse(content=health_data, status_code=status_code)
