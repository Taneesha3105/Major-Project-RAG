import re

from app.core.config import settings
from app.retrieval.schemas import RetrievalMatch
from app.chat.guardrails import (
    QUERY_INTENT_BROAD_SUMMARY,
    QUERY_INTENT_CALCULATION_METHOD,
    QUERY_INTENT_COMPARISON,
    QUERY_INTENT_DEADLINE,
    QUERY_INTENT_INCLUSION_EXCLUSION,
    QUERY_INTENT_PROCESS_EXPLANATION,
    QUERY_INTENT_RESPONSIBILITY,
    QUERY_POLARITY_EXCLUDES,
    QUERY_POLARITY_FREE,
    QUERY_POLARITY_REQUIRES,
    QUERY_SUBTYPE_DEADLINE_FAST,
    QUERY_SUBTYPE_DEADLINE_STANDARD,
    QUERY_SUBTYPE_OVERVIEW,
)


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


def budget_chat_context(
    matches: list[RetrievalMatch],
    *,
    max_total_chars: int,
    max_chunks: int,
    max_chars_per_chunk: int,
) -> list[RetrievalMatch]:
    if not matches or max_total_chars <= 0 or max_chunks <= 0 or max_chars_per_chunk <= 0:
        return []

    remaining_chars = max_total_chars
    budgeted_matches: list[RetrievalMatch] = []

    for match in matches:
        if len(budgeted_matches) >= max_chunks or remaining_chars <= 0:
            break

        cleaned_text = match.chunk_text.strip()
        if not cleaned_text:
            continue

        allowed_chars = min(max_chars_per_chunk, remaining_chars)
        if len(cleaned_text) > allowed_chars:
            cleaned_text = _truncate_text(cleaned_text, allowed_chars)
        if not cleaned_text:
            continue

        budgeted_matches.append(match.model_copy(update={"chunk_text": cleaned_text}))
        remaining_chars -= len(cleaned_text)

    return budgeted_matches


def build_chat_prompt(
    question: str,
    matches: list[RetrievalMatch],
    *,
    intent: str | None = None,
    subtype: str | None = None,
    polarity: str | None = None,
) -> str:
    if not matches:
        context_block = "No relevant excerpts were retrieved."
    else:
        context_block = "\n\n".join(
            f"Source {index}:\n{match.chunk_text}"
            for index, match in enumerate(matches, start=1)
        )

    intent_rules = "".join(
        rule
        for rule in (
            _build_comparison_rules(question, intent),
            _build_responsibility_rules(question, intent),
            _build_deadline_rules(intent, subtype),
            _build_inclusion_rules(intent, polarity),
            _build_calculation_rules(intent),
            _build_process_rules(intent),
            _build_summary_rules(intent, subtype),
        )
        if rule
    )

    return (
        f"Document excerpts:\n{context_block}\n\n"
        f"Question:\n{question}\n\n"
        "Style rules:\n"
        "- Answer only from the document excerpts.\n"
        "- Answer for the end user, not for debugging.\n"
        "- Keep the answer concise, but include all directly relevant details needed to fully answer the question.\n"
        "- For short factual answers drawn from tables, charts, or benefit rows, rewrite the answer as a complete natural sentence.\n"
        "- Do not start those fact answers with bare dollar amounts, numbers, or labels like 'From network providers:'.\n"
        "- If the excerpts show multiple directly relevant values for the same benefit, such as in-network and out-of-network amounts, include each of them in the answer.\n"
        "- Do not mention sources, excerpts, filenames, chunk numbers, section names, or chapter names.\n"
        "- Do not say things like 'in this document', 'see Section 5.3', or 'as described in Chapter 4'.\n"
        "- Give the answer directly instead of referring the user back to the document structure.\n"
        "- If the excerpts are enough, answer confidently and stop.\n"
        f"- If the excerpts are missing or insufficient, reply exactly with: {settings.chat_no_context_response}\n"
        "- Do not add notes, caveats, side details, or follow-up commentary after the answer.\n"
        f"{intent_rules}\n"
        "Answer:"
    )


def _build_comparison_rules(question: str, intent: str | None) -> str:
    if intent not in {None, QUERY_INTENT_COMPARISON}:
        return ""
    if intent != QUERY_INTENT_COMPARISON and not _is_comparison_style_question(question):
        return ""
    compared_terms = _extract_compared_terms(question)
    direct_rule = ""
    if len(compared_terms) >= 2:
        direct_rule = (
            f'- For this comparison question, explain what "{compared_terms[0]}" means and what "{compared_terms[1]}" means directly.\n'
        )
    return (
        f"{direct_rule}"
        "- For comparison questions, explain each compared thing directly and keep the contrast clear.\n"
        '- Prefer a direct format such as: "Appeal is ..." and "Complaint is ..."\n'
        "- Do not add setup definitions for related internal terms unless they are necessary to define one of the compared terms.\n"
        "- Do not drift into unrelated background unless it is needed to define one of the compared items.\n"
    )


def _build_responsibility_rules(question: str, intent: str | None) -> str:
    if intent not in {None, QUERY_INTENT_RESPONSIBILITY}:
        return ""
    if intent != QUERY_INTENT_RESPONSIBILITY and not _is_responsibility_style_question(question):
        return ""
    return (
        "- For responsibility questions, answer who is responsible first.\n"
        "- If the excerpts show different actors for different cases, state each case briefly and clearly.\n"
    )


def _build_deadline_rules(intent: str | None, subtype: str | None) -> str:
    if intent != QUERY_INTENT_DEADLINE:
        return ""
    if subtype == QUERY_SUBTYPE_DEADLINE_FAST:
        nuance = "Keep any expedited or fast qualifier if the excerpts support it."
    elif subtype == QUERY_SUBTYPE_DEADLINE_STANDARD:
        nuance = "Keep any standard qualifier if the excerpts support it."
    else:
        nuance = "Keep the timing language exactly as supported by the excerpts."
    return (
        "- For deadline questions, answer with the time requirement first in a direct sentence.\n"
        f"- {nuance}\n"
        "- Do not replace the timing answer with downstream outcome details.\n"
    )


def _build_inclusion_rules(intent: str | None, polarity: str | None) -> str:
    if intent != QUERY_INTENT_INCLUSION_EXCLUSION:
        return ""
    if polarity == QUERY_POLARITY_EXCLUDES:
        return (
            "- For inclusion or exclusion questions, answer the asked direction directly.\n"
            "- For exclusion questions, answer the excluded or negative direction directly.\n"
            "- If the question asks what does not count or what is excluded, do not answer with what does count.\n"
            "- Do not answer with the opposite direction unless it is needed to avoid changing the meaning.\n"
        )
    if polarity == QUERY_POLARITY_REQUIRES:
        return (
            "- For requirement questions, answer yes or no first when the excerpts make it clear.\n"
            "- Then state the key condition or exception directly.\n"
        )
    if polarity == QUERY_POLARITY_FREE:
        return (
            "- For no-cost questions, answer yes or no first when the excerpts make it clear.\n"
            "- Then state the relevant cost condition directly.\n"
        )
    return (
        "- For inclusion questions, answer the asked direction directly.\n"
        "- If the excerpts provide a list, summarize the relevant included items and stop.\n"
    )


def _build_calculation_rules(intent: str | None) -> str:
    if intent != QUERY_INTENT_CALCULATION_METHOD:
        return ""
    return (
        "- For method or basis questions, explain the method directly.\n"
        "- Do not replace the method with a nearby example amount unless the excerpts say the amount is itself the method.\n"
    )


def _build_process_rules(intent: str | None) -> str:
    if intent not in {QUERY_INTENT_PROCESS_EXPLANATION, "appeal_depth_or_reimbursement"}:
        return ""
    return (
        "- Do not tell the user to see another section or chapter; summarize the needed process directly.\n"
        "- For process questions, answer with the main process, consequence, or next step in order.\n"
        "- For 'what happens if' questions, state the main consequence first, then the immediate next action if the excerpts provide one.\n"
    )


def _build_summary_rules(intent: str | None, subtype: str | None) -> str:
    if intent != QUERY_INTENT_BROAD_SUMMARY and subtype != QUERY_SUBTYPE_OVERVIEW:
        return ""
    return (
        "- Do not describe the answer as being 'in this document'; give the summary directly.\n"
        "- For overview questions, give a short grounded summary of the main topic.\n"
        "- Do not answer with one narrow exception if the excerpts show a broader overview.\n"
    )


def _is_comparison_style_question(question: str) -> bool:
    lowered_question = question.lower()
    return any(marker in lowered_question for marker in COMPARISON_QUERY_MARKERS)


def _is_responsibility_style_question(question: str) -> bool:
    lowered_question = question.strip().lower()
    return lowered_question.startswith(RESPONSIBILITY_QUERY_PREFIXES)


def _extract_compared_terms(question: str) -> list[str]:
    lowered_question = question.lower()
    match = re.search(r"difference\s+between\s+(.+?)\s+and\s+(.+?)(?:\?|$)", lowered_question)
    if match is None:
        return []
    cleaned_terms = []
    for value in (match.group(1), match.group(2)):
        cleaned = re.sub(r"^(?:an?|the)\s+", "", value.strip())
        cleaned_terms.append(cleaned)
    return cleaned_terms


def _truncate_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."
