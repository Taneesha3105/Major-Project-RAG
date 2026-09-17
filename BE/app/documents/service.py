from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.documents.schemas import (
    DocumentChunkPreview,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSummary,
)

logger = logging.getLogger(__name__)


class DocumentManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chunk_preview_limit = 3
        self.chunk_preview_length = 240

    async def list_documents(self) -> DocumentListResponse:
        rows = await self._fetch_document_summary_rows()
        metadata_by_document_id = await self._fetch_document_metadata_map(
            [row.id for row in rows],
        )

        documents = [
            self._build_document_summary(row=row, metadata=metadata_by_document_id.get(row.id))
            for row in rows
        ]
        return DocumentListResponse(total_count=len(documents), documents=documents)

    async def get_document_detail(self, document_id: int) -> DocumentDetailResponse:
        row = await self._fetch_single_document_summary_row(document_id)
        if row is None:
            raise LookupError("Document not found.")

        metadata = await self._fetch_first_chunk_metadata(document_id)
        chunk_previews = await self._fetch_chunk_previews(document_id)
        summary = self._build_document_summary(row=row, metadata=metadata)

        return DocumentDetailResponse(
            **summary.model_dump(),
            content_hash=row.content_hash,
            chunk_previews=chunk_previews,
        )

    async def delete_document(self, document_id: int) -> DocumentDeleteResponse:
        row = await self._fetch_single_document_summary_row(document_id)
        if row is None:
            raise LookupError("Document not found.")

        document = await self.session.get(Document, document_id)
        if document is None:
            raise LookupError("Document not found.")

        await self.session.delete(document)
        await self.session.commit()
        logger.info("Deleted document %s and its related chunks.", document_id)

        return DocumentDeleteResponse(
            id=row.id,
            filename=row.filename,
            deleted_chunk_count=int(row.chunk_count),
            message="Document deleted successfully.",
        )

    async def _fetch_document_summary_rows(self) -> Sequence:
        statement = (
            select(
                Document.id.label("id"),
                Document.filename.label("filename"),
                Document.content_hash.label("content_hash"),
                Document.created_at.label("created_at"),
                Document.updated_at.label("updated_at"),
                func.count(Chunk.id).label("chunk_count"),
                func.count(Chunk.embedding).label("embedded_chunk_count"),
            )
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .group_by(
                Document.id,
                Document.filename,
                Document.content_hash,
                Document.created_at,
                Document.updated_at,
            )
            .order_by(Document.created_at.desc(), Document.id.desc())
        )
        result = await self.session.execute(statement)
        return result.all()

    async def _fetch_single_document_summary_row(self, document_id: int):
        statement = (
            select(
                Document.id.label("id"),
                Document.filename.label("filename"),
                Document.content_hash.label("content_hash"),
                Document.created_at.label("created_at"),
                Document.updated_at.label("updated_at"),
                func.count(Chunk.id).label("chunk_count"),
                func.count(Chunk.embedding).label("embedded_chunk_count"),
            )
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .where(Document.id == document_id)
            .group_by(
                Document.id,
                Document.filename,
                Document.content_hash,
                Document.created_at,
                Document.updated_at,
            )
        )
        result = await self.session.execute(statement)
        return result.one_or_none()

    async def _fetch_document_metadata_map(
        self,
        document_ids: list[int],
    ) -> dict[int, dict[str, object]]:
        if not document_ids:
            return {}

        statement = (
            select(Chunk.document_id, Chunk.chunk_metadata)
            .where(Chunk.document_id.in_(document_ids))
            .distinct(Chunk.document_id)
            .order_by(Chunk.document_id, Chunk.chunk_index)
        )
        result = await self.session.execute(statement)
        return {
            int(document_id): dict(chunk_metadata or {})
            for document_id, chunk_metadata in result.all()
        }

    async def _fetch_first_chunk_metadata(self, document_id: int) -> dict[str, object]:
        statement = (
            select(Chunk.chunk_metadata)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
            .limit(1)
        )
        result = await self.session.execute(statement)
        metadata = result.scalar_one_or_none()
        return dict(metadata or {})

    async def _fetch_chunk_previews(self, document_id: int) -> list[DocumentChunkPreview]:
        statement = (
            select(
                Chunk.id,
                Chunk.chunk_index,
                Chunk.chunk_text,
                Chunk.created_at,
            )
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
            .limit(self.chunk_preview_limit)
        )
        result = await self.session.execute(statement)
        rows = result.all()

        previews = []
        for row in rows:
            chunk_text = row.chunk_text.strip()
            preview = chunk_text[: self.chunk_preview_length]
            if len(chunk_text) > self.chunk_preview_length:
                preview = f"{preview.rstrip()}..."

            previews.append(
                DocumentChunkPreview(
                    id=row.id,
                    chunk_index=row.chunk_index,
                    created_at=row.created_at,
                    preview_text=preview,
                    character_count=len(chunk_text),
                )
            )

        return previews

    @staticmethod
    def _build_document_summary(row, metadata: dict[str, object] | None) -> DocumentSummary:
        metadata = metadata or {}
        embedded_chunk_count = int(row.embedded_chunk_count or 0)

        return DocumentSummary(
            id=row.id,
            filename=row.filename,
            created_at=row.created_at,
            updated_at=row.updated_at,
            chunk_count=int(row.chunk_count or 0),
            embedded_chunk_count=embedded_chunk_count,
            has_embeddings=embedded_chunk_count > 0,
            source_type=DocumentManagementService._read_string_metadata(metadata, "source_type"),
            source_format=DocumentManagementService._read_string_metadata(metadata, "source_format"),
            parser_name=DocumentManagementService._read_string_metadata(metadata, "parser_name"),
            embedding_provider=DocumentManagementService._read_string_metadata(
                metadata,
                "embedding_provider",
            ),
            embedding_model=DocumentManagementService._read_string_metadata(
                metadata,
                "embedding_model",
            ),
            embedding_dimensions=DocumentManagementService._read_int_metadata(
                metadata,
                "embedding_dimensions",
            ),
        )

    @staticmethod
    def _read_string_metadata(metadata: dict[str, object], key: str) -> str | None:
        value = metadata.get(key)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _read_int_metadata(metadata: dict[str, object], key: str) -> int | None:
        value = metadata.get(key)
        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None
