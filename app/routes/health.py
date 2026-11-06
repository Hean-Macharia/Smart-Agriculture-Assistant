from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.database import check_mongo_connection

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Liveness check",
    description="No authentication required. Confirms that the API process is responding.",
)
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@router.get(
    "/health/ready",
    summary="MongoDB readiness check",
    description="No authentication required. Pings MongoDB; returns 503 if the configured database is unavailable.",
    responses={503: {"description": "MongoDB did not respond to the readiness ping."}},
)
def readiness() -> dict[str, str]:
    if not check_mongo_connection():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        )
    return {"status": "ready", "database": "connected"}
