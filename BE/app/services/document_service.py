"""Data-room documents: upload, ingestion pipeline (extract -> OCR -> clean -> chunk -> embed) and insights."""

from __future__ import annotations

import logging
import mimetypes
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import embeddings, llm
from app.ai.prompts import DOCUMENT_INSIGHT_PROMPT
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.db.session import SessionLocal
from app.ingestion.chunker import chunk_blocks
from app.ingestion.cleaning import clean_blocks
from app.ingestion.extractors import SUPPORTED_EXTENSIONS, ExtractionError, extract
from app.models import Deal, Document, DocumentChunk, User
from app.models.enums import DocumentCategory, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentRead, DocumentUpdate, UploadResult
from app.services.audit_service import AuditService
from app.services.job_queue import ingestion_queue
from app.services.storage_service import sha256, storage

logger = logging.getLogger(__name__)


class _KeyFact(BaseModel):
    label: str = Field(description="Short label, e.g. 'FY2024 revenue'")
    value: str = Field(description="Value exactly as written in the document")


class _DocumentInsight(BaseModel):
    summary: str
    key_facts: list[_KeyFact] = Field(default_factory=list)


def to_read(document: Document) -> DocumentRead:
    uploader = document.__dict__.get("uploaded_by")  # only if eagerly loaded; avoids async lazy-load
    return DocumentRead.model_validate(document).model_copy(
        update={"uploaded_by_name": uploader.full_name if uploader else None}
    )


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DocumentRepository(session)
        self.audit = AuditService(session)

    async def list(self, deal: Deal, category: DocumentCategory | None, status: DocumentStatus | None,
                   search: str | None) -> list[DocumentRead]:
        return [to_read(doc) for doc in await self.repo.list_for_deal(deal.id, category=category, status=status, search=search)]

    async def get(self, deal: Deal, document_id: uuid.UUID) -> Document:
        document = await self.repo.get_in_deal(deal.id, document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    async def upload(
        self, user: User, deal: Deal, files: list[UploadFile], category: DocumentCategory, description: str | None
    ) -> UploadResult:
        if not files:
            raise ValidationFailedError("Select at least one file to upload.")
        max_bytes = settings.max_upload_mb * 1024 * 1024
        uploaded: list[Document] = []
        skipped: list[dict[str, str]] = []

        for upload in files:
            filename = Path(upload.filename or "document").name[:255]
            extension = Path(filename).suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                skipped.append({"filename": filename, "reason": f"Unsupported file type '{extension or 'unknown'}'."})
                continue
            data = await upload.read(max_bytes + 1)
            if len(data) > max_bytes:
                skipped.append({"filename": filename, "reason": f"File exceeds the {settings.max_upload_mb} MB limit."})
                continue
            if not data:
                skipped.append({"filename": filename, "reason": "File is empty."})
                continue
            content_hash = sha256(data)
            if duplicate := await self.repo.get_by_hash(deal.id, content_hash):
                skipped.append({"filename": filename, "reason": f"Duplicate of '{duplicate.filename}'."})
                continue

            document_id = uuid.uuid4()
            key = storage.build_key(deal.id, document_id, extension)
            await storage.save(key, data)
            document = await self.repo.add(
                Document(
                    id=document_id,
                    deal_id=deal.id,
                    uploaded_by_id=user.id,
                    filename=filename,
                    storage_key=key,
                    mime_type=upload.content_type or mimetypes.guess_type(filename)[0],
                    file_extension=extension,
                    file_size=len(data),
                    content_hash=content_hash,
                    category=category,
                    description=description,
                    status=DocumentStatus.QUEUED,
                )
            )
            uploaded.append(document)

        if uploaded:
            names = ", ".join(doc.filename for doc in uploaded[:3]) + ("…" if len(uploaded) > 3 else "")
            await self.audit.log(
                action="document.uploaded", entity_type="document", deal_id=deal.id, user=user,
                entity_id=uploaded[0].id if len(uploaded) == 1 else None,
                summary=f"{user.full_name} uploaded {len(uploaded)} {category.value} document(s): {names}",
                details={"document_ids": [str(doc.id) for doc in uploaded]},
            )
        await self.session.commit()
        for document in uploaded:
            enqueue_processing(document.id)

        return UploadResult(
            uploaded=[to_read(doc).model_copy(update={"uploaded_by_name": user.full_name}) for doc in uploaded],
            skipped=skipped,
        )

    async def update(self, user: User, deal: Deal, document_id: uuid.UUID, payload: DocumentUpdate) -> DocumentRead:
        document = await self.get(deal, document_id)
        self.repo.apply_updates(document, payload.model_dump(exclude_unset=True, exclude_none=True))
        await self.audit.log(action="document.updated", entity_type="document", entity_id=document.id,
                             deal_id=deal.id, user=user, summary=f"{user.full_name} updated '{document.filename}'")
        await self.session.commit()
        return to_read(await self.get(deal, document_id))

    async def delete(self, user: User, deal: Deal, document_id: uuid.UUID) -> None:
        document = await self.get(deal, document_id)
        key, name = document.storage_key, document.filename
        await self.repo.delete(document)
        await self.audit.log(action="document.deleted", entity_type="document", entity_id=document_id,
                             deal_id=deal.id, user=user, summary=f"{user.full_name} deleted '{name}'")
        await self.session.commit()
        await storage.delete(key)

    async def reprocess(self, user: User, deal: Deal, document_id: uuid.UUID) -> DocumentRead:
        document = await self.get(deal, document_id)
        if document.status == DocumentStatus.PROCESSING:
            raise ValidationFailedError("This document is already being processed.")
        document.status = DocumentStatus.QUEUED
        document.error_message = None
        await self.audit.log(action="document.reprocessed", entity_type="document", entity_id=document.id,
                             deal_id=deal.id, user=user, summary=f"{user.full_name} re-processed '{document.filename}'")
        await self.session.commit()
        enqueue_processing(document.id)
        return to_read(await self.get(deal, document_id))

    def file_path(self, document: Document) -> Path:
        return storage.path_for(document.storage_key)


# --- Background pipeline -------------------------------------------------------
def enqueue_processing(document_id: uuid.UUID) -> None:
    ingestion_queue.submit(f"ingest:{document_id}", lambda: process_document(document_id))


async def process_document(document_id: uuid.UUID) -> None:
    started = time.perf_counter()
    async with SessionLocal() as session:
        repo = DocumentRepository(session)
        document = await repo.get(document_id)
        if document is None:
            return
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        await session.commit()

        try:
            path = storage.path_for(document.storage_key)
            extraction = await extract(path, document.file_extension)
            blocks = clean_blocks(extraction.blocks)
            if not blocks:
                raise ExtractionError(
                    "No readable text was found. If this is a scanned document, ensure OCR is enabled."
                )
            chunks = chunk_blocks(blocks, settings.chunk_size, settings.chunk_overlap)

            # Embed with a light header so filename/category/section context informs the vector.
            embed_inputs = [
                f"{document.filename} | {document.category.value}" + (f" | {c.section}" if c.section else "") + f"\n{c.content}"
                for c in chunks
            ]
            vectors = await embeddings.embed_documents(embed_inputs)

            await repo.replace_chunks(
                document.id,
                [
                    DocumentChunk(
                        document_id=document.id,
                        deal_id=document.deal_id,
                        chunk_index=index,
                        page_number=chunk.page,
                        section=chunk.section[:300] if chunk.section else None,
                        content=chunk.content,
                        char_count=len(chunk.content),
                        is_ocr=chunk.is_ocr,
                        embedding=vector,
                    )
                    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )
            document.page_count = extraction.page_count
            document.ocr_page_count = extraction.ocr_pages
            document.ocr_applied = extraction.ocr_pages > 0
            document.chunk_count = len(chunks)
            document.char_count = sum(len(c.content) for c in chunks)
            document.status = DocumentStatus.READY
            document.processed_at = datetime.now(UTC)
            document.processing_ms = int((time.perf_counter() - started) * 1000)
            await AuditService(session).log(
                action="document.processed", entity_type="document", entity_id=document.id, deal_id=document.deal_id,
                summary=f"'{document.filename}' indexed: {len(chunks)} chunks"
                + (f", OCR on {extraction.ocr_pages} page(s)" if extraction.ocr_pages else ""),
            )
            await session.commit()
            logger.info("Processed %s in %sms (%s chunks)", document.filename, document.processing_ms, len(chunks))
        except Exception as exc:  # noqa: BLE001 - record any failure on the document
            await session.rollback()
            message = str(exc) if isinstance(exc, ExtractionError) else "Processing failed. Try re-processing the file."
            if not isinstance(exc, ExtractionError):
                logger.exception("Failed to process document %s", document_id)
            await repo.mark_status(document_id, DocumentStatus.FAILED, message)
            await session.commit()
            return

        if settings.auto_summarize_documents and settings.llm_configured:
            await generate_document_insights(session, document, "\n\n".join(c.content for c in chunks))


async def generate_document_insights(session: AsyncSession, document: Document, text: str) -> None:
    """Best-effort Gemini summary + key facts; failures never affect the document's READY status."""
    try:
        insight = await llm.generate_structured(
            DOCUMENT_INSIGHT_PROMPT.format(
                filename=document.filename, category=document.category.value, text=text[:24000]
            ),
            _DocumentInsight,
            max_tokens=2048,
        )
        document.summary = insight.summary.strip()
        document.key_facts = [fact.model_dump() for fact in insight.key_facts[:10]]
        await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("Could not generate insights for %s", document.filename, exc_info=True)
        await session.rollback()


async def resume_pending_documents() -> int:
    """Re-queue documents interrupted by a restart."""
    async with SessionLocal() as session:
        ids = await DocumentRepository(session).ids_with_status((DocumentStatus.QUEUED, DocumentStatus.PROCESSING))
    for document_id in ids:
        enqueue_processing(document_id)
    return len(ids)
