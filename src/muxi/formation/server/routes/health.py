"""
Health check and status endpoints.

These endpoints provide basic server health information
and formation status without requiring authentication.
"""

from typing import Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Health"])


@router.get("/")
async def root_status(request: Request) -> HTMLResponse:
    """
    Root endpoint that returns an HTML status page.

    Returns:
        HTML page showing server status (Up/Down)
    """
    # Check if the formation is healthy
    formation = request.app.state.formation
    is_healthy = True

    # Basic health checks
    try:
        # Check if formation is loaded
        if not hasattr(formation, 'config') or formation.config is None:
            is_healthy = False
    except Exception:
        is_healthy = False

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
    html_content = (
        "<!DOCTYPE html>",
        '<html style="margin:0; padding:0; height:100%; color:white">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width">',
        f'<title>{status}</title>',
        "</head>",
        '<body style="margin:0; padding:0; height:100%; color:white">',
        '<table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0">',
        f'<tr><td align="center" bgcolor="{color}">{status}</td></tr>',
        "</table>",
        "</body>",
        "</html>",
    )

    return HTMLResponse(content=html_content, status_code=status_code)


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint.

    Returns:
        Simple health status
    """
    return {"status": "healthy"}
