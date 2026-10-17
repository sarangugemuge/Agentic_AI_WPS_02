"""
System routes — Health check, version info, and service status.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class VersionResponse(BaseModel):
    api_version: str
    phase: str
    service: str
    test_doubles_active: bool


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check backend operational status. Used by frontend and monitoring probes.",
)
async def health_check():
    """Health check endpoint returning 200 OK when service is operational."""
    return HealthResponse(
        status="ok",
        service="skillsync-api",
        version="0.1.0",
        environment=settings.app_env,
    )


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Version info",
    description="Returns current API version, active phase, and test double status.",
)
async def get_version():
    """Return API version, phase, and test double mode."""
    return VersionResponse(
        api_version="0.1.0",
        phase="Phase 3 — Backend API",
        service="skillsync-api",
        test_doubles_active=settings.use_test_doubles,
    )
