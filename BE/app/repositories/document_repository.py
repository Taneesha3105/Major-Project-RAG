import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentChunk
from app.models.enums import DocumentCategory, DocumentStatus
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def list_for_deal(
        self,
        deal_id: uuid.UUID,
        *,
        category: DocumentCategory | None = None,
        status: DocumentStatus | None = None,
        search: str | None = None,
    ) -> Sequence[Document]:
        stmt = (
            select(Document)
            .where(Document.deal_id == deal_id)
            .options(selectinload(Document.uploaded_by))
            .order_by(Document.created_at.desc())
        )
        if category:
            stmt = stmt.where(Document.category == category)
        if status:
            stmt = stmt.where(Document.status == status)
        if search:
            stmt = stmt.where(func.lower(Document.filename).like(f"%{search.lower()}%"))
        return await self.list(stmt)

    async def get_in_deal(self, deal_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        return await self.session.scalar(
            select(Document)
            .where(Document.id == document_id, Document.deal_id == deal_id)
            .options(selectinload(Document.uploaded_by))
            .execution_options(populate_existing=True)
        )

    async def get_by_hash(self, deal_id: uuid.UUID, content_hash: str) -> Document | None:
        return await self.session.scalar(
            select(Document).where(Document.deal_id == deal_id, Document.content_hash == content_hash)
        )

    async def ids_with_status(self, statuses: tuple[DocumentStatus, ...]) -> list[uuid.UUID]:
        return list((await self.session.scalars(select(Document.id).where(Document.status.in_(statuses)))).all())

    async def mark_status(self, document_id: uuid.UUID, status: DocumentStatus, error: str | None = None) -> None:
        await self.session.execute(
            update(Document).where(Document.id == document_id).values(status=status, error_message=error)
        )

    async def categories_present(self, deal_id: uuid.UUID) -> dict[str, int]:
        rows = await self.session.execute(
            select(Document.category, func.count())
            .where(Document.deal_id == deal_id, Document.status == DocumentStatus.READY)
            .group_by(Document.category)
        )
        return {str(category): count for category, count in rows}

    async def ready_documents(self, deal_id: uuid.UUID) -> Sequence[Document]:
        return await self.list(
            select(Document).where(Document.deal_id == deal_id, Document.status == DocumentStatus.READY)
        )

    # --- chunks ---
    async def replace_chunks(self, document_id: uuid.UUID, chunks: list[DocumentChunk]) -> None:
        await self.session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        self.session.add_all(chunks)
        await self.session.flush()

    async def list_chunks(self, document_id: uuid.UUID, offset: int = 0, limit: int = 50) -> Sequence[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .offset(offset)
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()
