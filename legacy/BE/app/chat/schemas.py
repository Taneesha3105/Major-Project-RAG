from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.retrieval.schemas import RetrievalLatency

RERANK_STRATEGY_VALUES = {"fast", "hybrid", "neural"}
RETRIEVAL_MODE_VALUES = {"exact", "ann_rerank"}


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=settings.chat_top_k_default, ge=1)
    document_id: int | None = Field(default=None, ge=1)
    provider: str | None = Field(default=None)
    retrieval_mode: str | None = Field(default=None)
    rerank_strategy: str | None = Field(default=None)
    include_debug: bool = Field(default=False)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question cannot be empty.")
        return cleaned

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, value: int) -> int:
        if value > settings.chat_top_k_max:
            raise ValueError(f"top_k cannot be greater than {settings.chat_top_k_max}.")
        return value

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return value

        normalized_value = value.strip().lower()
        allowed_values = {"mock", "openai", "gemini", "groq", "openrouter"}
        if normalized_value not in allowed_values:
            raise ValueError("provider must be one of: mock, openai, gemini, groq, openrouter.")
        return normalized_value

    @field_validator("retrieval_mode")
    @classmethod
    def validate_retrieval_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value

        normalized_value = value.strip().lower()
        if normalized_value not in RETRIEVAL_MODE_VALUES:
            raise ValueError("retrieval_mode must be one of: exact, ann_rerank.")
        return normalized_value

    @field_validator("rerank_strategy")
    @classmethod
    def validate_rerank_strategy(cls, value: str | None) -> str | None:
        if value is None:
            return value

        normalized_value = value.strip().lower()
        if normalized_value not in RERANK_STRATEGY_VALUES:
            raise ValueError("rerank_strategy must be one of: fast, hybrid, neural.")
        return normalized_value


class ChatContextChunk(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    chunk_text: str
    similarity_score: float


class ChatContextRef(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    similarity_score: float


class ChatLatency(BaseModel):
    retrieval: RetrievalLatency
    prompt_build_ms: float
    preparation_ms: float = 0.0
    rerank_ms: float = 0.0
    llm_generation_ms: float
    total_ms: float
    support_retrieval_ms: float = 0.0
    neighbor_retrieval_ms: float = 0.0
    candidate_fusion_ms: float = 0.0


class ChatDebugCandidateSource(BaseModel):
    chunk_id: int
    document_id: int
    chunk_index: int
    source_kinds: list[str]
    vector_rank: int | None = None
    support_rank: int | None = None
    neighbor_rank: int | None = None
    rrf_score: float
    similarity_score: float


class ChatDebugTrace(BaseModel):
    detected_intent: str
    detected_subtype: str | None = None
    requested_retrieval_mode: str | None = None
    requested_rerank_strategy: str | None = None
    effective_rerank_strategy: str = "fast"
    flashrank_used: bool = False
    flashrank_fallback_used: bool = False
    flashrank_fallback_reason: str | None = None
    flashrank_model: str | None = None
    flashrank_candidate_count: int = 0
    flashrank_rerank_ms: float = 0.0
    flashrank_before_order: list[int] = Field(default_factory=list)
    flashrank_after_order: list[int] = Field(default_factory=list)
    support_retrieval_used: bool
    support_retrieval_succeeded: bool
    sparse_retrieval_used: bool = False
    sparse_retrieval_succeeded: bool = False
    neighbor_expansion_used: bool
    retrieval_strategy: str
    answer_path: str = "llm"
    evidence_signature_passed: bool = False
    composer_allowed: bool = False
    composer_attempted: bool = False
    composer_block_reason: str | None = None
    answer_policy_rejected: bool = False
    fallback_path_used: str | None = None
    candidate_sources: list[ChatDebugCandidateSource] = Field(default_factory=list)


class ChatResponse(BaseModel):
    question: str
    answer: str
    provider: str
    provider_used: bool = True
    answer_path: str = "llm"
    retrieval_mode: str | None = None
    rerank_strategy: str | None = None
    rerank_fallback_used: bool = False
    context_count: int
    context_refs: list[ChatContextRef]
    latency: ChatLatency
    prompt: str | None = None
    context_chunks: list[ChatContextChunk] | None = None
    debug_trace: ChatDebugTrace | None = None
