from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.readiness import readiness_state

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    snapshot = readiness_state.snapshot()
    payload = {
        "status": snapshot.status,
        "checks": {
            "database": "ready" if snapshot.database_ready else "starting",
            "embedding": snapshot.embedding_state,
        },
        "embedding_runtime": snapshot.embedding_runtime,
        "message": snapshot.message,
    }
    response_status = status.HTTP_200_OK if snapshot.status == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=response_status, content=payload)
