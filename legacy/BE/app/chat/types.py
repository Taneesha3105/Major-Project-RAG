from dataclasses import dataclass

from app.chat.guardrails import QueryRoute
from app.chat.schemas import ChatContextChunk, ChatContextRef, ChatDebugTrace
from app.retrieval.schemas import RetrievalLatency, RetrievalMatch


@dataclass(slots=True)
class ChatPreparationLatency:
    retrieval: RetrievalLatency
    prompt_build_ms: float
    rerank_ms: float
    total_ms: float
    support_retrieval_ms: float = 0.0
    neighbor_retrieval_ms: float = 0.0
    candidate_fusion_ms: float = 0.0


@dataclass(slots=True)
class PreparedChat:
    question: str
    query_route: QueryRoute
    system_prompt: str
    prompt: str
    provider: str
    fallback_answer: str | None
    retrieval_matches: list[RetrievalMatch]
    context_refs: list[ChatContextRef]
    context_chunks: list[ChatContextChunk]
    include_debug: bool
    debug_trace: ChatDebugTrace | None
    latency: ChatPreparationLatency
