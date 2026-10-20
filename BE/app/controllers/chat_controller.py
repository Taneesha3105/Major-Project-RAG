import uuid

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse

from app.ai.retrieval import hybrid_search
from app.controllers.deps import DealCtx, SessionDep
from app.core.exceptions import ServiceUnavailableError
from app.core.config import settings
from app.core.permissions import Permission
from app.models import Conversation, Message
from app.schemas.chat import (
    ChatRequest,
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageFeedback,
    MessageRead,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.services.chat_service import ChatService, stream_answer

router = APIRouter(prefix="/deals/{deal_id}", tags=["AI Assistant"])


@router.get("/conversations", response_model=list[ConversationRead])
async def list_conversations(ctx: DealCtx, session: SessionDep) -> list[Conversation]:
    return await ChatService(session).list_conversations(ctx.deal, ctx.user)


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate, ctx: DealCtx, session: SessionDep) -> Conversation:
    ctx.require(Permission.CHAT)
    return await ChatService(session).create_conversation(ctx.deal, ctx.user, payload.title)


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
async def rename_conversation(
    conversation_id: uuid.UUID, payload: ConversationUpdate, ctx: DealCtx, session: SessionDep
) -> Conversation:
    service = ChatService(session)
    conversation = await service.get_conversation(ctx.deal, ctx.user, conversation_id)
    return await service.rename(conversation, payload.title)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> Response:
    service = ChatService(session)
    await service.delete(await service.get_conversation(ctx.deal, ctx.user, conversation_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(conversation_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> list[Message]:
    service = ChatService(session)
    return await service.messages(await service.get_conversation(ctx.deal, ctx.user, conversation_id))


@router.post("/conversations/{conversation_id}/messages")
async def ask(conversation_id: uuid.UUID, payload: ChatRequest, ctx: DealCtx, session: SessionDep) -> StreamingResponse:
    """Streams the grounded answer as Server-Sent Events (meta, token..., done | error)."""
    ctx.require(Permission.CHAT)
    if not settings.llm_configured:
        raise ServiceUnavailableError("The AI assistant requires GEMINI_API_KEY to be configured on the server.")
    await ChatService(session).get_conversation(ctx.deal, ctx.user, conversation_id)
    return StreamingResponse(
        stream_answer(deal_id=ctx.deal.id, conversation_id=conversation_id, user_id=ctx.user.id, request=payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback", response_model=MessageRead)
async def message_feedback(
    conversation_id: uuid.UUID, message_id: uuid.UUID, payload: MessageFeedback, ctx: DealCtx, session: SessionDep
) -> Message:
    service = ChatService(session)
    conversation = await service.get_conversation(ctx.deal, ctx.user, conversation_id)
    return await service.set_feedback(conversation, message_id, payload.feedback)


@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest, ctx: DealCtx, session: SessionDep) -> SearchResponse:
    """Raw hybrid retrieval (no LLM) — evidence search across the data room."""
    result = await hybrid_search(
        session,
        deal_id=ctx.deal.id,
        query=payload.query,
        categories=payload.scope.categories or None,
        document_ids=payload.scope.document_ids or None,
        top_k=payload.top_k,
    )
    return SearchResponse(
        query=result.query,
        hits=[
            SearchHit(
                chunk_id=c.chunk_id, document_id=c.document_id, filename=c.filename, category=c.category,
                page_number=c.page_number, section=c.section, content=c.content, vector_score=c.vector_score,
                lexical_score=c.lexical_score, fused_score=c.fused_score, rerank_score=c.rerank_score,
            )
            for c in result.chunks
        ],
        timings_ms=result.timings_ms,
    )
