from datetime import datetime

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    id: int
    filename: str
    created_at: datetime
    updated_at: datetime
    chunk_count: int
    embedded_chunk_count: int
    has_embeddings: bool
    source_type: str | None = None
    source_format: str | None = None
    parser_name: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None


class DocumentListResponse(BaseModel):
    total_count: int
    documents: list[DocumentSummary]


class DocumentChunkPreview(BaseModel):
    id: int
    chunk_index: int
    created_at: datetime
    preview_text: str
    character_count: int


class DocumentDetailResponse(DocumentSummary):
    content_hash: str
    chunk_previews: list[DocumentChunkPreview]


class DocumentDeleteResponse(BaseModel):
    id: int
    filename: str
    deleted_chunk_count: int
    message: str
