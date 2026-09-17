import re
import time
from dataclasses import dataclass

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timing import elapsed_ms
from app.db.models import Chunk, Document
from app.embeddings.service import DocumentEmbeddingService
from app.retrieval.schemas import (
    RetrievalLatency,
    RetrievalMatch,
    RetrievalRequest,
    RetrievalResponse,
)


@dataclass(slots=True)
class RankedChunkRow:
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    distance: float


@dataclass(slots=True)
class FusedRetrievalCandidate:
    match: RetrievalMatch
    source_kinds: set[str]
    rrf_score: float


LEXICAL_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "between",
    "compare",
    "compared",
    "difference",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "you",
    "your",
}

LEXICAL_TERM_NORMALIZATION: dict[str, str] = {}
POSTGRES_TEXT_SEARCH_CONFIG = "english"

COMPARISON_QUERY_MARKERS = (
    "difference between",
    "compare ",
    "compared with",
    "compared to",
    " versus ",
    " vs ",
)

RESPONSIBILITY_QUERY_PREFIXES = (
    "who is responsible for ",
    "whose responsibility is ",
    "who needs to ",
    "who must ",
    "who has to ",
    "who is required to ",
)

RESPONSIBILITY_QUERY_STOP_WORDS = {
    "get",
    "gets",
    "getting",
    "need",
    "needs",
    "obtain",
    "obtaining",
    "require",
    "required",
    "requires",
    "responsibility",
    "responsible",
}

GENERIC_METHOD_PATTERNS = ("means", "based on", "based upon", "calculated", "determined", "computed", "percentage of")
GENERIC_NEGATIVE_PATTERNS = ("not", "never", "without", "excluded", "does not", "do not", "doesn't")
GENERIC_POSITIVE_PATTERNS = ("included", "covered", "allowed", "available", "count toward", "counts toward")
GENERIC_REQUIREMENT_PATTERNS = ("must", "required", "need", "needs", "permission", "approval", "authorization")
GENERIC_PROCESS_PATTERNS = ("if", "when", "then", "process", "step", "follow", "can", "must", "will")
GENERIC_OVERVIEW_PATTERNS = ("overview", "summary", "main", "includes", "topics")

DEADLINE_DIRECT_TIME_PATTERN = re.compile(
    r"\bwithin\s+\d+\s+(?:hour|hours|calendar\s+day|calendar\s+days|day|days)\b",
    re.IGNORECASE,
)


class RetrievalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.embedding_service = DocumentEmbeddingService(session)

    async def search(self, payload: RetrievalRequest) -> RetrievalResponse:
        overall_start = time.perf_counter()
        document_lookup_ms: float | None = None

        if payload.document_id is not None:
            document_lookup_start = time.perf_counter()
            document_exists = await self._document_exists(payload.document_id)
            document_lookup_ms = elapsed_ms(document_lookup_start)
            if not document_exists:
                raise LookupError("Document not found.")

        embedding_start = time.perf_counter()
        query_embedding = (await self.embedding_service.generate_embeddings([payload.query]))[0]
        query_embedding_ms = elapsed_ms(embedding_start)

        vector_search_start = time.perf_counter()
        if self._effective_retrieval_mode(payload) == "ann_rerank":
            rows = await self._search_ann_rerank(payload, query_embedding)
        else:
            rows = await self._search_exact(payload, query_embedding)
        vector_search_ms = elapsed_ms(vector_search_start)

        matches = [
            RetrievalMatch(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                metadata=chunk.chunk_metadata,
                similarity_score=max(0.0, 1.0 - float(distance_value)),
            )
            for chunk, filename, distance_value in rows
        ]

        if matches:
            message = "Top matching chunks returned."
        elif settings.retrieval_similarity_threshold > 0:
            message = (
                "No matching chunks met the current similarity threshold. "
                "Try another question or a different document scope."
            )
        else:
            message = "No matching chunks were found."
        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=len(matches),
            matches=matches,
            latency=RetrievalLatency(
                document_lookup_ms=document_lookup_ms,
                query_embedding_ms=query_embedding_ms,
                vector_search_ms=vector_search_ms,
                total_ms=elapsed_ms(overall_start),
            ),
            message=message,
        )

    async def search_for_chat(self, payload: RetrievalRequest) -> RetrievalResponse:
        overall_start = time.perf_counter()
        document_lookup_ms: float | None = None

        if payload.document_id is not None:
            document_lookup_start = time.perf_counter()
            document_exists = await self._document_exists(payload.document_id)
            document_lookup_ms = elapsed_ms(document_lookup_start)
            if not document_exists:
                raise LookupError("Document not found.")

        embedding_start = time.perf_counter()
        query_embedding = (await self.embedding_service.generate_embeddings([payload.query]))[0]
        query_embedding_ms = elapsed_ms(embedding_start)

        vector_search_start = time.perf_counter()
        vector_limit = max(payload.top_k, settings.chat_retrieval_fetch_k, 12)
        vector_payload = payload.model_copy(update={"top_k": vector_limit})
        ranked_rows = await self._search_ranked(vector_payload, query_embedding)
        vector_search_ms = elapsed_ms(vector_search_start)

        vector_hydration_start = time.perf_counter()
        vector_matches = await self._hydrate_chat_matches(ranked_rows)
        vector_hydration_ms = elapsed_ms(vector_hydration_start)

        sparse_search_start = time.perf_counter()
        sparse_matches = await self._search_sparse_matches(payload, limit=12)
        sparse_search_ms = elapsed_ms(sparse_search_start)

        query_terms = self._extract_lexical_terms(payload.query)
        lexical_matches: list[RetrievalMatch] = []
        lexical_rescue_ms: float | None = None
        if settings.chat_lexical_rescue_enabled and self._should_run_lexical_rescue(query_terms):
            lexical_rescue_start = time.perf_counter()
            lexical_matches = await self._search_lexical_rescue_matches(
                payload,
                query_terms,
                limit=max(settings.chat_lexical_rescue_k, 6),
            )
            lexical_rescue_ms = elapsed_ms(lexical_rescue_start)

        retrieval_fusion_start = time.perf_counter()
        matches = self._fuse_chat_matches_with_rrf(
            vector_matches[:12],
            sparse_matches[:12],
            lexical_matches[:6],
            limit=vector_limit,
        )
        retrieval_fusion_ms = elapsed_ms(retrieval_fusion_start)

        if matches:
            message = "Top matching chunks returned."
        elif settings.retrieval_similarity_threshold > 0:
            message = (
                "No matching chunks met the current similarity threshold. "
                "Try another question or a different document scope."
            )
        else:
            message = "No matching chunks were found."

        return RetrievalResponse(
            query=payload.query,
            top_k=payload.top_k,
            returned_count=len(matches),
            matches=matches,
            latency=RetrievalLatency(
                document_lookup_ms=document_lookup_ms,
                query_embedding_ms=query_embedding_ms,
                vector_search_ms=vector_search_ms,
                total_ms=elapsed_ms(overall_start),
                vector_hydration_ms=vector_hydration_ms,
                sparse_search_ms=sparse_search_ms,
                lexical_rescue_ms=lexical_rescue_ms,
                retrieval_fusion_ms=retrieval_fusion_ms,
            ),
            message=message,
        )

    async def search_comparison_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        query_terms = self._extract_lexical_terms(question)
        comparison_terms = self._extract_comparison_terms(question, query_terms)
        if not comparison_terms or limit <= 0:
            return []

        rows = await self._search_comparison_definition_candidates(
            RetrievalRequest(
                query=question,
                top_k=max(limit, settings.chat_retrieval_fetch_k),
                document_id=document_id,
            ),
            comparison_terms,
            limit=max(limit * 10, 100),
        )

        candidate_matches: list[RetrievalMatch] = []
        for row in rows:
            if len(row) == 7:
                chunk_id, matched_document_id, filename, chunk_index, chunk_text, chunk_metadata, _ = row
            else:
                chunk_id, matched_document_id, filename, chunk_index, chunk_text, _ = row
                chunk_metadata = {}
            candidate_matches.append(
                RetrievalMatch(
                    chunk_id=chunk_id,
                    document_id=matched_document_id,
                    filename=filename,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    metadata=chunk_metadata or {},
                    similarity_score=max(settings.retrieval_similarity_threshold, 0.55),
                )
            )

        selected_matches: list[RetrievalMatch] = []
        used_chunk_ids: set[int] = set()
        for term in comparison_terms:
            ranked_for_term = sorted(
                candidate_matches,
                key=lambda match: self._score_comparison_support_match(term, match.chunk_text),
                reverse=True,
            )
            for match in ranked_for_term:
                if match.chunk_id in used_chunk_ids:
                    continue
                if self._score_comparison_support_match(term, match.chunk_text) <= 0:
                    continue
                selected_matches.append(
                    match.model_copy(
                        update={"chunk_text": self._trim_comparison_support_text(term, match.chunk_text)}
                    )
                )
                used_chunk_ids.add(match.chunk_id)
                break

        return selected_matches[:limit]

    async def search_responsibility_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        query_terms = self._extract_lexical_terms(question)
        responsibility_terms = self._extract_responsibility_terms(question, query_terms)
        if not responsibility_terms or limit <= 0:
            return []

        lexical_score = self._build_lexical_rank_expression(responsibility_terms)
        if lexical_score is None:
            return []

        sparse_query_text = self.build_sparse_query_text(question)
        candidate_limit = max(limit * 8, settings.chat_retrieval_fetch_k * 6, 24)
        support_payload = RetrievalRequest(query=question, top_k=limit, document_id=document_id)
        if sparse_query_text is not None:
            tsquery = func.websearch_to_tsquery(POSTGRES_TEXT_SEARCH_CONFIG, sparse_query_text)
            sparse_rank = func.ts_rank_cd(Chunk.search_vector, tsquery).label("sparse_rank")
            statement = (
                select(
                    Chunk.id,
                    Chunk.document_id,
                    Document.filename,
                    Chunk.chunk_index,
                    Chunk.chunk_text,
                    lexical_score.label("lexical_score"),
                    sparse_rank,
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(*self._build_search_filters(support_payload))
                .where(or_(lexical_score > 0, Chunk.search_vector.op("@@")(tsquery)))
                .order_by((lexical_score + (sparse_rank * 25.0)).desc(), Chunk.document_id, Chunk.chunk_index)
                .limit(candidate_limit)
            )
        else:
            statement = (
                select(
                    Chunk.id,
                    Chunk.document_id,
                    Document.filename,
                    Chunk.chunk_index,
                    Chunk.chunk_text,
                    lexical_score.label("lexical_score"),
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(*self._build_search_filters(support_payload))
                .where(lexical_score > 0)
                .order_by(lexical_score.desc(), Chunk.document_id, Chunk.chunk_index)
                .limit(candidate_limit)
            )
        result = await self.session.execute(statement)
        candidate_rows = list(result.all())

        scored_matches: list[tuple[float, RetrievalMatch]] = []
        for candidate_row in candidate_rows:
            if sparse_query_text is not None:
                chunk_id, matched_document_id, filename, chunk_index, chunk_text, db_score, sparse_rank = candidate_row
                sparse_rank_value = float(sparse_rank)
            else:
                chunk_id, matched_document_id, filename, chunk_index, chunk_text, db_score = candidate_row
                sparse_rank_value = 0.0
            python_score = self._score_responsibility_support_match(responsibility_terms, chunk_text)
            if python_score <= 0:
                continue

            combined_score = float(db_score) + (sparse_rank_value * 25.0) + python_score
            similarity_score = min(
                settings.chat_high_confidence_top_similarity_score - 0.001,
                round(0.5 + min(0.249, python_score / 100.0), 3),
            )
            support_source_kinds: list[str] = []
            if float(db_score) > 0:
                support_source_kinds.append("lexical")
            if sparse_rank_value > 0:
                support_source_kinds.append("sparse")
            scored_matches.append(
                (
                    combined_score,
                    RetrievalMatch(
                        chunk_id=chunk_id,
                        document_id=matched_document_id,
                        filename=filename,
                        chunk_index=chunk_index,
                        chunk_text=self._trim_responsibility_support_text(chunk_text),
                        metadata={
                            "support_intent": "responsibility",
                            "support_subtype": "responsibility",
                            "support_source_kinds": support_source_kinds,
                        },
                        similarity_score=similarity_score,
                    ),
                )
            )

        scored_matches.sort(
            key=lambda item: (item[0], item[1].similarity_score, -item[1].chunk_index),
            reverse=True,
        )
        return [match for _, match in scored_matches[:limit]]

    async def search_deadline_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        return await self._search_generic_support_matches(question, document_id, limit=limit, intent_name="deadline")

    async def search_calculation_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        return await self._search_generic_support_matches(question, document_id, limit=limit, intent_name="calculation_method")

    async def search_inclusion_exclusion_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        return await self._search_generic_support_matches(question, document_id, limit=limit, intent_name="inclusion_exclusion")

    async def search_process_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        return await self._search_generic_support_matches(question, document_id, limit=limit, intent_name="process_explanation")

    async def search_summary_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        return await self._search_generic_support_matches(question, document_id, limit=limit, intent_name="broad_summary")

    async def load_neighbor_matches(
        self,
        anchors: list[RetrievalMatch],
        *,
        window: int,
    ) -> list[RetrievalMatch]:
        if not anchors or window <= 0:
            return []

        anchors_by_document: dict[int, list[RetrievalMatch]] = {}
        for anchor in anchors:
            anchors_by_document.setdefault(anchor.document_id, []).append(anchor)

        neighbor_matches: list[RetrievalMatch] = []
        for document_id, document_anchors in anchors_by_document.items():
            max_index_statement = select(func.max(Chunk.chunk_index)).where(Chunk.document_id == document_id)
            max_index_result = await self.session.execute(max_index_statement)
            max_index = max_index_result.scalar_one_or_none()
            if max_index is None:
                continue

            requested_indexes: set[int] = set()
            anchor_by_index = {anchor.chunk_index: anchor for anchor in document_anchors}
            for anchor in document_anchors:
                lower_bound = max(0, anchor.chunk_index - window)
                upper_bound = min(int(max_index), anchor.chunk_index + window)
                requested_indexes.update(range(lower_bound, upper_bound + 1))

            if not requested_indexes:
                continue

            statement = (
                select(Chunk.id, Document.filename, Chunk.chunk_index, Chunk.chunk_text, Chunk.chunk_metadata)
                .join(Document, Document.id == Chunk.document_id)
                .where(Chunk.document_id == document_id, Chunk.chunk_index.in_(requested_indexes))
                .order_by(Chunk.chunk_index)
            )
            result = await self.session.execute(statement)

            for row in result.all():
                if len(row) == 5:
                    chunk_id, filename, chunk_index, chunk_text, chunk_metadata = row
                else:
                    chunk_id, filename, chunk_index, chunk_text = row
                    chunk_metadata = {}
                anchor = min(
                    document_anchors,
                    key=lambda item: abs(item.chunk_index - chunk_index),
                )
                distance = abs(anchor.chunk_index - chunk_index)
                similarity_score = max(
                    settings.retrieval_similarity_threshold,
                    round(anchor.similarity_score - (distance * 0.02), 3),
                )
                neighbor_matches.append(
                    RetrievalMatch(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        chunk_index=chunk_index,
                        chunk_text=chunk_text,
                        metadata={
                            **(chunk_metadata or {}),
                            "support_intent": anchor.metadata.get("support_intent"),
                            "support_subtype": anchor.metadata.get("support_subtype"),
                            "neighbor_of_chunk_id": anchor.chunk_id,
                            "cue_hits": anchor.metadata.get("cue_hits", []),
                        },
                        similarity_score=similarity_score,
                    )
                )

        return neighbor_matches

    async def _search_generic_support_matches(
        self,
        question: str,
        document_id: int | None,
        *,
        limit: int,
        intent_name: str,
    ) -> list[RetrievalMatch]:
        query_terms = self._extract_lexical_terms(question)
        if not query_terms or limit <= 0:
            return []

        payload = RetrievalRequest(
            query=question,
            top_k=max(limit, settings.chat_retrieval_fetch_k),
            document_id=document_id,
        )
        lexical_score = self._build_lexical_rank_expression(query_terms)
        if lexical_score is None:
            return []

        trim_patterns = self._build_support_trim_patterns(question, query_terms)
        sparse_query_text = self.build_sparse_query_text(payload.query)
        candidate_limit = max(limit * 8, settings.chat_retrieval_fetch_k * 4, 24)

        if sparse_query_text is not None:
            tsquery = func.websearch_to_tsquery(POSTGRES_TEXT_SEARCH_CONFIG, sparse_query_text)
            sparse_rank = func.ts_rank_cd(Chunk.search_vector, tsquery).label("sparse_rank")
            statement = (
                select(
                    Chunk.id,
                    Chunk.document_id,
                    Document.filename,
                    Chunk.chunk_index,
                    Chunk.chunk_text,
                    Chunk.chunk_metadata,
                    lexical_score.label("lexical_score"),
                    sparse_rank,
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(*self._build_search_filters(payload))
                .where(or_(lexical_score > 0, Chunk.search_vector.op("@@")(tsquery)))
                .order_by((lexical_score + (sparse_rank * 25.0)).desc(), Chunk.document_id, Chunk.chunk_index)
                .limit(candidate_limit)
            )
        else:
            statement = (
                select(
                    Chunk.id,
                    Chunk.document_id,
                    Document.filename,
                    Chunk.chunk_index,
                    Chunk.chunk_text,
                    Chunk.chunk_metadata,
                    lexical_score.label("lexical_score"),
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(*self._build_search_filters(payload))
                .where(lexical_score > 0)
                .order_by(lexical_score.desc(), Chunk.document_id, Chunk.chunk_index)
                .limit(candidate_limit)
            )
        result = await self.session.execute(statement)
        candidate_rows = list(result.all())

        scored_matches: list[tuple[float, RetrievalMatch]] = []
        for candidate_row in candidate_rows:
            if sparse_query_text is not None:
                chunk_id, document_id, filename, chunk_index, chunk_text, chunk_metadata, db_score, sparse_rank = candidate_row
                sparse_rank_value = float(sparse_rank)
            else:
                chunk_id, document_id, filename, chunk_index, chunk_text, chunk_metadata, db_score = candidate_row
                sparse_rank_value = 0.0
            python_score = self._score_generic_support_match(intent_name, query_terms, question, chunk_text)
            if python_score <= 0:
                continue

            combined_score = float(db_score) + (sparse_rank_value * 25.0) + python_score
            trimmed_text = self._trim_phrase_support_text(chunk_text, trim_patterns)
            lowered_chunk_text = chunk_text.lower()
            cue_hits = sorted(
                {
                    *[term for term in query_terms if term in lowered_chunk_text],
                    *[pattern for pattern in trim_patterns if pattern in lowered_chunk_text],
                }
            )
            support_source_kinds: list[str] = []
            if float(db_score) > 0:
                support_source_kinds.append("lexical")
            if sparse_rank_value > 0:
                support_source_kinds.append("sparse")
            similarity_score = min(
                settings.chat_high_confidence_top_similarity_score - 0.001,
                round(0.5 + min(0.249, python_score / 100.0), 3),
            )
            scored_matches.append(
                (
                    combined_score,
                    RetrievalMatch(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        chunk_index=chunk_index,
                        chunk_text=trimmed_text,
                        metadata={
                            **(chunk_metadata or {}),
                            "support_intent": intent_name,
                            "support_subtype": intent_name,
                            "support_score": round(combined_score, 3),
                            "support_source_kinds": support_source_kinds,
                            "summary_anchor": intent_name == "broad_summary",
                            "cue_hits": cue_hits,
                        },
                        similarity_score=similarity_score,
                    ),
                )
            )

        scored_matches.sort(
            key=lambda item: (item[0], item[1].similarity_score, -item[1].chunk_index),
            reverse=True,
        )
        return [match for _, match in scored_matches[:limit]]

    async def _apply_chat_lexical_rescue(
        self,
        payload: RetrievalRequest,
        matches: list[RetrievalMatch],
    ) -> list[RetrievalMatch]:
        if not settings.chat_lexical_rescue_enabled or settings.chat_lexical_rescue_k <= 0:
            return matches

        query_terms = self._extract_lexical_terms(payload.query)
        if not self._should_run_lexical_rescue(query_terms):
            return matches

        lexical_matches = await self._search_lexical_rescue_matches(
            payload,
            query_terms,
            limit=settings.chat_lexical_rescue_k,
        )
        if not lexical_matches:
            return matches

        fetch_limit = max(payload.top_k, settings.chat_retrieval_fetch_k)
        return self._merge_chat_matches(matches, lexical_matches, limit=fetch_limit)

    async def _document_exists(self, document_id: int) -> bool:
        statement = select(Document.id).where(Document.id == document_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _search_exact(
        self,
        payload: RetrievalRequest,
        query_embedding: list[float],
    ) -> list[tuple[Chunk, str, float]]:
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        max_distance = self._max_distance_for_threshold()
        statement = (
            select(Chunk, Document.filename, distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(*self._build_search_filters(payload))
            .where(distance <= max_distance)
            .order_by(distance, Chunk.document_id, Chunk.chunk_index)
            .limit(payload.top_k)
        )

        result = await self.session.execute(statement)
        return result.all()

    async def _search_ann_rerank(
        self,
        payload: RetrievalRequest,
        query_embedding: list[float],
    ) -> list[tuple[Chunk, str, float]]:
        candidate_count = max(settings.retrieval_candidate_k, payload.top_k)
        candidate_distance = Chunk.embedding.cosine_distance(query_embedding).label("candidate_distance")
        candidate_statement = (
            select(Chunk.id, candidate_distance)
            .where(*self._build_search_filters(payload))
            .order_by(candidate_distance, Chunk.document_id, Chunk.chunk_index)
            .limit(candidate_count)
        )

        candidate_result = await self.session.execute(candidate_statement)
        candidate_rows = candidate_result.all()
        candidate_ids = [chunk_id for chunk_id, _ in candidate_rows]

        if not candidate_ids:
            return []

        exact_distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        max_distance = self._max_distance_for_threshold()
        rerank_filters = [Chunk.id.in_(candidate_ids), Chunk.embedding.is_not(None)]
        if payload.document_id is not None:
            rerank_filters.append(Chunk.document_id == payload.document_id)

        rerank_statement: Select = (
            select(Chunk, Document.filename, exact_distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(*rerank_filters)
            .where(exact_distance <= max_distance)
            .order_by(exact_distance, Chunk.document_id, Chunk.chunk_index)
            .limit(payload.top_k)
        )

        rerank_result = await self.session.execute(rerank_statement)
        return rerank_result.all()

    async def _search_ranked(
        self,
        payload: RetrievalRequest,
        query_embedding: list[float],
    ) -> list[RankedChunkRow]:
        if self._effective_retrieval_mode(payload) == "ann_rerank":
            return await self._search_ann_rerank_ranked(payload, query_embedding)
        return await self._search_exact_ranked(payload, query_embedding)

    @staticmethod
    def _effective_retrieval_mode(payload: RetrievalRequest) -> str:
        return payload.retrieval_mode or settings.retrieval_mode

    async def _search_exact_ranked(
        self,
        payload: RetrievalRequest,
        query_embedding: list[float],
    ) -> list[RankedChunkRow]:
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        max_distance = self._max_distance_for_threshold()
        statement = (
            select(Chunk.id, Chunk.document_id, Document.filename, Chunk.chunk_index, distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(*self._build_search_filters(payload))
            .where(distance <= max_distance)
            .order_by(distance, Chunk.document_id, Chunk.chunk_index)
            .limit(payload.top_k)
        )

        result = await self.session.execute(statement)
        return [
            RankedChunkRow(
                chunk_id=chunk_id,
                document_id=document_id,
                filename=filename,
                chunk_index=chunk_index,
                distance=float(distance_value),
            )
            for chunk_id, document_id, filename, chunk_index, distance_value in result.all()
        ]

    async def _search_ann_rerank_ranked(
        self,
        payload: RetrievalRequest,
        query_embedding: list[float],
    ) -> list[RankedChunkRow]:
        candidate_count = max(settings.retrieval_candidate_k, payload.top_k)
        candidate_distance = Chunk.embedding.cosine_distance(query_embedding).label("candidate_distance")
        candidate_statement = (
            select(Chunk.id, candidate_distance)
            .where(*self._build_search_filters(payload))
            .order_by(candidate_distance, Chunk.document_id, Chunk.chunk_index)
            .limit(candidate_count)
        )

        candidate_result = await self.session.execute(candidate_statement)
        candidate_rows = candidate_result.all()
        candidate_ids = [chunk_id for chunk_id, _ in candidate_rows]

        if not candidate_ids:
            return []

        exact_distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        max_distance = self._max_distance_for_threshold()
        rerank_filters = [Chunk.id.in_(candidate_ids), Chunk.embedding.is_not(None)]
        if payload.document_id is not None:
            rerank_filters.append(Chunk.document_id == payload.document_id)

        rerank_statement: Select = (
            select(Chunk.id, Chunk.document_id, Document.filename, Chunk.chunk_index, exact_distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(*rerank_filters)
            .where(exact_distance <= max_distance)
            .order_by(exact_distance, Chunk.document_id, Chunk.chunk_index)
            .limit(payload.top_k)
        )

        rerank_result = await self.session.execute(rerank_statement)
        return [
            RankedChunkRow(
                chunk_id=chunk_id,
                document_id=document_id,
                filename=filename,
                chunk_index=chunk_index,
                distance=float(distance_value),
            )
            for chunk_id, document_id, filename, chunk_index, distance_value in rerank_result.all()
        ]

    async def _hydrate_chat_matches(self, ranked_rows: list[RankedChunkRow]) -> list[RetrievalMatch]:
        if not ranked_rows:
            return []

        chunk_ids = [row.chunk_id for row in ranked_rows]
        statement = select(Chunk.id, Chunk.chunk_text, Chunk.chunk_metadata).where(Chunk.id.in_(chunk_ids))
        result = await self.session.execute(statement)
        data_by_chunk_id: dict[int, dict[str, object]] = {}
        for row in result.all():
            if len(row) == 3:
                chunk_id, chunk_text, chunk_metadata = row
            else:
                chunk_id, chunk_text = row
                chunk_metadata = {}
            data_by_chunk_id[chunk_id] = {"chunk_text": chunk_text, "metadata": chunk_metadata or {}}

        matches: list[RetrievalMatch] = []
        for row in ranked_rows:
            chunk_data = data_by_chunk_id.get(row.chunk_id)
            if chunk_data is None:
                continue

            matches.append(
                RetrievalMatch(
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    filename=row.filename,
                    chunk_index=row.chunk_index,
                    chunk_text=chunk_data["chunk_text"],
                    metadata={**chunk_data["metadata"], "base_source_kinds": ["vector"]},
                    similarity_score=max(0.0, 1.0 - row.distance),
                )
            )

        return matches

    async def _search_sparse_matches(
        self,
        payload: RetrievalRequest,
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        sparse_query_text = self.build_sparse_query_text(payload.query)
        if sparse_query_text is None or limit <= 0:
            return []

        tsquery = func.websearch_to_tsquery(POSTGRES_TEXT_SEARCH_CONFIG, sparse_query_text)
        sparse_rank = func.ts_rank_cd(Chunk.search_vector, tsquery).label("sparse_rank")
        statement = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.filename,
                Chunk.chunk_index,
                Chunk.chunk_text,
                Chunk.chunk_metadata,
                sparse_rank,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(*self._build_search_filters(payload, require_embedding=False))
            .where(Chunk.search_vector.op("@@")(tsquery))
            .order_by(sparse_rank.desc(), Chunk.document_id, Chunk.chunk_index)
            .limit(limit)
        )
        result = await self.session.execute(statement)

        matches: list[RetrievalMatch] = []
        for row in result.all():
            if len(row) == 7:
                chunk_id, document_id, filename, chunk_index, chunk_text, chunk_metadata, rank_value = row
            else:
                chunk_id, document_id, filename, chunk_index, chunk_text, rank_value = row
                chunk_metadata = {}
            similarity_score = min(
                settings.chat_high_confidence_top_similarity_score - 0.001,
                round(0.5 + min(0.249, float(rank_value)), 3),
            )
            matches.append(
                RetrievalMatch(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    filename=filename,
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    metadata={**(chunk_metadata or {}), "base_source_kinds": ["sparse"]},
                    similarity_score=similarity_score,
                )
            )

        return matches

    async def _search_lexical_rescue_matches(
        self,
        payload: RetrievalRequest,
        query_terms: list[str],
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        if not query_terms or limit <= 0:
            return []

        comparison_terms = self._extract_comparison_terms(payload.query, query_terms)
        lexical_score = self._build_lexical_rank_expression(
            query_terms,
            comparison_terms=comparison_terms,
        )
        if lexical_score is None:
            return []

        candidate_limit = max(limit * 4, payload.top_k * 4, 12)
        statement = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.filename,
                Chunk.chunk_index,
                Chunk.chunk_text,
                Chunk.chunk_metadata,
                lexical_score.label("lexical_score"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(*self._build_search_filters(payload))
            .where(lexical_score > 0)
            .order_by(lexical_score.desc(), Chunk.document_id, Chunk.chunk_index)
            .limit(candidate_limit)
        )
        result = await self.session.execute(statement)
        candidate_rows = list(result.all())

        if comparison_terms:
            definition_rows = await self._search_comparison_definition_candidates(
                payload,
                comparison_terms,
                limit=max(limit * 10, 100),
            )
            seen_chunk_ids = {chunk_id for chunk_id, *_ in candidate_rows}
            for row in definition_rows:
                chunk_id = row[0]
                if chunk_id in seen_chunk_ids:
                    continue
                candidate_rows.append(row)
                seen_chunk_ids.add(chunk_id)

        scored_matches: list[tuple[float, RetrievalMatch]] = []
        for row in candidate_rows:
            if len(row) == 7:
                chunk_id, document_id, filename, chunk_index, chunk_text, chunk_metadata, db_score = row
            else:
                chunk_id, document_id, filename, chunk_index, chunk_text, db_score = row
                chunk_metadata = {}
            python_score = self._score_lexical_candidate(
                query_terms,
                chunk_text,
                comparison_terms=comparison_terms,
            )
            if python_score <= 0:
                continue

            combined_score = float(db_score) + python_score
            similarity_score = self._lexical_similarity_score(
                query_terms,
                chunk_text,
                comparison_terms=comparison_terms,
                comparison_python_score=python_score,
            )
            scored_matches.append(
                (
                    combined_score,
                    RetrievalMatch(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        chunk_index=chunk_index,
                        chunk_text=chunk_text,
                        metadata={**(chunk_metadata or {}), "base_source_kinds": ["lexical"]},
                        similarity_score=similarity_score,
                    ),
                )
            )

        scored_matches.sort(
            key=lambda item: (item[0], item[1].similarity_score, -item[1].chunk_index),
            reverse=True,
        )
        return [match for _, match in scored_matches[:limit]]

    async def _search_comparison_definition_candidates(
        self,
        payload: RetrievalRequest,
        comparison_terms: list[str],
        *,
        limit: int,
    ) -> list[tuple[int, int, str, int, str, dict[str, object], float]]:
        if not comparison_terms or limit <= 0:
            return []

        lowered_chunk_text = func.lower(Chunk.chunk_text)
        weighted_patterns: dict[str, float] = {}
        for term in comparison_terms:
            weighted_patterns[f"%{term}%–%"] = max(weighted_patterns.get(f"%{term}%–%", 0.0), 8.0)
            weighted_patterns[f"%{term}%-%"] = max(weighted_patterns.get(f"%{term}%-%", 0.0), 8.0)
            weighted_patterns[f"%{term}%is%a%"] = max(weighted_patterns.get(f"%{term}%is%a%", 0.0), 6.0)
            weighted_patterns[f"%{term}%is%an%"] = max(weighted_patterns.get(f"%{term}%is%an%", 0.0), 6.0)
            weighted_patterns[f"%{term}%is%something%"] = max(
                weighted_patterns.get(f"%{term}%is%something%", 0.0),
                7.0,
            )
            weighted_patterns[f"%{term}%means%"] = max(weighted_patterns.get(f"%{term}%means%", 0.0), 6.0)
            weighted_patterns[f"%{term}%refers%"] = max(weighted_patterns.get(f"%{term}%refers%", 0.0), 6.0)
            weighted_patterns[f"%type%of%{term}%"] = max(
                weighted_patterns.get(f"%type%of%{term}%", 0.0),
                7.0,
            )

        expressions = [
            case((lowered_chunk_text.like(pattern), weight), else_=0.0)
            for pattern, weight in weighted_patterns.items()
        ]
        if not expressions:
            return []

        score_expression = expressions[0]
        for expression in expressions[1:]:
            score_expression = score_expression + expression

        statement = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.filename,
                Chunk.chunk_index,
                Chunk.chunk_text,
                Chunk.chunk_metadata,
                score_expression.label("lexical_score"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(*self._build_search_filters(payload))
            .where(score_expression > 0)
            .order_by(score_expression.desc(), Chunk.document_id, Chunk.chunk_index)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return result.all()

    def _build_search_filters(self, payload: RetrievalRequest, *, require_embedding: bool = True) -> list[object]:
        filters: list[object] = []
        if require_embedding:
            filters.append(Chunk.embedding.is_not(None))
        if payload.document_id is not None:
            filters.append(Chunk.document_id == payload.document_id)
        return filters

    @staticmethod
    def _max_distance_for_threshold() -> float:
        similarity_threshold = settings.retrieval_similarity_threshold
        if similarity_threshold <= 0:
            return 1.0
        return max(0.0, 1.0 - similarity_threshold)

    @staticmethod
    def _extract_lexical_terms(question: str) -> list[str]:
        terms: list[str] = []
        seen_terms: set[str] = set()
        normalized_question = re.sub(r"\bu\.\s*s\.?\b", "united states", question.lower())
        for token in re.findall(r"[a-z0-9']+", normalized_question):
            normalized = RetrievalService._normalize_lexical_token(token)
            if len(normalized) < 4 or normalized in LEXICAL_STOP_WORDS or normalized in seen_terms:
                continue
            terms.append(normalized)
            seen_terms.add(normalized)
        for facet in sorted(RetrievalService._extract_query_facets(normalized_question)):
            facet_token = RetrievalService._facet_to_token(facet)
            if facet_token not in seen_terms:
                terms.append(facet_token)
                seen_terms.add(facet_token)
        return terms

    @staticmethod
    def build_sparse_query_text(question: str) -> str | None:
        sparse_terms = RetrievalService._extract_sparse_terms(question)
        query_facets = RetrievalService._extract_query_facets(question)
        sparse_parts = list(sparse_terms)
        for facet in sorted(query_facets):
            if " " in facet or "-" in facet:
                sparse_parts.append(f"\"{facet}\"")
            elif facet not in sparse_parts:
                sparse_parts.append(facet)

        if not sparse_parts:
            return None
        return " ".join(sparse_parts)

    @staticmethod
    def _extract_sparse_terms(question: str) -> list[str]:
        terms: list[str] = []
        seen_terms: set[str] = set()
        normalized_question = re.sub(r"\bu\.\s*s\.?\b", "united states", question.lower())
        for token in re.findall(r"[a-z0-9']+", normalized_question):
            normalized = RetrievalService._normalize_sparse_token(token)
            if len(normalized) < 4 or normalized in LEXICAL_STOP_WORDS or normalized in seen_terms:
                continue
            terms.append(normalized)
            seen_terms.add(normalized)
        return terms

    @staticmethod
    def _normalize_sparse_token(token: str) -> str:
        cleaned = token.lower()
        if cleaned.endswith("'s"):
            cleaned = cleaned[:-2]
        return cleaned

    @staticmethod
    def _normalize_lexical_token(token: str) -> str:
        cleaned = token.lower()
        if cleaned.endswith("'s"):
            cleaned = cleaned[:-2]
        normalized = LEXICAL_TERM_NORMALIZATION.get(cleaned, cleaned)
        if normalized.endswith("ies") and len(normalized) > 4:
            return f"{normalized[:-3]}y"
        if normalized.endswith("s") and len(normalized) > 4 and not normalized.endswith("ss"):
            return normalized[:-1]
        return normalized

    @staticmethod
    def _extract_query_facets(question: str) -> set[str]:
        lowered_question = question.lower()
        facets: set[str] = set()
        for pattern in (
            r"\b(?:chapter|section|part|phase|stage|tier|level)\s+[a-z0-9.-]+\b",
            r"\b\d+-day\b",
            r"\b\d+\s+(?:day|days|hour|hours|month|months|year|years)\b",
        ):
            facets.update(re.findall(pattern, lowered_question))
        return facets

    @staticmethod
    def _extract_chunk_facets(chunk_text: str) -> set[str]:
        lowered_text = chunk_text.lower()
        facets: set[str] = set()
        for pattern in (
            r"\b(?:chapter|section|part|phase|stage|tier|level)\s+[a-z0-9.-]+\b",
            r"\b\d+-day\b",
            r"\b\d+\s+(?:day|days|hour|hours|month|months|year|years)\b",
        ):
            facets.update(re.findall(pattern, lowered_text))
        return facets

    @staticmethod
    def _facet_match_score(query_facets: set[str], chunk_facets: set[str]) -> float:
        if not query_facets or not chunk_facets:
            return 0.0
        return len(query_facets & chunk_facets) * 6.0

    @staticmethod
    def _facet_token_match_score(query_terms: list[str], chunk_tokens: list[str]) -> float:
        query_facet_tokens = {
            term
            for term in query_terms
            if term.startswith(("chapter_", "section_", "part_", "phase_", "stage_", "tier_", "level_"))
            or term.endswith(("_stage", "_day", "_days", "_hour", "_hours", "_month", "_months", "_year", "_years"))
        }
        chunk_facet_tokens = {
            token
            for token in chunk_tokens
            if token.startswith(("chapter_", "section_", "part_", "phase_", "stage_", "tier_", "level_"))
            or token.endswith(("_stage", "_day", "_days", "_hour", "_hours", "_month", "_months", "_year", "_years"))
        }

        if not query_facet_tokens or not chunk_facet_tokens:
            return 0.0
        return len(query_facet_tokens & chunk_facet_tokens) * 6.0

    @staticmethod
    def _extract_comparison_terms(question: str, query_terms: list[str]) -> list[str]:
        if not RetrievalService._is_comparison_query(question):
            return []
        return query_terms[:3]

    @staticmethod
    def _extract_responsibility_terms(question: str, query_terms: list[str]) -> list[str]:
        if not RetrievalService._is_responsibility_query(question):
            return []
        return [
            term
            for term in query_terms
            if term not in RESPONSIBILITY_QUERY_STOP_WORDS
        ]

    @staticmethod
    def _is_comparison_query(question: str) -> bool:
        lowered_question = question.lower()
        return any(marker in lowered_question for marker in COMPARISON_QUERY_MARKERS)

    @staticmethod
    def _is_responsibility_query(question: str) -> bool:
        lowered_question = question.strip().lower()
        return lowered_question.startswith(RESPONSIBILITY_QUERY_PREFIXES)

    @staticmethod
    def _should_run_lexical_rescue(query_terms: list[str]) -> bool:
        return len(query_terms) >= 2 or any(
            term.startswith(("chapter_", "section_", "part_", "phase_", "stage_", "tier_", "level_"))
            or any(char.isdigit() for char in term)
            for term in query_terms
        )

    @staticmethod
    def _build_lexical_rank_expression(
        query_terms: list[str],
        *,
        comparison_terms: list[str] | None = None,
        extra_patterns: dict[str, float] | None = None,
    ):
        weighted_patterns: dict[str, float] = {}

        for term in query_terms:
            weighted_patterns[f"%{term}%"] = max(weighted_patterns.get(f"%{term}%", 0.0), 1.5)
            like_term = term.replace("_", " ")
            if like_term != term:
                weighted_patterns[f"%{like_term}%"] = max(weighted_patterns.get(f"%{like_term}%", 0.0), 3.5)

        for phrase in RetrievalService._build_query_phrases(query_terms, size=2):
            pattern = RetrievalService._phrase_to_like_pattern(phrase)
            weighted_patterns[pattern] = max(weighted_patterns.get(pattern, 0.0), 4.0)

        for phrase in RetrievalService._build_query_phrases(query_terms, size=3):
            pattern = RetrievalService._phrase_to_like_pattern(phrase)
            weighted_patterns[pattern] = max(weighted_patterns.get(pattern, 0.0), 6.0)

        comparison_terms = comparison_terms or []
        for term in comparison_terms:
            weighted_patterns[f"%{term}%is%a%"] = max(weighted_patterns.get(f"%{term}%is%a%", 0.0), 4.5)
            weighted_patterns[f"%{term}%is%an%"] = max(weighted_patterns.get(f"%{term}%is%an%", 0.0), 4.5)
            weighted_patterns[f"%{term}%is%something%"] = max(
                weighted_patterns.get(f"%{term}%is%something%", 0.0),
                4.5,
            )
            weighted_patterns[f"%an%{term}%is%a%"] = max(
                weighted_patterns.get(f"%an%{term}%is%a%", 0.0),
                5.5,
            )
            weighted_patterns[f"%an%{term}%is%an%"] = max(
                weighted_patterns.get(f"%an%{term}%is%an%", 0.0),
                5.5,
            )
            weighted_patterns[f"%an%{term}%is%something%"] = max(
                weighted_patterns.get(f"%an%{term}%is%something%", 0.0),
                6.0,
            )
            weighted_patterns[f"%{term}%means%"] = max(weighted_patterns.get(f"%{term}%means%", 0.0), 4.5)
            weighted_patterns[f"%{term}%refers%"] = max(weighted_patterns.get(f"%{term}%refers%", 0.0), 4.5)
            weighted_patterns[f"%{term}%dispute%"] = max(weighted_patterns.get(f"%{term}%dispute%", 0.0), 3.0)
            weighted_patterns[f"%type%of%{term}%"] = max(
                weighted_patterns.get(f"%type%of%{term}%", 0.0),
                4.5,
            )

        if len(comparison_terms) >= 2:
            first, second = comparison_terms[:2]
            weighted_patterns[f"%{first}%{second}%"] = max(
                weighted_patterns.get(f"%{first}%{second}%", 0.0),
                3.5,
            )
            weighted_patterns[f"%{second}%{first}%"] = max(
                weighted_patterns.get(f"%{second}%{first}%", 0.0),
                3.5,
            )

        for pattern, weight in (extra_patterns or {}).items():
            weighted_patterns[pattern] = max(weighted_patterns.get(pattern, 0.0), weight)

        if not weighted_patterns:
            return None

        lowered_chunk_text = func.lower(Chunk.chunk_text)
        expressions = [
            case((lowered_chunk_text.like(pattern), weight), else_=0.0)
            for pattern, weight in weighted_patterns.items()
        ]

        score_expression = expressions[0]
        for expression in expressions[1:]:
            score_expression = score_expression + expression
        return score_expression

    @staticmethod
    def _build_support_trim_patterns(question: str, query_terms: list[str]) -> tuple[str, ...]:
        lowered_question = question.lower()
        patterns = [term.replace("_", " ") for term in query_terms[:6]]
        generic_patterns = [
            phrase
            for phrase in ("within", "means", "based on", "included", "excluded", "required", "process", "if", "when")
            if phrase in lowered_question
        ]
        deduped: list[str] = []
        for pattern in (*patterns, *generic_patterns):
            if pattern and pattern not in deduped:
                deduped.append(pattern)
        return tuple(deduped[:8])

    @staticmethod
    def _score_generic_support_match(intent_name: str, query_terms: list[str], question: str, chunk_text: str) -> float:
        chunk_tokens = RetrievalService._extract_chunk_tokens(chunk_text)
        if not chunk_tokens:
            return 0.0

        chunk_term_set = set(chunk_tokens)
        matched_terms = [term for term in query_terms if term in chunk_term_set]
        if not matched_terms:
            return 0.0

        coverage_ratio = len(matched_terms) / len(query_terms)
        phrase_hits = RetrievalService._count_query_phrase_hits(query_terms, chunk_tokens)
        lowered_text = chunk_text.lower()
        base_score = len(matched_terms) * 3.0 + coverage_ratio * 6.0 + phrase_hits * 5.0

        if intent_name == "deadline":
            if DEADLINE_DIRECT_TIME_PATTERN.search(lowered_text):
                base_score += 18.0
            if "fast" in question.lower() and ("fast" in lowered_text or "expedited" in lowered_text):
                base_score += 6.0
            if "standard" in question.lower() and ("standard" in lowered_text or "regular" in lowered_text):
                base_score += 6.0
            return base_score

        if intent_name == "responsibility":
            if any(phrase in lowered_text for phrase in RESPONSIBILITY_QUERY_PREFIXES):
                base_score += 4.0
            if any(phrase in lowered_text for phrase in ("responsible for", "responsibility of", "must", "required to")):
                base_score += 10.0
            return base_score

        if intent_name == "calculation_method":
            method_bonus = sum(4.0 for phrase in GENERIC_METHOD_PATTERNS if phrase in lowered_text)
            return base_score + method_bonus

        if intent_name == "inclusion_exclusion":
            polarity_bonus = 0.0
            polarity_bonus += sum(3.0 for phrase in GENERIC_POSITIVE_PATTERNS if phrase in lowered_text)
            polarity_bonus += sum(3.0 for phrase in GENERIC_NEGATIVE_PATTERNS if phrase in lowered_text)
            polarity_bonus += sum(3.0 for phrase in GENERIC_REQUIREMENT_PATTERNS if phrase in lowered_text)
            return base_score + polarity_bonus

        if intent_name == "broad_summary":
            overview_bonus = 0.0
            overview_bonus += sum(3.0 for phrase in GENERIC_OVERVIEW_PATTERNS if phrase in lowered_text)
            if chunk_text.count("â€¢") >= 2:
                overview_bonus += 6.0
            return base_score + overview_bonus

        process_bonus = 0.0
        process_bonus += sum(2.5 for phrase in GENERIC_PROCESS_PATTERNS if phrase in lowered_text)
        if "what happens if" in question.lower() and any(phrase in lowered_text for phrase in ("if ", "when ", "then ", "will ", "can ")):
            process_bonus += 6.0
        return base_score + process_bonus

    @staticmethod
    def _score_deadline_support_match(query_terms: list[str], chunk_text: str) -> float:
        return RetrievalService._score_generic_support_match("deadline", query_terms, "how long", chunk_text)

    @staticmethod
    def _score_calculation_support_match(query_terms: list[str], chunk_text: str) -> float:
        return RetrievalService._score_generic_support_match("calculation_method", query_terms, "how is it calculated", chunk_text)

    @staticmethod
    def _score_inclusion_support_match(query_terms: list[str], chunk_text: str) -> float:
        return RetrievalService._score_generic_support_match("inclusion_exclusion", query_terms, "is it included", chunk_text)

    @staticmethod
    def _score_part_d_counts_toward_support_match(query_terms: list[str], chunk_text: str) -> float:
        return RetrievalService._score_generic_support_match("inclusion_exclusion", query_terms, "what counts toward", chunk_text)

    @staticmethod
    def _score_process_support_match(query_terms: list[str], chunk_text: str) -> float:
        return RetrievalService._score_generic_support_match("process_explanation", query_terms, "what happens if", chunk_text)

    @staticmethod
    def _score_summary_support_match(query_terms: list[str], chunk_text: str) -> float:
        return RetrievalService._score_generic_support_match("broad_summary", query_terms, "tell me about", chunk_text)

    @staticmethod
    def _trim_phrase_support_text(chunk_text: str, patterns: tuple[str, ...]) -> str:
        lowered_text = chunk_text.lower()
        positions = [lowered_text.find(pattern) for pattern in patterns if lowered_text.find(pattern) >= 0]
        if not positions:
            return chunk_text

        pattern_position = min(positions)
        line_start = max(
            chunk_text.rfind("\n", 0, pattern_position),
            chunk_text.rfind("\r", 0, pattern_position),
        )
        if line_start < 0:
            sentence_start = RetrievalService._find_sentence_start(chunk_text, pattern_position)
            trimmed = chunk_text[sentence_start:]
        elif pattern_position - line_start > 120:
            sentence_start = RetrievalService._find_sentence_start(
                chunk_text,
                pattern_position,
                lower_bound=line_start + 1,
            )
            trimmed = chunk_text[sentence_start:]
        else:
            trimmed = chunk_text[line_start + 1 :]
        return trimmed.lstrip(" .\r\n\t")

    @staticmethod
    def _find_sentence_start(text: str, position: int, *, lower_bound: int = 0) -> int:
        sentence_breaks = [
            text.rfind(marker, lower_bound, position)
            for marker in (". ", "? ", "! ")
        ]
        best_break = max(sentence_breaks)
        if best_break >= lower_bound:
            return best_break + 2
        return max(lower_bound, 0)

    @staticmethod
    def _build_query_phrases(query_terms: list[str], *, size: int) -> list[tuple[str, ...]]:
        if len(query_terms) < size:
            return []
        return [
            tuple(query_terms[index : index + size])
            for index in range(len(query_terms) - size + 1)
        ]

    @staticmethod
    def _phrase_to_like_pattern(phrase: tuple[str, ...]) -> str:
        return "%" + "%".join(phrase) + "%"

    @staticmethod
    def _extract_chunk_tokens(chunk_text: str) -> list[str]:
        tokens: list[str] = []
        for token in re.findall(r"[a-z0-9']+", chunk_text.lower()):
            normalized = RetrievalService._normalize_lexical_token(token)
            if len(normalized) >= 4:
                tokens.append(normalized)
        for facet in sorted(RetrievalService._extract_chunk_facets(chunk_text)):
            tokens.append(RetrievalService._facet_to_token(facet))
        return tokens

    @staticmethod
    def _facet_to_token(facet: str) -> str:
        return facet.replace(" ", "_").replace("-", "_")

    @staticmethod
    def _score_lexical_candidate(
        query_terms: list[str],
        chunk_text: str,
        *,
        comparison_terms: list[str] | None = None,
    ) -> float:
        chunk_tokens = RetrievalService._extract_chunk_tokens(chunk_text)
        if not chunk_tokens:
            return 0.0

        chunk_term_set = set(chunk_tokens)
        matched_terms = [term for term in query_terms if term in chunk_term_set]
        if not matched_terms:
            return 0.0

        overlap_count = len(matched_terms)
        coverage_ratio = overlap_count / len(query_terms)
        phrase_hits = RetrievalService._count_query_phrase_hits(query_terms, chunk_tokens)
        window_size = RetrievalService._smallest_covering_window(matched_terms, chunk_tokens)
        proximity_bonus = 0.0
        if window_size is not None:
            proximity_bonus = max(0.0, 6.0 - (window_size - overlap_count))

        lowered_text = chunk_text.lower()
        value_density_bonus = min(2.0, max(chunk_text.count("$") + chunk_text.count("%") - 1, 0) * 1.0)
        structure_bonus = 1.5 if ":" in chunk_text or "\n" in chunk_text else 0.0
        facet_bonus = RetrievalService._facet_token_match_score(query_terms, chunk_tokens)

        comparison_bonus = 0.0
        comparison_terms = comparison_terms or []
        if comparison_terms:
            comparison_term_set = set(comparison_terms)
            matched_comparison_terms = [term for term in comparison_terms if term in chunk_term_set]
            comparison_bonus += len(set(matched_comparison_terms)) * 1.0

            if RetrievalService._contains_glossary_dash(chunk_text) and matched_comparison_terms:
                comparison_bonus += 1.5

            pattern_positions = [
                position
                for term in comparison_term_set
                if (position := RetrievalService._comparison_term_pattern_position(lowered_text, term)) is not None
            ]
            if pattern_positions:
                comparison_bonus += 12.0
                comparison_bonus += max(0.0, 18.0 - (min(pattern_positions) / 20.0))

        return (
            overlap_count * 3.0
            + coverage_ratio * 3.0
            + phrase_hits * 5.0
            + proximity_bonus
            + value_density_bonus
            + structure_bonus
            + comparison_bonus
            + facet_bonus
        )

    @staticmethod
    def _count_query_phrase_hits(query_terms: list[str], chunk_tokens: list[str]) -> int:
        hit_count = 0
        for phrase_size in (3, 2):
            query_phrases = RetrievalService._build_query_phrases(query_terms, size=phrase_size)
            if not query_phrases:
                continue
            chunk_phrases = {
                tuple(chunk_tokens[index : index + phrase_size])
                for index in range(len(chunk_tokens) - phrase_size + 1)
            }
            hit_count += sum(1 for phrase in query_phrases if phrase in chunk_phrases)
        return hit_count

    @staticmethod
    def _smallest_covering_window(required_terms: list[str], chunk_tokens: list[str]) -> int | None:
        if not required_terms:
            return None

        required = set(required_terms)
        counts: dict[str, int] = {}
        window_start = 0
        best_window: int | None = None

        for window_end, token in enumerate(chunk_tokens):
            if token not in required:
                continue

            counts[token] = counts.get(token, 0) + 1
            while len(counts) == len(required):
                window_size = window_end - window_start + 1
                if best_window is None or window_size < best_window:
                    best_window = window_size

                start_token = chunk_tokens[window_start]
                if start_token in required:
                    counts[start_token] -= 1
                    if counts[start_token] == 0:
                        del counts[start_token]
                window_start += 1
                while window_start < len(chunk_tokens) and chunk_tokens[window_start] not in required and len(counts) < len(required):
                    window_start += 1

        return best_window

    @staticmethod
    def _lexical_similarity_score(
        query_terms: list[str],
        chunk_text: str,
        *,
        comparison_terms: list[str] | None = None,
        comparison_python_score: float | None = None,
    ) -> float:
        chunk_tokens = RetrievalService._extract_chunk_tokens(chunk_text)
        if not chunk_tokens:
            return max(settings.retrieval_similarity_threshold, 0.35)

        chunk_term_set = set(chunk_tokens)
        matched_terms = [term for term in query_terms if term in chunk_term_set]
        coverage_ratio = len(matched_terms) / len(query_terms) if query_terms else 0.0
        phrase_hits = RetrievalService._count_query_phrase_hits(query_terms, chunk_tokens)
        window_size = RetrievalService._smallest_covering_window(matched_terms, chunk_tokens)
        proximity_score = 0.0
        if window_size is not None:
            proximity_score = max(0.0, 1.0 - ((window_size - len(matched_terms)) / max(len(chunk_tokens), 1)))

        lowered_text = chunk_text.lower()
        extra_signal = 0.0
        if "$" in chunk_text or "%" in chunk_text:
            extra_signal += 0.04
        if ":" in chunk_text or "\n" in chunk_text:
            extra_signal += 0.02

        comparison_terms = comparison_terms or []
        if comparison_terms:
            comparison_term_set = set(comparison_terms)
            matched_comparison_terms = [term for term in comparison_terms if term in chunk_term_set]
            pattern_positions = [
                position
                for term in comparison_term_set
                if (position := RetrievalService._comparison_term_pattern_position(lowered_text, term)) is not None
            ]
            if comparison_python_score is not None:
                comparison_similarity = 0.45 + min(0.299, comparison_python_score / 100.0)
                if pattern_positions:
                    comparison_similarity += max(0.0, 0.04 - (min(pattern_positions) / 10000.0))
                return min(
                    settings.chat_high_confidence_top_similarity_score - 0.001,
                    round(comparison_similarity, 3),
                )

            extra_signal += min(0.08, len(set(matched_comparison_terms)) * 0.04)
            if RetrievalService._contains_glossary_dash(chunk_text) and matched_comparison_terms:
                extra_signal += 0.05
            if pattern_positions:
                extra_signal += 0.08
                extra_signal += max(0.0, 0.04 - (min(pattern_positions) / 10000.0))

        similarity_score = (
            0.36
            + coverage_ratio * 0.22
            + min(phrase_hits, 2) * 0.08
            + min(proximity_score, 1.0) * 0.08
            + extra_signal
        )
        return min(settings.chat_high_confidence_top_similarity_score - 0.01, round(similarity_score, 3))

    @staticmethod
    def _contains_glossary_dash(chunk_text: str) -> bool:
        normalized_text = chunk_text.replace("\r", " ").replace("\n", " ").strip()
        return " – " in normalized_text or " â€“ " in normalized_text or " - " in normalized_text

    @staticmethod
    def _comparison_term_pattern_position(lowered_text: str, term: str) -> int | None:
        definition_patterns = (
            f"{term} is a ",
            f"{term} is an ",
            f"{term} means ",
            f"{term} refers to ",
            f"{term} is something ",
            f"an {term} is a ",
            f"an {term} is an ",
            f"an {term} is something ",
            f"type of {term}",
        )
        positions = [
            lowered_text.find(pattern)
            for pattern in definition_patterns
            if lowered_text.find(pattern) >= 0
        ]
        if not positions:
            return None
        return min(positions)

    @staticmethod
    def _score_comparison_support_match(term: str, chunk_text: str) -> float:
        lowered_text = chunk_text.lower()
        position = RetrievalService._comparison_term_pattern_position(lowered_text, term)
        if position is None:
            return 0.0

        score = 30.0
        score += max(0.0, 20.0 - (position / 25.0))
        heading_position = RetrievalService._comparison_term_heading_position(lowered_text, term)
        if heading_position is not None:
            score += 14.0
            score += max(0.0, 10.0 - (heading_position / 40.0))
        if RetrievalService._contains_glossary_dash(chunk_text):
            score += 6.0
        if term in set(RetrievalService._extract_chunk_tokens(chunk_text)):
            score += 2.0
        return score

    @staticmethod
    def _trim_comparison_support_text(term: str, chunk_text: str) -> str:
        lowered_text = chunk_text.lower()
        heading_position = RetrievalService._comparison_term_heading_position(lowered_text, term)
        if heading_position is not None:
            return chunk_text[heading_position:].lstrip(" .\r\n\t")

        pattern_position = RetrievalService._comparison_term_pattern_position(lowered_text, term)
        if pattern_position is None:
            return chunk_text

        line_start = max(
            chunk_text.rfind("\n", 0, pattern_position),
            chunk_text.rfind("\r", 0, pattern_position),
        )
        if line_start < 0:
            trimmed = chunk_text[pattern_position:]
        else:
            trimmed = chunk_text[line_start + 1 :]
        return trimmed.lstrip(" .\r\n\t")

    @staticmethod
    def _comparison_term_heading_position(lowered_text: str, term: str) -> int | None:
        heading_patterns = (
            f"{term} – ",
            f"{term} â€“ ",
            f"{term} - ",
        )
        positions = [
            lowered_text.find(pattern)
            for pattern in heading_patterns
            if lowered_text.find(pattern) >= 0
        ]
        if not positions:
            return None
        return min(positions)

    @staticmethod
    def _score_responsibility_support_match(responsibility_terms: list[str], chunk_text: str) -> float:
        chunk_tokens = RetrievalService._extract_chunk_tokens(chunk_text)
        if not chunk_tokens:
            return 0.0

        chunk_term_set = set(chunk_tokens)
        matched_terms = [term for term in responsibility_terms if term in chunk_term_set]
        if not matched_terms:
            return 0.0

        coverage_ratio = len(matched_terms) / len(responsibility_terms)
        phrase_hits = RetrievalService._count_query_phrase_hits(responsibility_terms, chunk_tokens)
        window_size = RetrievalService._smallest_covering_window(matched_terms, chunk_tokens)
        proximity_bonus = 0.0
        if window_size is not None:
            proximity_bonus = max(0.0, 6.0 - (window_size - len(matched_terms)))

        lowered_text = chunk_text.lower()
        pattern_position = RetrievalService._responsibility_pattern_position(lowered_text)
        pattern_bonus = 0.0
        if pattern_position is not None:
            pattern_bonus += 18.0
            pattern_bonus += max(0.0, 16.0 - (pattern_position / 30.0))

        actor_bonus = 6.0 if RetrievalService._contains_actor_assignment_pattern(lowered_text) else 0.0
        exception_penalty = 0.0

        return (
            len(matched_terms) * 3.0
            + coverage_ratio * 4.0
            + phrase_hits * 5.0
            + proximity_bonus
            + pattern_bonus
            + actor_bonus
            - exception_penalty
        )

    @staticmethod
    def _trim_responsibility_support_text(chunk_text: str) -> str:
        lowered_text = chunk_text.lower()
        pattern_position = RetrievalService._responsibility_pattern_position(lowered_text)
        if pattern_position is None:
            return chunk_text

        line_start = max(
            chunk_text.rfind("\n", 0, pattern_position),
            chunk_text.rfind("\r", 0, pattern_position),
        )
        if line_start < 0:
            trimmed = chunk_text[pattern_position:]
        else:
            trimmed = chunk_text[line_start + 1 :]
        return trimmed.lstrip(" .\r\n\t")

    @staticmethod
    def _responsibility_pattern_position(lowered_text: str) -> int | None:
        patterns = (
            "responsibility of",
            "responsible for",
            "must obtain",
            "must get",
            "must do",
            "must submit",
            "need to",
            "needs to",
            "required to obtain",
            "required to",
            "owner of",
        )
        positions = [
            lowered_text.find(pattern)
            for pattern in patterns
            if lowered_text.find(pattern) >= 0
        ]
        if not positions:
            return None
        return min(positions)

    @staticmethod
    def _contains_actor_assignment_pattern(lowered_text: str) -> bool:
        patterns = (
            "owner must",
            "manager must",
            "team must",
            "you must",
            "the user must",
            "the requester must",
            "the project owner",
            "responsible for",
        )
        return any(pattern in lowered_text for pattern in patterns)

    @staticmethod
    def _merge_chat_matches(
        vector_matches: list[RetrievalMatch],
        lexical_matches: list[RetrievalMatch],
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        merged_by_chunk_id: dict[int, RetrievalMatch] = {}
        for match in vector_matches + lexical_matches:
            existing = merged_by_chunk_id.get(match.chunk_id)
            if existing is None or match.similarity_score > existing.similarity_score:
                merged_by_chunk_id[match.chunk_id] = match

        ordered_matches = sorted(
            merged_by_chunk_id.values(),
            key=lambda match: (
                match.similarity_score,
                -match.document_id,
                -match.chunk_index,
            ),
            reverse=True,
        )
        return ordered_matches[:limit]

    @staticmethod
    def _fuse_chat_matches_with_rrf(
        vector_matches: list[RetrievalMatch],
        sparse_matches: list[RetrievalMatch],
        lexical_matches: list[RetrievalMatch],
        *,
        limit: int,
    ) -> list[RetrievalMatch]:
        fused_by_chunk_id: dict[int, FusedRetrievalCandidate] = {}
        source_lists = (
            ("vector", vector_matches),
            ("sparse", sparse_matches),
            ("lexical", lexical_matches),
        )

        for source_kind, matches in source_lists:
            for rank, match in enumerate(matches, start=1):
                candidate = fused_by_chunk_id.get(match.chunk_id)
                if candidate is None:
                    candidate = FusedRetrievalCandidate(
                        match=match,
                        source_kinds=set(match.metadata.get("base_source_kinds", [source_kind])),
                        rrf_score=0.0,
                    )
                    fused_by_chunk_id[match.chunk_id] = candidate
                else:
                    candidate.match = candidate.match.model_copy(
                        update={
                            "chunk_text": match.chunk_text if len(match.chunk_text) >= len(candidate.match.chunk_text) else candidate.match.chunk_text,
                            "metadata": {
                                **candidate.match.metadata,
                                **match.metadata,
                            },
                            "similarity_score": max(candidate.match.similarity_score, match.similarity_score),
                        }
                    )
                    candidate.source_kinds.update(match.metadata.get("base_source_kinds", [source_kind]))

                candidate.rrf_score += 1.0 / (settings.chat_rrf_k + rank)

        fused_matches: list[RetrievalMatch] = []
        for candidate in sorted(
            fused_by_chunk_id.values(),
            key=lambda item: (item.rrf_score, item.match.similarity_score, -item.match.chunk_index),
            reverse=True,
        ):
            metadata = dict(candidate.match.metadata)
            metadata["base_source_kinds"] = sorted(candidate.source_kinds)
            metadata["base_rrf_score"] = round(candidate.rrf_score, 6)
            fused_matches.append(candidate.match.model_copy(update={"metadata": metadata}))

        return fused_matches[:limit]
