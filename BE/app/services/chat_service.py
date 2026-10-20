"""Evidence-backed Q&A over a deal's data room (RAG with Gemini, streamed over SSE)."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm
from app.ai.prompts import CHAT_SYSTEM_PROMPT, QUERY_REWRITE_PROMPT, chat_user_prompt
from app.ai.retrieval import hybrid_search, to_citation
from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.db.session import SessionLocal
from app.models import Conversation, Deal, Message, User
from app.models.enums import MessageRole
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatRequest, MessageRead
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

_CITATION_MARK = re.compile(r"\[(\d{1,2})\]")


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ConversationRepository(session)

    async def list_conversations(self, deal: Deal, user: User) -> list[Conversation]:
        return list(await self.repo.list_for_user(deal.id, user.id))

    async def create_conversation(self, deal: Deal, user: User, title: str | None) -> Conversation:
        conversation = await self.repo.add(
            Conversation(deal_id=deal.id, user_id=user.id, title=(title or "New conversation").strip()[:200])
        )
        await self.session.commit()
        return conversation

    async def get_conversation(self, deal: Deal, user: User, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.repo.get_owned(conversation_id, deal.id, user.id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    async def rename(self, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title.strip()[:200]
        await self.session.commit()
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self.repo.delete(conversation)
        await self.session.commit()

    async def messages(self, conversation: Conversation) -> list[Message]:
        return list(await self.repo.messages(conversation.id))

    async def set_feedback(self, conversation: Conversation, message_id: uuid.UUID, feedback: int) -> Message:
        message = await self.repo.get_message(message_id, conversation.id)
        if message is None or message.role != MessageRole.ASSISTANT:
            raise NotFoundError("Message not found.")
        message.feedback = feedback or None
        await self.session.commit()
        return message


async def _standalone_query(question: str, history: list[Message]) -> str:
    if not history or not settings.llm_configured:
        return question
    transcript = "\n".join(f"{m.role.value}: {m.content[:600]}" for m in history[-4:])
    try:
        rewritten = await llm.generate_text(
            QUERY_REWRITE_PROMPT.format(history=transcript, question=question), temperature=0.0, max_tokens=200
        )
        rewritten = rewritten.strip().strip('"').splitlines()[0] if rewritten.strip() else ""
        return rewritten if 3 <= len(rewritten) <= 500 else question
    except AppError:
        return question


async def stream_answer(
    *, deal_id: uuid.UUID, conversation_id: uuid.UUID, user_id: uuid.UUID, request: ChatRequest
) -> AsyncIterator[str]:
    """Server-Sent Events: `meta` (sources) -> many `token` -> `done` (persisted message) | `error`."""
    started = time.perf_counter()
    # The generator outlives the request scope, so it owns its own session.
    async with SessionLocal() as session:
        repo = ConversationRepository(session)
        deal = await session.get(Deal, deal_id)
        conversation = await repo.get_owned(conversation_id, deal_id, user_id)
        if deal is None or conversation is None:
            yield _sse("error", {"message": "Conversation not found."})
            return

        history = await repo.recent_messages(conversation.id, settings.chat_history_turns)
        user_message = await repo.add(Message(conversation_id=conversation.id, role=MessageRole.USER, content=request.question))
        if conversation.title == "New conversation":
            conversation.title = request.question[:80] + ("…" if len(request.question) > 80 else "")
        await session.commit()

        try:
            search_query = await _standalone_query(request.question, history)
            retrieval = await hybrid_search(
                session,
                deal_id=deal.id,
                query=search_query,
                categories=request.scope.categories or None,
                document_ids=request.scope.document_ids or None,
                top_k=request.top_k,
            )
            await session.commit()  # end the read transaction (SET LOCAL scope)
            citations = [to_citation(i, chunk) for i, chunk in enumerate(retrieval.chunks, start=1)]
            yield _sse("meta", {
                "user_message_id": str(user_message.id),
                "conversation_title": conversation.title,
                "search_query": search_query,
                "citations": citations,
            })

            contents = llm.to_contents(
                [(m.role.value, m.content) for m in history],
                chat_user_prompt(request.question, retrieval.chunks, deal),
            )
            answer_parts: list[str] = []
            async for token in llm.stream_text(contents, system=CHAT_SYSTEM_PROMPT):
                answer_parts.append(token)
                yield _sse("token", {"text": token})

            answer = "".join(answer_parts).strip() or "I could not generate an answer. Please try rephrasing the question."
            cited = {int(n) for n in _CITATION_MARK.findall(answer)}
            for citation in citations:
                citation["cited"] = citation["index"] in cited

            assistant = await repo.add(
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=answer,
                    citations=citations,
                    retrieval_meta={
                        "search_query": search_query,
                        "scope": request.scope.model_dump(mode="json"),
                        "timings_ms": retrieval.timings_ms,
                        "retrieved": len(citations),
                        "cited": sorted(cited),
                    },
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            await AuditService(session).log(
                action="chat.question", entity_type="conversation", entity_id=conversation.id, deal_id=deal.id,
                user_id=user_id, summary=f"Asked: {request.question[:200]}",
            )
            await session.commit()
            await session.refresh(assistant)
            yield _sse("done", MessageRead.model_validate(assistant).model_dump(mode="json"))
        except AppError as exc:
            await session.rollback()
            yield _sse("error", {"message": exc.message})
        except Exception:  # noqa: BLE001
            logger.exception("Chat stream failed")
            await session.rollback()
            yield _sse("error", {"message": "Something went wrong while generating the answer."})
