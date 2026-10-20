import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models import Conversation, Message
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def list_for_user(self, deal_id: uuid.UUID, user_id: uuid.UUID) -> Sequence[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.deal_id == deal_id, Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return await self.list(stmt)

    async def get_owned(self, conversation_id: uuid.UUID, deal_id: uuid.UUID, user_id: uuid.UUID) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.deal_id == deal_id,
                Conversation.user_id == user_id,
            )
        )

    async def messages(self, conversation_id: uuid.UUID) -> Sequence[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        return (await self.session.scalars(stmt)).all()

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        if limit <= 0:
            return []
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed((await self.session.scalars(stmt)).all()))

    async def get_message(self, message_id: uuid.UUID, conversation_id: uuid.UUID) -> Message | None:
        return await self.session.scalar(
            select(Message).where(Message.id == message_id, Message.conversation_id == conversation_id)
        )
