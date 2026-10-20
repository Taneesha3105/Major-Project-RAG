import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DocumentCategory, DocumentStatus
from app.schemas.common import ORMModel


class DocumentRead(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    filename: str
    mime_type: str | None
    file_extension: str
    file_size: int
    category: DocumentCategory
    description: str | None
    status: DocumentStatus
    error_message: str | None
    page_count: int | None
    chunk_count: int
    char_count: int
    ocr_applied: bool
    ocr_page_count: int
    summary: str | None
    key_facts: list[dict[str, Any]]
    processing_ms: int | None
    processed_at: datetime | None
    created_at: datetime
    uploaded_by_name: str | None = None


class DocumentUpdate(BaseModel):
    category: DocumentCategory | None = None
    description: str | None = Field(default=None, max_length=2000)


class ChunkRead(ORMModel):
    id: int
    chunk_index: int
    page_number: int | None
    section: str | None
    content: str
    is_ocr: bool


class UploadResult(BaseModel):
    uploaded: list[DocumentRead]
    skipped: list[dict[str, str]]
