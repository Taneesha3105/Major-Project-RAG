import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.retrieval.schemas import RetrievalRequest, RetrievalResponse
from app.retrieval.service import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])
logger = logging.getLogger(__name__)


@router.post("/search", response_model=RetrievalResponse, status_code=status.HTTP_200_OK)
async def search_chunks(
    payload: RetrievalRequest,
    session: AsyncSession = Depends(get_db_session),
) -> RetrievalResponse:
    service = RetrievalService(session)

    try:
        return await service.search(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while searching chunks.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while retrieving chunks.",
        ) from exc
