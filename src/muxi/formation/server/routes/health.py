"""
Health check and status endpoints.

These endpoints provide basic server health information
and formation status without requiring authentication.
"""

from typing import Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ....utils.version import get_version

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint.

    Returns:
        Simple health status
    """
    return {"status": "healthy"}
