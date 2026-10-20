import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import DocumentCategory, MessageRole
from app.schemas.common import ORMModel


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationRead(ORMModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(ORMModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[dict[str, Any]]
    feedback: int | None
    latency_ms: int | None
    created_at: datetime


class ChatScope(BaseModel):
    categories: list[DocumentCategory] = Field(default_factory=list)
    document_ids: list[uuid.UUID] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    scope: ChatScope = Field(default_factory=ChatScope)
    top_k: int | None = Field(default=None, ge=1, le=20)


class MessageFeedback(BaseModel):
    feedback: int = Field(ge=-1, le=1)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    scope: ChatScope = Field(default_factory=ChatScope)
    top_k: int = Field(default=8, ge=1, le=30)


class SearchHit(BaseModel):
    chunk_id: int
    document_id: uuid.UUID
    filename: str
    category: str
    page_number: int | None
    section: str | None
    content: str
    vector_score: float | None
    lexical_score: float | None
    fused_score: float
    rerank_score: float | None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    timings_ms: dict[str, int]
