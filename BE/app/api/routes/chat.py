import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.provider import ProviderRequestError
from app.chat.schemas import ChatRequest, ChatResponse
from app.chat.service import ChatService
from app.db.session import get_db_session

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post(
    "/ask",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def ask_question(
    payload: ChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    service = ChatService(session, reranker=request.app.state.chat_reranker)

    try:
        return await service.ask(payload)
    except ProviderRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while answering chat question.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while generating the answer.",
        ) from exc


@router.post("/stream", status_code=status.HTTP_200_OK)
async def stream_answer(
    payload: ChatRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    service = ChatService(session, reranker=request.app.state.chat_reranker)

    try:
        prepared_chat = await service.prepare_chat(payload)
    except ProviderRequestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while preparing streaming chat response.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while starting the stream.",
        ) from exc

    return StreamingResponse(
        service.stream_prepared(prepared_chat),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
