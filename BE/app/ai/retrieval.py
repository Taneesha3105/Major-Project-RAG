"""Hybrid retrieval: pgvector semantic search + PostgreSQL full-text search, fused with
Reciprocal Rank Fusion and re-ranked with a FlashRank cross-encoder."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import embeddings, reranker
from app.core.config import settings
from app.models import Document, DocumentChunk
from app.models.enums import DocumentCategory, DocumentStatus

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by can could did do does for from had has have how i if in into is it its "
    "me my of on or our please show tell than that the their them there these they this those to us "
    "was we were what when where which who why will with would you your about any all give list".split()
)


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: uuid.UUID
    filename: str
    category: str
    page_number: int | None
    section: str | None
    content: str
    vector_score: float | None = None
    lexical_score: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None

    @property
    def score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.fused_score


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    timings_ms: dict[str, int] = field(default_factory=dict)


def build_or_tsquery(query: str) -> str:
    """Natural questions AND every word with plainto_tsquery; OR the meaningful terms instead."""
    terms = []
    for word in _WORD.findall(query.lower()):
        if len(word) > 1 and word not in _STOPWORDS and word not in terms:
            terms.append(word)
    return " | ".join(terms[:24])


def _scoped(
    stmt: Select,
    deal_id: uuid.UUID,
    categories: list[DocumentCategory] | None,
    document_ids: list[uuid.UUID] | None,
) -> Select:
    stmt = stmt.join(Document, Document.id == DocumentChunk.document_id).where(
        DocumentChunk.deal_id == deal_id, Document.status == DocumentStatus.READY
    )
    if categories:
        stmt = stmt.where(Document.category.in_(categories))
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
    return stmt


async def hybrid_search(
    session: AsyncSession,
    *,
    deal_id: uuid.UUID,
    query: str,
    categories: list[DocumentCategory] | None = None,
    document_ids: list[uuid.UUID] | None = None,
    top_k: int | None = None,
    use_reranker: bool = True,
) -> RetrievalResult:
    top_k = top_k or settings.retrieval_final_k
    timings: dict[str, int] = {}

    started = time.perf_counter()
    query_vector = await embeddings.embed_query(query)
    timings["embed"] = int((time.perf_counter() - started) * 1000)

    # --- semantic (pgvector, cosine) ---
    started = time.perf_counter()
    # Iterative HNSW scans keep recall high when the deal/category filter is selective (pgvector >= 0.8).
    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    vector_stmt = _scoped(
        select(DocumentChunk.id, (1 - distance).label("score")), deal_id, categories, document_ids
    ).where(DocumentChunk.embedding.is_not(None)).order_by(distance).limit(settings.retrieval_vector_k)
    vector_rows = (await session.execute(vector_stmt)).all()
    timings["vector"] = int((time.perf_counter() - started) * 1000)

    # --- lexical (tsvector, BM25-like cover density ranking) ---
    started = time.perf_counter()
    lexical_rows = []
    ts_expression = build_or_tsquery(query)
    if ts_expression:
        ts_query = func.to_tsquery("english", ts_expression)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, ts_query, 32)
        lexical_stmt = (
            _scoped(select(DocumentChunk.id, rank.label("score")), deal_id, categories, document_ids)
            .where(DocumentChunk.search_vector.op("@@")(ts_query))
            .order_by(rank.desc())
            .limit(settings.retrieval_lexical_k)
        )
        lexical_rows = (await session.execute(lexical_stmt)).all()
    timings["lexical"] = int((time.perf_counter() - started) * 1000)

    # --- Reciprocal Rank Fusion ---
    fused: dict[int, float] = {}
    vector_scores: dict[int, float] = {}
    lexical_scores: dict[int, float] = {}
    for rank_position, (chunk_id, score) in enumerate(vector_rows, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (settings.retrieval_rrf_k + rank_position)
        vector_scores[chunk_id] = float(score)
    for rank_position, (chunk_id, score) in enumerate(lexical_rows, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (settings.retrieval_rrf_k + rank_position)
        lexical_scores[chunk_id] = float(score)

    if not fused:
        return RetrievalResult(query=query, chunks=[], timings_ms=timings)

    candidate_ids = [cid for cid, _ in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)]
    candidate_ids = candidate_ids[: settings.retrieval_rerank_candidates]

    rows = (
        await session.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.page_number,
                DocumentChunk.section,
                DocumentChunk.content,
                Document.filename,
                Document.category,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(candidate_ids))
        )
    ).all()
    by_id = {
        row.id: RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            filename=row.filename,
            category=str(row.category),
            page_number=row.page_number,
            section=row.section,
            content=row.content,
            vector_score=vector_scores.get(row.id),
            lexical_score=lexical_scores.get(row.id),
            fused_score=fused[row.id],
        )
        for row in rows
    }
    candidates = [by_id[cid] for cid in candidate_ids if cid in by_id]

    # --- Cross-encoder reranking ---
    if use_reranker:
        started = time.perf_counter()
        scores = await reranker.rerank(query, [(c.chunk_id, _rerank_text(c)) for c in candidates])
        timings["rerank"] = int((time.perf_counter() - started) * 1000)
        if scores:
            for candidate in candidates:
                candidate.rerank_score = scores.get(candidate.chunk_id)
            candidates.sort(key=lambda c: (c.rerank_score or 0.0, c.fused_score), reverse=True)

    return RetrievalResult(query=query, chunks=candidates[:top_k], timings_ms=timings)


def _rerank_text(chunk: RetrievedChunk) -> str:
    header = f"{chunk.section}\n" if chunk.section else ""
    return f"{header}{chunk.content}"


def to_citation(index: int, chunk: RetrievedChunk, snippet_chars: int = 600) -> dict:
    snippet = chunk.content if len(chunk.content) <= snippet_chars else chunk.content[:snippet_chars].rsplit(" ", 1)[0] + "…"
    return {
        "index": index,
        "chunk_id": chunk.chunk_id,
        "document_id": str(chunk.document_id),
        "filename": chunk.filename,
        "category": chunk.category,
        "page_number": chunk.page_number,
        "section": chunk.section,
        "snippet": snippet,
        "score": round(chunk.score, 4),
    }
