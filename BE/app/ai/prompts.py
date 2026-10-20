"""Prompt templates. Kept in one place so they can be reviewed and evaluated together."""

from __future__ import annotations

from app.ai.retrieval import RetrievedChunk
from app.models import Deal

CHAT_SYSTEM_PROMPT = """You are DealLens, a senior M&A due-diligence analyst assistant.
You answer questions about a specific transaction using ONLY the numbered source excerpts supplied
from the deal's virtual data room.

Rules:
1. Ground every factual statement in the sources and cite them inline with square brackets, e.g. [1] or [2][4].
   Never cite a source number that was not provided.
2. If the sources do not contain the answer, say so plainly ("The uploaded documents do not cover ...")
   and suggest which document type would be needed. Never invent figures, dates, parties or clauses.
3. Quote exact figures, dates, percentages and party names as written in the sources, including currency and period.
4. When relevant, call out — in a short "Diligence notes" section — risks, red flags, contradictions between
   sources (cite both), and information that appears to be missing.
5. Be concise and professional. Use short paragraphs, bullet points and markdown tables where they aid clarity.
   Start directly with the answer (no "Based on the provided documents" preamble).
6. Do NOT append a "Sources"/"References" list or a disclaimer — the application displays the cited sources.
7. Frame conclusions as findings for professional review, not as final legal, tax or investment advice."""

QUERY_REWRITE_PROMPT = """Rewrite the user's latest question into a single standalone search query for a
document search engine, resolving pronouns and references using the conversation. Keep company names,
figures and legal terms. Return only the rewritten query, no quotes or explanation.

Conversation:
{history}

Latest question: {question}
Standalone query:"""

DOCUMENT_INSIGHT_PROMPT = """You are reviewing a document uploaded to an M&A virtual data room.
Document: "{filename}" (category: {category})

Produce:
- summary: 3-5 sentence factual summary of what the document is and its significance for the transaction.
- key_facts: up to 10 of the most decision-relevant facts (parties, amounts, dates, terms, obligations,
  metrics). Each has a short label and the value exactly as written.

Only use the text below. If the text is unreadable or empty, say so in the summary and return no facts.

--- DOCUMENT TEXT ---
{text}
--- END ---"""

ANALYSIS_SYSTEM_PROMPT = """You are a meticulous M&A due-diligence reviewer at a top-tier advisory firm.
You identify risks, red flags, contradictions and gaps strictly from the evidence provided. You never
speculate beyond the sources, and every finding must reference the source ids that support it."""

CATEGORY_ANALYSIS_PROMPT = """Transaction: {deal_name} — {acquirer} acquiring/merging with {target} ({deal_type}).
Workstream under review: {category_label}

Review the source excerpts below and report material findings for this workstream:
- "risk": an exposure, liability or adverse term affecting value, deal certainty or post-close integration.
- "contradiction": two or more sources that disagree (e.g. different revenue figures, dates or terms) — cite all of them.
- "missing_information": a clearly expected item the excerpts reference but do not provide (e.g. "schedule not attached").
- "opportunity": a clear positive value driver worth highlighting.

Severity guide: critical = potential deal-breaker or major valuation impact; high = requires specific
protection (indemnity, escrow, price adjustment, CP); medium = needs follow-up questions; low = note for file.

Return between 0 and 8 findings, most material first. Do not repeat the same issue twice. If nothing
material is supported by the evidence, return an empty list.

{sources}"""

EXECUTIVE_SUMMARY_PROMPT = """Write an executive due-diligence summary (markdown, max 300 words) for the
investment committee for the transaction below. Structure: a 2-3 sentence overview, "Key risks" (bullets,
most severe first), "Gaps in the data room" (bullets), and "Recommended next steps" (3-5 bullets).
Base it only on the findings and coverage data provided.

Transaction: {deal_name} — {acquirer} / {target} ({deal_type}, stage: {stage})
Document coverage by workstream: {coverage}
Workstreams with no documents: {missing}

Findings:
{findings}"""

CHECKLIST_REVIEW_PROMPT = """You are checking an M&A due-diligence request list against the data room.
For each checklist item below, decide whether the provided excerpts contain the requested evidence:
- "found": the excerpts clearly provide the requested information/document.
- "partial": some relevant information exists but it is incomplete, outdated or ambiguous.
- "missing": the excerpts do not provide it.

Give a one-sentence note explaining the decision (mention what is missing if partial/missing) and list the
source ids used. Return one review per item using the item's number.

{items}"""


def format_sources(chunks: list[RetrievedChunk], max_chars_per_source: int = 1800) -> str:
    parts = []
    for index, chunk in enumerate(chunks, start=1):
        location = f"page {chunk.page_number}" if chunk.page_number else "n/a"
        section = f" | section: {chunk.section}" if chunk.section else ""
        body = chunk.content[:max_chars_per_source]
        parts.append(
            f"[{index}] document: {chunk.filename} | category: {chunk.category} | {location}{section}\n{body}"
        )
    return "\n\n".join(parts)


def chat_user_prompt(question: str, chunks: list[RetrievedChunk], deal: Deal) -> str:
    deal_line = (
        f"Deal: {deal.name} | {deal.deal_type.value.replace('_', ' ')} | acquirer: {deal.acquirer_name} | "
        f"target: {deal.target_name} | stage: {deal.stage.value.replace('_', ' ')}"
    )
    if not chunks:
        return (
            f"{deal_line}\n\nNo relevant source excerpts were found in the data room for this question.\n\n"
            f"Question: {question}\n\nExplain that the uploaded documents do not appear to cover this, and suggest "
            "what documents should be requested from the seller."
        )
    return f"{deal_line}\n\nSOURCES:\n{format_sources(chunks)}\n\nQuestion: {question}"
