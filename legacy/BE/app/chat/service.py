import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.answering import (
    apply_answer_policy,
    build_compact_evidence_matches,
    compose_answer,
    evidence_signature_passes,
    is_composer_allowed,
    is_specialized_route,
)
from app.chat.guardrails import (
    normalize_query_text,
    QUERY_INTENT_BROAD_SUMMARY,
    QUERY_INTENT_CALCULATION_METHOD,
    QUERY_INTENT_CLARIFY_FRAGMENT,
    QUERY_INTENT_COMPARISON,
    QUERY_INTENT_DEADLINE,
    QUERY_INTENT_DEFAULT_FACT,
    QUERY_INTENT_DEFINITION,
    QUERY_INTENT_INCLUSION_EXCLUSION,
    QUERY_INTENT_PROCESS_EXPLANATION,
    QUERY_INTENT_RESPONSIBILITY,
    QUERY_SUBTYPE_DEADLINE_FAST,
    QUERY_SUBTYPE_DEADLINE_STANDARD,
    route_query,
    should_fallback_for_low_confidence,
)
from app.chat.prompt_builder import budget_chat_context, build_chat_prompt
from app.chat.provider import BaseChatProvider, ChatGenerationRequest, get_chat_provider
from app.chat.reranker import BaseChatReranker, NoopChatReranker
from app.chat.schemas import (
    ChatContextChunk,
    ChatContextRef,
    ChatDebugCandidateSource,
    ChatDebugTrace,
    ChatLatency,
    ChatRequest,
    ChatResponse,
)
from app.chat.types import ChatPreparationLatency, PreparedChat
from app.core.config import settings
from app.core.timing import elapsed_ms
from app.retrieval.schemas import RetrievalLatency, RetrievalRequest
from app.retrieval.service import RetrievalService


logger = logging.getLogger(__name__)


def _format_sse_event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@dataclass(slots=True)
class RankedCandidate:
    match: object
    source_kinds: set[str] = field(default_factory=set)
    vector_rank: int | None = None
    support_rank: int | None = None
    neighbor_rank: int | None = None
    rrf_score: float = 0.0


RERANK_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "both",
    "by",
    "compare",
    "compared",
    "considered",
    "between",
    "difference",
    "for",
    "from",
    "have",
    "how",
    "in",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "the",
    "their",
    "them",
    "they",
    "this",
    "those",
    "to",
    "under",
    "us",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "you",
    "your",
}

STRUCTURED_VALUE_PATTERN = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?%")
RERANK_TERM_NORMALIZATION = {
    "answered": "answer",
    "answering": "answer",
    "answers": "answer",
    "costs": "cost",
    "moved": "move",
    "moves": "move",
    "moving": "move",
    "requested": "request",
    "requesting": "request",
    "requests": "request",
    "responsibilities": "responsible",
    "responsibility": "responsible",
    "services": "service",
    "stayed": "stay",
    "staying": "stay",
    "stays": "stay",
}


class ChatService:
    def __init__(self, session: AsyncSession, reranker: BaseChatReranker | None = None) -> None:
        self.session = session
        self.retrieval_service = RetrievalService(session)
        self.provider = get_chat_provider(settings.chat_provider)
        self.reranker = reranker or NoopChatReranker()

    async def ask(self, payload: ChatRequest) -> ChatResponse:
        overall_start = time.perf_counter()
        prepared_chat = await self.prepare_chat(payload)
        effective_retrieval_mode = self._resolve_retrieval_mode(payload.retrieval_mode)
        if prepared_chat.fallback_answer is not None:
            answer = prepared_chat.fallback_answer
            llm_generation_ms = 0.0
        else:
            generation_start = time.perf_counter()
            raw_answer = await self.provider.generate_answer(self._build_generation_request(prepared_chat))
            answer = self._finalize_generated_answer(prepared_chat, raw_answer)
            llm_generation_ms = elapsed_ms(generation_start)

        return ChatResponse(
            question=prepared_chat.question,
            answer=answer,
            provider=prepared_chat.provider,
            provider_used=self._provider_used(prepared_chat),
            answer_path=self._answer_path(prepared_chat),
            retrieval_mode=effective_retrieval_mode,
            rerank_strategy=prepared_chat.debug_trace.effective_rerank_strategy if prepared_chat.debug_trace else None,
            rerank_fallback_used=prepared_chat.debug_trace.flashrank_fallback_used if prepared_chat.debug_trace else False,
            context_count=len(prepared_chat.context_chunks),
            context_refs=prepared_chat.context_refs,
            latency=ChatLatency(
                retrieval=prepared_chat.latency.retrieval,
                prompt_build_ms=prepared_chat.latency.prompt_build_ms,
                preparation_ms=prepared_chat.latency.total_ms,
                rerank_ms=prepared_chat.latency.rerank_ms,
                llm_generation_ms=llm_generation_ms,
                total_ms=elapsed_ms(overall_start),
                support_retrieval_ms=prepared_chat.latency.support_retrieval_ms,
                neighbor_retrieval_ms=prepared_chat.latency.neighbor_retrieval_ms,
                candidate_fusion_ms=prepared_chat.latency.candidate_fusion_ms,
            ),
            prompt=prepared_chat.prompt if prepared_chat.include_debug else None,
            context_chunks=prepared_chat.context_chunks if prepared_chat.include_debug else None,
            debug_trace=prepared_chat.debug_trace if prepared_chat.include_debug else None,
        )

    async def stream_prepared(self, prepared_chat: PreparedChat) -> AsyncIterator[str]:
        buffered_answer: str | None = None
        if prepared_chat.fallback_answer is None and self._should_buffer_stream_output(prepared_chat):
            raw_answer = await self.provider.generate_answer(self._build_generation_request(prepared_chat))
            buffered_answer = self._finalize_generated_answer(prepared_chat, raw_answer)

        metadata = {
            "question": prepared_chat.question,
            "provider": prepared_chat.provider,
            "provider_used": self._provider_used(prepared_chat),
            "answer_path": self._answer_path(prepared_chat),
            "retrieval_mode": self._resolve_retrieval_mode(
                getattr(prepared_chat.debug_trace, "requested_retrieval_mode", None)
                if prepared_chat.debug_trace
                else None
            ),
            "rerank_strategy": (
                prepared_chat.debug_trace.effective_rerank_strategy if prepared_chat.debug_trace else None
            ),
            "rerank_fallback_used": (
                prepared_chat.debug_trace.flashrank_fallback_used if prepared_chat.debug_trace else False
            ),
            "context_count": len(prepared_chat.context_chunks),
            "context_refs": [chunk.model_dump() for chunk in prepared_chat.context_refs],
            "latency": {
                "retrieval": prepared_chat.latency.retrieval.model_dump(),
                "prompt_build_ms": prepared_chat.latency.prompt_build_ms,
                "rerank_ms": prepared_chat.latency.rerank_ms,
                "preparation_ms": prepared_chat.latency.total_ms,
                "support_retrieval_ms": prepared_chat.latency.support_retrieval_ms,
                "neighbor_retrieval_ms": prepared_chat.latency.neighbor_retrieval_ms,
                "candidate_fusion_ms": prepared_chat.latency.candidate_fusion_ms,
            },
        }
        if prepared_chat.include_debug:
            metadata["prompt"] = prepared_chat.prompt
            metadata["context_chunks"] = [chunk.model_dump() for chunk in prepared_chat.context_chunks]
            metadata["debug_trace"] = (
                prepared_chat.debug_trace.model_dump() if prepared_chat.debug_trace is not None else None
            )
        yield _format_sse_event("metadata", metadata)

        if prepared_chat.fallback_answer is not None:
            yield _format_sse_event("chunk", {"delta": prepared_chat.fallback_answer})
            yield _format_sse_event("done", {"message": "Streaming completed."})
            return

        if buffered_answer is not None:
            yield _format_sse_event("chunk", {"delta": buffered_answer})
            yield _format_sse_event("done", {"message": "Streaming completed."})
            return

        async for chunk in self.provider.stream_answer(self._build_generation_request(prepared_chat)):
            yield _format_sse_event("chunk", {"delta": chunk})

        yield _format_sse_event("done", {"message": "Streaming completed."})

    async def stream(self, payload: ChatRequest) -> AsyncIterator[str]:
        prepared_chat = await self.prepare_chat(payload)
        async for event in self.stream_prepared(prepared_chat):
            yield event

    async def prepare_chat(self, payload: ChatRequest) -> PreparedChat:
        overall_start = time.perf_counter()
        self.provider = self._resolve_provider(payload.provider)
        reranker = getattr(self, "reranker", None) or NoopChatReranker()
        effective_rerank_strategy = self._resolve_rerank_strategy(payload.rerank_strategy)
        normalized_query = normalize_query_text(
            payload.question,
            cutoff=settings.chat_query_spelling_cutoff,
        )
        query_route = route_query(normalized_query.normalized_question)
        routed_intent = query_route.intent
        debug_trace = ChatDebugTrace(
            detected_intent=query_route.intent,
            detected_subtype=query_route.subtype,
            requested_retrieval_mode=payload.retrieval_mode,
            requested_rerank_strategy=payload.rerank_strategy,
            effective_rerank_strategy=effective_rerank_strategy,
            flashrank_model=reranker.model_name,
            support_retrieval_used=False,
            support_retrieval_succeeded=False,
            sparse_retrieval_used=False,
            sparse_retrieval_succeeded=False,
            neighbor_expansion_used=False,
            retrieval_strategy="clarification_only"
            if query_route.intent == QUERY_INTENT_CLARIFY_FRAGMENT
            else "vector+lexical",
            answer_path="clarify" if query_route.clarification_message else "llm",
            evidence_signature_passed=False,
            composer_allowed=is_composer_allowed(query_route),
            composer_attempted=False,
            composer_block_reason=None,
            answer_policy_rejected=False,
            fallback_path_used="clarification" if query_route.clarification_message else None,
            candidate_sources=[],
        )
        if query_route.clarification_message:
            prompt_build_start = time.perf_counter()
            prompt = build_chat_prompt(
                question=payload.question,
                matches=[],
                intent=query_route.intent,
                subtype=query_route.subtype,
                polarity=query_route.polarity,
            )
            prompt_build_ms = elapsed_ms(prompt_build_start)
            return PreparedChat(
                question=payload.question,
                query_route=query_route,
                system_prompt=settings.chat_system_prompt,
                prompt=prompt,
                provider=self.provider.display_name,
                fallback_answer=query_route.clarification_message or settings.chat_clarification_response,
                retrieval_matches=[],
                context_refs=[],
                context_chunks=[],
                include_debug=payload.include_debug,
                debug_trace=debug_trace,
                latency=ChatPreparationLatency(
                    retrieval=RetrievalLatency(
                        document_lookup_ms=None,
                        query_embedding_ms=0.0,
                        vector_search_ms=0.0,
                        total_ms=0.0,
                    ),
                    prompt_build_ms=prompt_build_ms,
                    rerank_ms=0.0,
                    total_ms=elapsed_ms(overall_start),
                    support_retrieval_ms=0.0,
                    neighbor_retrieval_ms=0.0,
                    candidate_fusion_ms=0.0,
                ),
            )

        retrieval_result = await self.retrieval_service.search_for_chat(
            RetrievalRequest(
                query=normalized_query.normalized_question,
                top_k=max(payload.top_k, settings.chat_retrieval_fetch_k),
                document_id=payload.document_id,
                retrieval_mode=payload.retrieval_mode,
            )
        )

        support_retrieval_start = time.perf_counter()
        support_matches = await self._load_support_matches(
            query_route,
            normalized_query.normalized_question,
            payload.document_id,
        )
        support_retrieval_ms = elapsed_ms(support_retrieval_start)
        support_matches = self._annotate_support_matches(query_route, support_matches)
        support_succeeded = bool(support_matches)
        sparse_query_builder = getattr(self.retrieval_service, "build_sparse_query_text", None)
        sparse_query_text = (
            sparse_query_builder(normalized_query.normalized_question)
            if callable(sparse_query_builder)
            else None
        )
        base_sparse_succeeded = any(
            "sparse" in match.metadata.get("base_source_kinds", [])
            for match in retrieval_result.matches
        )
        support_sparse_succeeded = any(
            "sparse" in match.metadata.get("support_source_kinds", [])
            for match in support_matches
        )
        if query_route.intent == QUERY_INTENT_BROAD_SUMMARY and not support_succeeded:
            prompt_build_start = time.perf_counter()
            prompt = build_chat_prompt(
                question=payload.question,
                matches=[],
                intent=query_route.intent,
                subtype=query_route.subtype,
                polarity=query_route.polarity,
            )
            prompt_build_ms = elapsed_ms(prompt_build_start)
            debug_trace.support_retrieval_used = True
            debug_trace.support_retrieval_succeeded = False
            debug_trace.sparse_retrieval_used = sparse_query_text is not None
            debug_trace.sparse_retrieval_succeeded = base_sparse_succeeded or support_sparse_succeeded
            debug_trace.answer_path = "fallback"
            debug_trace.fallback_path_used = "clarification_from_weak_summary"
            debug_trace.retrieval_strategy = self._build_retrieval_strategy(
                query_route.intent,
                support_used=True,
                sparse_used=debug_trace.sparse_retrieval_used,
                neighbor_used=False,
            )
            return PreparedChat(
                question=payload.question,
                query_route=query_route,
                system_prompt=settings.chat_system_prompt,
                prompt=prompt,
                provider=self.provider.display_name,
                fallback_answer=settings.chat_clarification_response,
                retrieval_matches=[],
                context_refs=[],
                context_chunks=[],
                include_debug=payload.include_debug,
                debug_trace=debug_trace,
                latency=ChatPreparationLatency(
                    retrieval=retrieval_result.latency,
                    prompt_build_ms=prompt_build_ms,
                    rerank_ms=0.0,
                    total_ms=elapsed_ms(overall_start),
                    support_retrieval_ms=support_retrieval_ms,
                    neighbor_retrieval_ms=0.0,
                    candidate_fusion_ms=0.0,
                ),
            )

        neighbor_retrieval_ms = 0.0
        if support_matches:
            neighbor_retrieval_start = time.perf_counter()
            neighbor_matches = self._annotate_support_matches(
                query_route,
                await self._load_neighbor_matches(query_route.intent, support_matches),
            )
            neighbor_retrieval_ms = elapsed_ms(neighbor_retrieval_start)
        else:
            neighbor_matches = []

        candidate_fusion_start = time.perf_counter()
        fused_candidates = self._fuse_candidates(
            retrieval_result.matches,
            support_matches,
            neighbor_matches,
        )
        candidate_fusion_ms = elapsed_ms(candidate_fusion_start)
        if query_route.intent in {
            QUERY_INTENT_BROAD_SUMMARY,
            QUERY_INTENT_CALCULATION_METHOD,
            QUERY_INTENT_COMPARISON,
            QUERY_INTENT_DEADLINE,
            QUERY_INTENT_INCLUSION_EXCLUSION,
            QUERY_INTENT_PROCESS_EXPLANATION,
            QUERY_INTENT_RESPONSIBILITY,
        } and support_matches:
            prompt_candidate_source = self._merge_prompt_candidates(support_matches, [candidate.match for candidate in fused_candidates])
            prompt_candidate_rrf = {
                match.chunk_id: 1.0 for match in support_matches
            } | {
                candidate.match.chunk_id: candidate.rrf_score for candidate in fused_candidates
            }
        else:
            prompt_candidate_source = [candidate.match for candidate in fused_candidates]
            prompt_candidate_rrf = {candidate.match.chunk_id: candidate.rrf_score for candidate in fused_candidates}

        prompt_candidates, rerank_ms = await self._apply_prompt_reranking(
            normalized_query.normalized_question,
            prompt_candidate_source,
            query_route.intent,
            query_route.subtype,
            prompt_candidate_rrf,
            effective_rerank_strategy,
            debug_trace,
        )
        prompt_matches = budget_chat_context(
            prompt_candidates,
            max_total_chars=settings.chat_context_max_chars,
            max_chunks=settings.chat_context_max_chunks,
            max_chars_per_chunk=settings.chat_context_per_chunk_max_chars,
        )
        compact_prompt_matches = prompt_matches
        composer_answer: str | None = None
        fallback_answer = None
        fallback_path_used: str | None = None
        if is_specialized_route(query_route) and prompt_matches:
            if not support_succeeded:
                fallback_path_used = "default_fact_safety_valve"
                query_route = self._build_default_fact_route(query_route)
                compact_prompt_matches = []
                # Default-fact safety-valve matches stay on the fast reranker path only.
                prompt_matches = self._build_default_fact_prompt_matches(
                    normalized_query.normalized_question,
                    retrieval_result.matches,
                )
            else:
                evidence_source = self._merge_prompt_candidates(prompt_matches, support_matches)
                if neighbor_matches:
                    evidence_source = self._merge_prompt_candidates(evidence_source, neighbor_matches)
                compact_prompt_matches = build_compact_evidence_matches(
                    payload.question,
                    query_route,
                    evidence_source,
                    max_matches=settings.chat_context_max_chunks,
                    max_chars_per_match=min(settings.chat_context_per_chunk_max_chars, 500),
                )
                evidence_signature_ok = evidence_signature_passes(
                    payload.question,
                    query_route,
                    compact_prompt_matches,
                )
                debug_trace.evidence_signature_passed = evidence_signature_ok
                if not evidence_signature_ok:
                    if query_route.subtype == "overview":
                        compact_prompt_matches = []
                        fallback_answer = settings.chat_clarification_response
                        fallback_path_used = "clarification_from_weak_summary"
                        debug_trace.answer_path = "fallback"
                    else:
                        fallback_path_used = "default_fact_safety_valve"
                        query_route = self._build_default_fact_route(query_route)
                        compact_prompt_matches = []
                        # Default-fact safety-valve matches stay on the fast reranker path only.
                        prompt_matches = self._build_default_fact_prompt_matches(
                            normalized_query.normalized_question,
                            retrieval_result.matches,
                        )
                else:
                    if debug_trace.composer_allowed:
                        debug_trace.composer_attempted = True
                        composer_answer = compose_answer(
                            payload.question,
                            query_route,
                            compact_prompt_matches,
                        )
                        if composer_answer:
                            fallback_answer = composer_answer
                            fallback_path_used = "composer"
                            debug_trace.answer_path = "composer"
                        else:
                            debug_trace.composer_block_reason = "composer_returned_none"
                    else:
                        debug_trace.composer_block_reason = "subtype_not_allowlisted"

        if query_route.intent == QUERY_INTENT_BROAD_SUMMARY and not self._has_strong_summary_support(
            fused_candidates,
            prompt_matches,
        ):
            prompt_matches = []
            fallback_answer = settings.chat_clarification_response
            fallback_path_used = "clarification_from_weak_summary"
            debug_trace.answer_path = "fallback"
        if compact_prompt_matches and fallback_answer is None:
            prompt_matches = compact_prompt_matches
        strong_lexical_grounding = self._has_strong_lexical_grounding(
            normalized_query.normalized_question,
            prompt_matches,
        )
        if (
            fallback_answer is None
            and prompt_matches
            and not strong_lexical_grounding
            and should_fallback_for_low_confidence(
            prompt_matches,
            minimum_top_score=settings.chat_min_top_similarity_score,
            high_confidence_top_score=settings.chat_high_confidence_top_similarity_score,
            minimum_average_score=settings.chat_min_average_similarity_score,
            average_top_n=settings.chat_average_similarity_top_n,
        )
        ):
            prompt_matches = []
            fallback_answer = settings.chat_no_context_response
            fallback_path_used = "low_confidence"
            debug_trace.answer_path = "fallback"
        prompt_build_start = time.perf_counter()
        prompt = build_chat_prompt(
            question=payload.question,
            matches=prompt_matches,
            intent=query_route.intent,
            subtype=query_route.subtype,
            polarity=query_route.polarity,
        )
        context_chunks = [
            ChatContextChunk(
                chunk_id=match.chunk_id,
                document_id=match.document_id,
                filename=match.filename,
                chunk_index=match.chunk_index,
                chunk_text=match.chunk_text,
                similarity_score=match.similarity_score,
            )
            for match in prompt_matches
        ]
        context_refs = [
            ChatContextRef(
                chunk_id=match.chunk_id,
                document_id=match.document_id,
                filename=match.filename,
                chunk_index=match.chunk_index,
                similarity_score=match.similarity_score,
            )
            for match in prompt_matches
        ]
        prompt_build_ms = elapsed_ms(prompt_build_start)
        if not prompt_matches and fallback_answer is None:
            fallback_answer = settings.chat_no_context_response
            fallback_path_used = "no_context"
            debug_trace.answer_path = "fallback"

        debug_trace.support_retrieval_used = routed_intent in {
            QUERY_INTENT_BROAD_SUMMARY,
            QUERY_INTENT_CALCULATION_METHOD,
            QUERY_INTENT_COMPARISON,
            QUERY_INTENT_DEADLINE,
            QUERY_INTENT_INCLUSION_EXCLUSION,
            QUERY_INTENT_PROCESS_EXPLANATION,
            QUERY_INTENT_RESPONSIBILITY,
        }
        debug_trace.support_retrieval_succeeded = support_succeeded
        debug_trace.sparse_retrieval_used = sparse_query_text is not None
        debug_trace.sparse_retrieval_succeeded = base_sparse_succeeded or support_sparse_succeeded
        debug_trace.neighbor_expansion_used = bool(neighbor_matches)
        debug_trace.retrieval_strategy = self._build_retrieval_strategy(
            routed_intent,
            support_used=debug_trace.support_retrieval_used,
            sparse_used=debug_trace.sparse_retrieval_used,
            neighbor_used=debug_trace.neighbor_expansion_used,
        )
        debug_trace.fallback_path_used = fallback_path_used
        debug_trace.candidate_sources = self._build_debug_candidate_sources(
            prompt_matches,
            fused_candidates,
        )
        logger.debug("chat_debug_trace=%s", debug_trace.model_dump())

        return PreparedChat(
            question=payload.question,
            query_route=query_route,
            system_prompt=settings.chat_system_prompt,
            prompt=prompt,
            provider=self.provider.display_name,
            fallback_answer=fallback_answer,
            retrieval_matches=prompt_matches,
            context_refs=context_refs,
            context_chunks=context_chunks,
            include_debug=payload.include_debug,
            debug_trace=debug_trace,
            latency=ChatPreparationLatency(
                retrieval=retrieval_result.latency,
                prompt_build_ms=prompt_build_ms,
                rerank_ms=rerank_ms,
                total_ms=elapsed_ms(overall_start),
                support_retrieval_ms=support_retrieval_ms,
                neighbor_retrieval_ms=neighbor_retrieval_ms,
                candidate_fusion_ms=candidate_fusion_ms,
            ),
        )

    @staticmethod
    def _build_generation_request(prepared_chat: PreparedChat) -> ChatGenerationRequest:
        return ChatGenerationRequest(
            question=prepared_chat.question,
            system_prompt=prepared_chat.system_prompt,
            prompt=prepared_chat.prompt,
            matches=prepared_chat.retrieval_matches,
        )

    @staticmethod
    def _answer_path(prepared_chat: PreparedChat) -> str:
        if prepared_chat.debug_trace is not None:
            return prepared_chat.debug_trace.answer_path
        return "llm" if prepared_chat.fallback_answer is None else "fallback"

    @classmethod
    def _provider_used(cls, prepared_chat: PreparedChat) -> bool:
        return cls._answer_path(prepared_chat) == "llm"

    @staticmethod
    def _resolve_provider(provider_name: str | None) -> BaseChatProvider:
        selected_provider = provider_name or settings.chat_provider
        return get_chat_provider(selected_provider)

    @staticmethod
    def _resolve_rerank_strategy(requested_strategy: str | None) -> str:
        return requested_strategy or settings.chat_rerank_strategy_default

    @staticmethod
    def _resolve_retrieval_mode(requested_mode: str | None) -> str:
        return requested_mode or settings.retrieval_mode

    async def _apply_prompt_reranking(
        self,
        question: str,
        prompt_candidate_source: list,
        intent: str,
        subtype: str | None,
        prompt_candidate_rrf: dict[int, float],
        rerank_strategy: str,
        debug_trace: ChatDebugTrace,
    ) -> tuple[list, float]:
        if not prompt_candidate_source:
            return [], 0.0

        debug_trace.flashrank_before_order = [match.chunk_id for match in prompt_candidate_source]
        reranker = getattr(self, "reranker", None) or NoopChatReranker()
        rerank_ms = 0.0

        if rerank_strategy == "fast":
            reranked = self._rerank_prompt_matches(
                question,
                prompt_candidate_source,
                intent=intent,
                subtype=subtype,
                rrf_scores=prompt_candidate_rrf,
            )
            debug_trace.flashrank_after_order = [match.chunk_id for match in reranked]
            return reranked, rerank_ms

        if not reranker.enabled:
            debug_trace.flashrank_fallback_used = True
            debug_trace.flashrank_fallback_reason = "flashrank_unavailable"
            reranked = self._rerank_prompt_matches(
                question,
                prompt_candidate_source,
                intent=intent,
                subtype=subtype,
                rrf_scores=prompt_candidate_rrf,
            )
            debug_trace.flashrank_after_order = [match.chunk_id for match in reranked]
            return reranked, rerank_ms

        if rerank_strategy == "hybrid":
            baseline_matches = self._rerank_prompt_matches(
                question,
                prompt_candidate_source,
                intent=intent,
                subtype=subtype,
                rrf_scores=prompt_candidate_rrf,
            )
            flashrank_input = baseline_matches[: settings.flashrank_hybrid_top_n]
            tail_matches = baseline_matches[settings.flashrank_hybrid_top_n :]
        else:
            flashrank_input = prompt_candidate_source[: settings.flashrank_neural_top_n]
            tail_matches = prompt_candidate_source[settings.flashrank_neural_top_n :]

        debug_trace.flashrank_candidate_count = len(flashrank_input)
        if not flashrank_input:
            debug_trace.flashrank_after_order = [match.chunk_id for match in prompt_candidate_source]
            return prompt_candidate_source, rerank_ms

        try:
            flashrank_result = await reranker.rerank(question, flashrank_input)
        except Exception as exc:
            logger.exception("FlashRank reranking failed. Falling back to fast mode.")
            debug_trace.flashrank_fallback_used = True
            debug_trace.flashrank_fallback_reason = exc.__class__.__name__
            reranked = self._rerank_prompt_matches(
                question,
                prompt_candidate_source,
                intent=intent,
                subtype=subtype,
                rrf_scores=prompt_candidate_rrf,
            )
            debug_trace.flashrank_after_order = [match.chunk_id for match in reranked]
            return reranked, rerank_ms

        debug_trace.flashrank_used = True
        debug_trace.flashrank_rerank_ms = flashrank_result.rerank_ms
        rerank_ms = flashrank_result.rerank_ms
        combined_matches = flashrank_result.matches + tail_matches
        debug_trace.flashrank_after_order = [match.chunk_id for match in combined_matches]
        return combined_matches, rerank_ms

    @staticmethod
    def _should_buffer_stream_output(prepared_chat: PreparedChat) -> bool:
        return is_specialized_route(prepared_chat.query_route)

    @staticmethod
    def _finalize_generated_answer(prepared_chat: PreparedChat, raw_answer: str) -> str:
        composer_answer = (
            prepared_chat.fallback_answer
            if prepared_chat.debug_trace is not None
            and prepared_chat.debug_trace.answer_path == "composer"
            else None
        )
        policy_outcome = apply_answer_policy(
            raw_answer,
            prepared_chat.query_route,
            composer_answer=composer_answer,
        )
        if prepared_chat.debug_trace is not None:
            prepared_chat.debug_trace.answer_policy_rejected = policy_outcome.rejected
            if policy_outcome.rejected and policy_outcome.answer != raw_answer:
                if composer_answer and policy_outcome.answer == composer_answer:
                    prepared_chat.debug_trace.answer_path = "composer"
                elif policy_outcome.answer in {
                    settings.chat_clarification_response,
                    settings.chat_no_context_response,
                }:
                    prepared_chat.debug_trace.answer_path = "fallback"
        return policy_outcome.answer

    @staticmethod
    def _build_default_fact_route(query_route):
        return query_route.__class__(
            intent=QUERY_INTENT_DEFAULT_FACT,
            normalized_question=query_route.normalized_question,
        )

    @staticmethod
    def _annotate_support_matches(query_route, matches: list) -> list:
        annotated_matches: list = []
        for match in matches:
            metadata = dict(match.metadata)
            if query_route.subtype is not None:
                metadata["support_subtype"] = query_route.subtype
            metadata.setdefault(
                "cue_hits",
                sorted(set(ChatService._extract_query_terms(query_route.normalized_question)) & ChatService._extract_chunk_terms(match.chunk_text)),
            )
            annotated_matches.append(match.model_copy(update={"metadata": metadata}))
        return annotated_matches

    @staticmethod
    def _build_default_fact_prompt_matches(question: str, matches: list) -> list:
        prompt_candidates = ChatService._rerank_prompt_matches(
            question,
            matches,
            intent=QUERY_INTENT_DEFAULT_FACT,
            subtype=None,
        )
        return budget_chat_context(
            prompt_candidates,
            max_total_chars=settings.chat_context_max_chars,
            max_chunks=settings.chat_context_max_chunks,
            max_chars_per_chunk=settings.chat_context_per_chunk_max_chars,
        )

    async def _load_support_matches(
        self,
        query_route,
        question: str,
        document_id: int | None,
    ) -> list:
        intent = query_route.intent
        if intent == QUERY_INTENT_COMPARISON:
            return await self._load_comparison_support_matches(question, document_id)
        if intent == QUERY_INTENT_RESPONSIBILITY:
            return await self._load_responsibility_support_matches(question, document_id)
        if intent == QUERY_INTENT_DEADLINE:
            return await self._load_deadline_support_matches(question, document_id)
        if intent == QUERY_INTENT_INCLUSION_EXCLUSION:
            return await self._load_inclusion_exclusion_support_matches(question, document_id)
        if intent == QUERY_INTENT_CALCULATION_METHOD:
            return await self._load_calculation_support_matches(question, document_id)
        if intent == QUERY_INTENT_PROCESS_EXPLANATION:
            return await self._load_process_support_matches(question, document_id)
        if intent == QUERY_INTENT_BROAD_SUMMARY:
            return await self._load_summary_support_matches(question, document_id)
        return []

    async def _load_neighbor_matches(
        self,
        intent: str,
        support_matches: list,
    ) -> list:
        if intent not in {
            QUERY_INTENT_BROAD_SUMMARY,
            QUERY_INTENT_DEADLINE,
            QUERY_INTENT_INCLUSION_EXCLUSION,
            QUERY_INTENT_PROCESS_EXPLANATION,
            QUERY_INTENT_RESPONSIBILITY,
        }:
            return []

        loader = getattr(self.retrieval_service, "load_neighbor_matches", None)
        if loader is None:
            return []
        return await loader(support_matches, window=1)

    async def _load_comparison_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_comparison_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    async def _load_deadline_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_deadline_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    async def _load_calculation_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_calculation_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    async def _load_inclusion_exclusion_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_inclusion_exclusion_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    async def _load_process_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_process_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    async def _load_summary_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_summary_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    async def _load_responsibility_support_matches(
        self,
        question: str,
        document_id: int | None,
    ) -> list:
        support_loader = getattr(self.retrieval_service, "search_responsibility_support_matches", None)
        if support_loader is None:
            return []
        return await support_loader(
            question,
            document_id,
            limit=max(settings.chat_context_max_chunks, 8),
        )

    @staticmethod
    def _rerank_prompt_matches(
        question: str,
        matches: list,
        *,
        intent: str = QUERY_INTENT_DEFAULT_FACT,
        subtype: str | None = None,
        rrf_scores: dict[int, float] | None = None,
    ) -> list:
        if len(matches) <= 1:
            return matches

        query_terms = ChatService._extract_query_terms(question)
        if not query_terms:
            return matches

        rrf_scores = rrf_scores or {}

        def rerank_key(match):
            support_bonus = ChatService._support_match_bonus(intent, subtype, match.metadata)
            overlap_count = ChatService._count_term_overlap(query_terms, match.chunk_text)
            phrase_hits = ChatService._count_phrase_hits(query_terms, match.chunk_text)
            coverage_ratio = overlap_count / len(query_terms)
            structure_bonus = ChatService._generic_structure_bonus(match.chunk_text, match.metadata)
            return (
                support_bonus,
                phrase_hits,
                structure_bonus,
                coverage_ratio,
                overlap_count,
                rrf_scores.get(match.chunk_id, 0.0),
                match.similarity_score,
            )

        return sorted(matches, key=rerank_key, reverse=True)

    @staticmethod
    def _extract_query_terms(question: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9']+", re.sub(r"\bu\.\s*s\.?\b", "united states", question.lower()))
        normalized_terms: list[str] = []
        seen_terms: set[str] = set()
        for token in tokens:
            normalized = ChatService._normalize_rerank_token(token)
            if len(normalized) < 4 or normalized in RERANK_STOP_WORDS or normalized in seen_terms:
                continue
            normalized_terms.append(normalized)
            seen_terms.add(normalized)
        return normalized_terms

    @staticmethod
    def _count_term_overlap(query_terms: list[str], chunk_text: str) -> int:
        chunk_terms = ChatService._extract_chunk_terms(chunk_text)
        return len(set(query_terms) & chunk_terms)

    @staticmethod
    def _count_phrase_hits(query_terms: list[str], chunk_text: str) -> int:
        if len(query_terms) < 2:
            return 0

        normalized_chunk_tokens = [
            ChatService._normalize_rerank_token(token)
            for token in re.findall(r"[a-z0-9']+", chunk_text.lower())
        ]
        normalized_chunk_tokens = [token for token in normalized_chunk_tokens if len(token) >= 4]
        chunk_phrases = {
            f"{normalized_chunk_tokens[index]} {normalized_chunk_tokens[index + 1]}"
            for index in range(len(normalized_chunk_tokens) - 1)
        }
        query_phrases = [
            f"{query_terms[index]} {query_terms[index + 1]}"
            for index in range(len(query_terms) - 1)
        ]
        return sum(1 for phrase in query_phrases if phrase in chunk_phrases)

    @staticmethod
    def _support_match_bonus(intent: str, subtype: str | None, metadata: dict[str, object]) -> tuple[int, int, int]:
        support_intent = metadata.get("support_intent")
        support_subtype = metadata.get("support_subtype")
        return (
            int(support_subtype == subtype and subtype is not None),
            int(support_intent == intent),
            int(bool(support_intent)),
        )

    @staticmethod
    def _generic_structure_bonus(chunk_text: str, metadata: dict[str, object]) -> tuple[int, int, int]:
        lowered_text = chunk_text.lower()
        return (
            int(bool(metadata.get("table_like_row") or metadata.get("label_value_row")) or bool(STRUCTURED_VALUE_PATTERN.search(chunk_text))),
            int(":" in chunk_text or "\n" in chunk_text),
            int(bool(metadata.get("heading_path")) or lowered_text.count("•") >= 2 or lowered_text.count("- ") >= 2),
        )

    @staticmethod
    def _extract_chunk_terms(chunk_text: str) -> set[str]:
        chunk_terms: set[str] = set()
        for token in re.findall(r"[a-z0-9']+", chunk_text.lower()):
            normalized = ChatService._normalize_rerank_token(token)
            if len(normalized) >= 4:
                chunk_terms.add(normalized)
        return chunk_terms

    @staticmethod
    def _normalize_rerank_token(token: str) -> str:
        cleaned = token.lower()
        if cleaned.endswith("'s"):
            cleaned = cleaned[:-2]
        normalized = RERANK_TERM_NORMALIZATION.get(cleaned, cleaned)
        if normalized.endswith("ies") and len(normalized) > 4:
            return f"{normalized[:-3]}y"
        if normalized.endswith("s") and len(normalized) > 4 and not normalized.endswith("ss"):
            return normalized[:-1]
        return normalized

    @staticmethod
    def _has_strong_lexical_grounding(question: str, matches: list) -> bool:
        if not matches:
            return False

        query_terms = ChatService._extract_query_terms(question)
        if not query_terms:
            return False

        best_overlap = max(
            ChatService._count_term_overlap(query_terms, match.chunk_text)
            for match in matches
        )
        best_coverage_ratio = best_overlap / len(query_terms)

        if len(query_terms) <= 2:
            return best_coverage_ratio >= 1.0

        return best_coverage_ratio >= 0.75
    @staticmethod
    def _fuse_candidates(
        vector_matches: list,
        support_matches: list,
        neighbor_matches: list,
    ) -> list[RankedCandidate]:
        fused_by_chunk_id: dict[int, RankedCandidate] = {}
        list_specs = (
            ("vector", vector_matches),
            ("support", support_matches),
            ("neighbor", neighbor_matches),
        )

        for source_kind, matches in list_specs:
            for rank, match in enumerate(matches, start=1):
                ranked_candidate = fused_by_chunk_id.get(match.chunk_id)
                if ranked_candidate is None:
                    ranked_candidate = RankedCandidate(match=match)
                    fused_by_chunk_id[match.chunk_id] = ranked_candidate
                elif source_kind != "vector":
                    ranked_candidate.match = match

                if source_kind == "vector":
                    source_kinds = match.metadata.get("base_source_kinds", ["vector"])
                elif source_kind == "support":
                    source_kinds = ["support", *match.metadata.get("support_source_kinds", [])]
                else:
                    source_kinds = ["neighbor"]

                ranked_candidate.source_kinds.update(source_kinds)
                ranked_candidate.rrf_score += 1.0 / (settings.chat_rrf_k + rank)
                if source_kind == "vector":
                    ranked_candidate.vector_rank = rank
                elif source_kind == "support":
                    ranked_candidate.support_rank = rank
                else:
                    ranked_candidate.neighbor_rank = rank

        return sorted(
            fused_by_chunk_id.values(),
            key=lambda candidate: (
                candidate.rrf_score,
                candidate.match.similarity_score,
                -candidate.match.chunk_index,
            ),
            reverse=True,
        )

    @staticmethod
    def _build_retrieval_strategy(
        intent: str,
        *,
        support_used: bool,
        sparse_used: bool,
        neighbor_used: bool,
    ) -> str:
        strategy_parts = ["vector"]
        if sparse_used:
            strategy_parts.append("sparse")
        strategy_parts.append("lexical")
        if support_used:
            strategy_parts.append(f"{intent}_support")
        if neighbor_used:
            strategy_parts.append("neighbor")
        return "+".join(strategy_parts)

    @staticmethod
    def _build_debug_candidate_sources(
        prompt_matches: list,
        fused_candidates: list[RankedCandidate],
    ) -> list[ChatDebugCandidateSource]:
        fused_by_chunk_id = {candidate.match.chunk_id: candidate for candidate in fused_candidates}
        debug_sources: list[ChatDebugCandidateSource] = []
        for match in prompt_matches:
            candidate = fused_by_chunk_id.get(match.chunk_id)
            if candidate is None:
                continue
            debug_sources.append(
                ChatDebugCandidateSource(
                    chunk_id=match.chunk_id,
                    document_id=match.document_id,
                    chunk_index=match.chunk_index,
                    source_kinds=sorted(candidate.source_kinds),
                    vector_rank=candidate.vector_rank,
                    support_rank=candidate.support_rank,
                    neighbor_rank=candidate.neighbor_rank,
                    rrf_score=round(candidate.rrf_score, 6),
                    similarity_score=match.similarity_score,
                )
            )
        return debug_sources

    @staticmethod
    def _has_strong_summary_support(
        fused_candidates: list[RankedCandidate],
        prompt_matches: list,
    ) -> bool:
        if not prompt_matches or not fused_candidates:
            return False

        final_chunk_ids = {match.chunk_id for match in prompt_matches}
        summary_candidates = [
            candidate
            for candidate in fused_candidates
            if candidate.match.chunk_id in final_chunk_ids
            and candidate.match.metadata.get("support_intent") == QUERY_INTENT_BROAD_SUMMARY
        ]
        if not summary_candidates:
            return False

        summary_candidates.sort(
            key=lambda candidate: (candidate.rrf_score, candidate.match.similarity_score),
            reverse=True,
        )
        top_summary = summary_candidates[0]
        if top_summary.rrf_score < settings.chat_summary_min_rrf_score:
            return False

        best_non_summary = next(
            (
                candidate
                for candidate in fused_candidates
                if candidate.match.chunk_id in final_chunk_ids
                and candidate.match.metadata.get("support_intent") != QUERY_INTENT_BROAD_SUMMARY
            ),
            None,
        )
        if best_non_summary is not None:
            margin = top_summary.rrf_score - best_non_summary.rrf_score
            if margin < settings.chat_summary_min_margin_rrf_score:
                return False

        if top_summary.match.chunk_text.count("•") >= 2:
            return True

        corroborated = sum(
            1
            for candidate in fused_candidates[:3]
            if candidate.match.metadata.get("support_intent") == QUERY_INTENT_BROAD_SUMMARY
            or "neighbor" in candidate.source_kinds
        )
        return corroborated >= 2

    @staticmethod
    def _merge_prompt_candidates(primary_matches: list, secondary_matches: list) -> list:
        merged_matches: list = []
        seen_chunk_ids: set[int] = set()

        for match in primary_matches + secondary_matches:
            if match.chunk_id in seen_chunk_ids:
                continue
            merged_matches.append(match)
            seen_chunk_ids.add(match.chunk_id)

        return merged_matches
