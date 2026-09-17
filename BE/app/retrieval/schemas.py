from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class RetrievalLatency(BaseModel):
    document_lookup_ms: float | None = None
    query_embedding_ms: float
    vector_search_ms: float
    total_ms: float
    vector_hydration_ms: float | None = None
    sparse_search_ms: float | None = None
    lexical_rescue_ms: float | None = None
    retrieval_fusion_ms: float | None = None


class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=settings.retrieval_top_k_default, ge=1)
    document_id: int | None = Field(default=None, ge=1)
    retrieval_mode: str | None = Field(default=None)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty.")
        return cleaned

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        if value > settings.retrieval_top_k_max:
            raise ValueError(
                f"top_k cannot be greater than {settings.retrieval_top_k_max}."
            )
        return value

    @field_validator("retrieval_mode")
    @classmethod
    def validate_retrieval_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized_value = value.strip().lower()
        if normalized_value not in {"exact", "ann_rerank"}:
            raise ValueError("retrieval_mode must be one of: exact, ann_rerank.")
        return normalized_value


class RetrievalMatch(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    chunk_text: str
    metadata: dict[str, object]
    similarity_score: float


class RetrievalResponse(BaseModel):
    query: str
    top_k: int
    returned_count: int
    matches: list[RetrievalMatch]
    latency: RetrievalLatency
    message: str
