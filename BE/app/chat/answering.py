from __future__ import annotations

from dataclasses import dataclass
import re

from app.chat.guardrails import (
    QUERY_INTENT_BROAD_SUMMARY,
    QUERY_INTENT_CALCULATION_METHOD,
    QUERY_INTENT_COMPARISON,
    QUERY_INTENT_DEADLINE,
    QUERY_INTENT_DEFAULT_FACT,
    QUERY_INTENT_INCLUSION_EXCLUSION,
    QUERY_INTENT_PROCESS_EXPLANATION,
    QUERY_INTENT_RESPONSIBILITY,
    QUERY_POLARITY_EXCLUDES,
    QUERY_POLARITY_FREE,
    QUERY_POLARITY_REQUIRES,
    QUERY_SUBTYPE_DEADLINE_FAST,
    QUERY_SUBTYPE_DEADLINE_STANDARD,
    QUERY_SUBTYPE_OVERVIEW,
    QueryRoute,
)
from app.core.config import settings
from app.retrieval.schemas import RetrievalMatch


TIME_PHRASE_PATTERN = re.compile(
    r"\bwithin\s+\d+\s+(?:hour|hours|calendar\s+day|calendar\s+days|day|days|month|months|year|years)\b",
    re.IGNORECASE,
)
STRUCTURED_VALUE_PATTERN = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?%")
METHOD_PHRASES = ("means", "based on", "based upon", "calculated", "determined", "computed", "percentage of")
RESPONSIBILITY_PHRASES = ("responsible for", "responsibility of", "must", "has to", "required to")
PROCESS_PHRASES = ("if", "when", "then", "process", "step", "follow", "must", "can", "will")
POSITIVE_POLARITY_PHRASES = ("included", "covered", "allowed", "count toward", "counts toward")
NEGATIVE_POLARITY_PHRASES = ("excluded", "not covered", "does not", "do not", "doesn't", "without")
REQUIREMENT_PHRASES = ("required", "must", "need", "needs", "permission", "approval", "authorization")
FREE_PHRASES = ("$0", "free", "no cost", "at no cost")
DOCUMENT_REFERENCE_PATTERNS = (
    re.compile(r"\bsection\s+\d+(?:\.\d+)*\b", re.IGNORECASE),
    re.compile(r"\bchapter\s+\d+(?:\.\d+)*\b", re.IGNORECASE),
    re.compile(r"\bpage\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bsource\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bchunk\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bfilenames?\b", re.IGNORECASE),
    re.compile(r"\bprovided excerpts?\b", re.IGNORECASE),
    re.compile(r"\bprovided context\b", re.IGNORECASE),
    re.compile(r"\bin this document\b", re.IGNORECASE),
    re.compile(r"\bthis document\b", re.IGNORECASE),
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
QUESTION_TERM_STOP_WORDS = {
    "about",
    "answer",
    "does",
    "give",
    "kinds",
    "main",
    "must",
    "tell",
    "that",
    "their",
    "this",
    "under",
    "what",
    "when",
    "where",
    "which",
    "work",
    "works",
    "would",
    "should",
    "could",
}


@dataclass(slots=True)
class AnswerPolicyOutcome:
    answer: str
    rejected: bool


def is_specialized_route(route: QueryRoute) -> bool:
    return route.intent in {
        QUERY_INTENT_BROAD_SUMMARY,
        QUERY_INTENT_CALCULATION_METHOD,
        QUERY_INTENT_COMPARISON,
        QUERY_INTENT_DEADLINE,
        QUERY_INTENT_INCLUSION_EXCLUSION,
        QUERY_INTENT_PROCESS_EXPLANATION,
        QUERY_INTENT_RESPONSIBILITY,
    }


def is_composer_allowed(route: QueryRoute) -> bool:
    del route
    return False


def build_compact_evidence_matches(
    question: str,
    route: QueryRoute,
    matches: list[RetrievalMatch],
    *,
    max_matches: int = 3,
    max_chars_per_match: int = 500,
) -> list[RetrievalMatch]:
    if not matches:
        return []

    question_terms = _extract_question_terms(question)
    compact_matches: list[RetrievalMatch] = []

    for match in matches:
        cue_hits = _collect_cue_hits(question, route, match.chunk_text)
        if _should_preserve_structured_fact_text(question, route, match):
            trimmed_text = match.chunk_text[:max_chars_per_match]
        else:
            trimmed_text = _trim_to_relevant_fragments(
                match.chunk_text,
                cue_hits=cue_hits,
                question_terms=question_terms,
                route=route,
                max_chars=max_chars_per_match,
            )
        metadata = dict(match.metadata)
        if route.subtype is not None:
            metadata.setdefault("support_subtype", route.subtype)
        if cue_hits:
            metadata["cue_hits"] = cue_hits
        compact_matches.append(
            match.model_copy(
                update={
                    "chunk_text": trimmed_text or match.chunk_text[:max_chars_per_match],
                    "metadata": metadata,
                }
            )
        )
        if len(compact_matches) >= max_matches:
            break

    return compact_matches


def evidence_signature_passes(question: str, route: QueryRoute, matches: list[RetrievalMatch]) -> bool:
    if not matches:
        return False

    lowered_text = " ".join(match.chunk_text.lower() for match in matches)
    question_terms = _extract_question_terms(question)
    matched_terms = sum(1 for term in question_terms if term in lowered_text)

    if route.intent == QUERY_INTENT_DEADLINE:
        if not TIME_PHRASE_PATTERN.search(lowered_text):
            return False
        if route.subtype == QUERY_SUBTYPE_DEADLINE_FAST:
            return "fast" in lowered_text or "expedited" in lowered_text
        if route.subtype == QUERY_SUBTYPE_DEADLINE_STANDARD:
            return "standard" in lowered_text or "regular" in lowered_text or "normal" in lowered_text
        return True

    if route.intent == QUERY_INTENT_RESPONSIBILITY:
        return any(phrase in lowered_text for phrase in RESPONSIBILITY_PHRASES)

    if route.intent == QUERY_INTENT_CALCULATION_METHOD:
        return any(phrase in lowered_text for phrase in METHOD_PHRASES)

    if route.intent == QUERY_INTENT_INCLUSION_EXCLUSION:
        if route.polarity == QUERY_POLARITY_EXCLUDES:
            return any(phrase in lowered_text for phrase in NEGATIVE_POLARITY_PHRASES)
        if route.polarity == QUERY_POLARITY_REQUIRES:
            return any(phrase in lowered_text for phrase in REQUIREMENT_PHRASES)
        if route.polarity == QUERY_POLARITY_FREE:
            return any(phrase in lowered_text for phrase in FREE_PHRASES)
        return any(phrase in lowered_text for phrase in POSITIVE_POLARITY_PHRASES)

    if route.intent == QUERY_INTENT_PROCESS_EXPLANATION:
        return matched_terms >= max(1, min(2, len(question_terms))) and any(
            phrase in lowered_text for phrase in PROCESS_PHRASES
        )

    if route.intent == QUERY_INTENT_BROAD_SUMMARY or route.subtype == QUERY_SUBTYPE_OVERVIEW:
        return bool(_extract_overview_items(matches)) or matched_terms >= max(1, min(2, len(question_terms)))

    return matched_terms >= max(1, min(2, len(question_terms)))


def compose_answer(question: str, route: QueryRoute, matches: list[RetrievalMatch]) -> str | None:
    del question, route, matches
    return None


def apply_answer_policy(answer: str, route: QueryRoute, *, composer_answer: str | None = None) -> AnswerPolicyOutcome:
    candidate = _sanitize_answer(answer)
    if candidate and not _violates_answer_policy(candidate):
        return AnswerPolicyOutcome(answer=candidate, rejected=candidate != answer)

    if composer_answer:
        return AnswerPolicyOutcome(answer=composer_answer, rejected=True)

    if route.intent == QUERY_INTENT_BROAD_SUMMARY or route.subtype == QUERY_SUBTYPE_OVERVIEW:
        return AnswerPolicyOutcome(answer=settings.chat_clarification_response, rejected=True)

    return AnswerPolicyOutcome(answer=settings.chat_no_context_response, rejected=True)


def _extract_question_terms(question: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9']+", question.lower())
        if len(token) >= 4 and token not in QUESTION_TERM_STOP_WORDS
    ]


def _should_preserve_structured_fact_text(question: str, route: QueryRoute, match: RetrievalMatch) -> bool:
    if route.intent != QUERY_INTENT_DEFAULT_FACT:
        return False
    question_facets = _extract_question_facets(question)
    lowered_text = match.chunk_text.lower()
    has_value_marker = bool(STRUCTURED_VALUE_PATTERN.search(match.chunk_text))
    has_label_metadata = bool(match.metadata.get("label_value_row") or match.metadata.get("table_like_row"))
    has_facet_overlap = any(facet in lowered_text for facet in question_facets)
    return has_value_marker and (has_label_metadata or has_facet_overlap)


def _collect_cue_hits(question: str, route: QueryRoute, text: str) -> list[str]:
    lowered_text = text.lower()
    question_terms = _extract_question_terms(question)
    question_facets = _extract_question_facets(question)
    cue_hits: list[str] = []

    for term in question_terms:
        if term in lowered_text and term not in cue_hits:
            cue_hits.append(term)
    for facet in question_facets:
        if facet in lowered_text and facet not in cue_hits:
            cue_hits.append(facet)

    if route.intent == QUERY_INTENT_DEADLINE:
        for marker in ("within", "deadline", "hours", "days", "months", "years", "fast", "standard", "expedited"):
            if marker in lowered_text and marker not in cue_hits:
                cue_hits.append(marker)
    elif route.intent == QUERY_INTENT_RESPONSIBILITY:
        for marker in RESPONSIBILITY_PHRASES:
            if marker in lowered_text and marker not in cue_hits:
                cue_hits.append(marker)
    elif route.intent == QUERY_INTENT_CALCULATION_METHOD:
        for marker in METHOD_PHRASES:
            if marker in lowered_text and marker not in cue_hits:
                cue_hits.append(marker)
    elif route.intent == QUERY_INTENT_INCLUSION_EXCLUSION:
        marker_pool = POSITIVE_POLARITY_PHRASES + NEGATIVE_POLARITY_PHRASES + REQUIREMENT_PHRASES + FREE_PHRASES
        for marker in marker_pool:
            if marker in lowered_text and marker not in cue_hits:
                cue_hits.append(marker)
    elif route.intent == QUERY_INTENT_PROCESS_EXPLANATION:
        for marker in PROCESS_PHRASES:
            if marker in lowered_text and marker not in cue_hits:
                cue_hits.append(marker)

    time_match = TIME_PHRASE_PATTERN.search(text)
    if time_match is not None and time_match.group(0).lower() not in cue_hits:
        cue_hits.append(time_match.group(0).lower())

    return cue_hits


def _trim_to_relevant_fragments(
    text: str,
    *,
    cue_hits: list[str],
    question_terms: list[str],
    route: QueryRoute,
    max_chars: int,
) -> str:
    fragments = _split_fragments(text)
    if not fragments:
        return ""

    selected_indexes: set[int] = set()
    for index, fragment in enumerate(fragments):
        lowered_fragment = fragment.lower()
        if any(cue in lowered_fragment for cue in cue_hits) or any(term in lowered_fragment for term in question_terms):
            selected_indexes.update({max(0, index - 1), index, min(len(fragments) - 1, index + 1)})
        elif route.intent == QUERY_INTENT_BROAD_SUMMARY and _looks_like_bullet(fragment):
            selected_indexes.add(index)

    if not selected_indexes:
        selected_indexes = set(range(min(len(fragments), 2)))

    chosen_fragments: list[str] = []
    current_length = 0
    for index in sorted(selected_indexes):
        fragment = fragments[index]
        fragment_length = len(fragment) + (1 if chosen_fragments else 0)
        if current_length + fragment_length > max_chars and chosen_fragments:
            break
        chosen_fragments.append(fragment)
        current_length += fragment_length

    joiner = "\n" if route.intent == QUERY_INTENT_BROAD_SUMMARY else " "
    return joiner.join(chosen_fragments).strip()


def _split_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    normalized_text = text.replace("\r\n", "\n")
    for raw_line in normalized_text.split("\n"):
        stripped_line = re.sub(r"\s+", " ", raw_line).strip()
        if not stripped_line:
            continue
        if _looks_like_bullet(stripped_line) or len(stripped_line) <= 180 or STRUCTURED_VALUE_PATTERN.search(stripped_line):
            fragments.append(stripped_line)
            continue
        fragments.extend(part for part in SENTENCE_SPLIT_PATTERN.split(stripped_line) if part.strip())
    return fragments


def _looks_like_bullet(text: str) -> bool:
    return bool(
        text.startswith(("â€¢", "-", "*"))
        or re.match(r"^[^A-Za-z0-9]{1,3}\s+", text)
        or re.match(r"^[A-Z][A-Za-z0-9 /&()'\"-]+:\s*$", text)
    )


def _extract_question_facets(question: str) -> list[str]:
    lowered_question = question.lower()
    facets: list[str] = []
    for pattern in (
        r"\btier\s+\d+\b",
        r"\blevel\s+\d+\b",
        r"\bpart\s+[a-z0-9]+\b",
        r"\b(?:initial|catastrophic|deductible)\s+coverage\s+stage\b",
        r"\bcoverage\s+stage\b",
        r"\bin-network\b",
        r"\bout-of-network\b",
        r"\b\d+-day\b",
    ):
        for match in re.findall(pattern, lowered_question):
            if match not in facets:
                facets.append(match)
    return facets


def _extract_overview_items(matches: list[RetrievalMatch]) -> list[str]:
    items: list[str] = []
    for match in matches:
        for fragment in _split_fragments(match.chunk_text):
            if _looks_like_bullet(fragment):
                cleaned = re.sub(r"^(?:â€¢|-|\*)\s*", "", fragment).strip()
                if cleaned and cleaned not in items:
                    items.append(cleaned.rstrip("."))
    return items


def _sanitize_answer(answer: str) -> str:
    candidate = re.sub(r"\s+", " ", answer).strip()
    return candidate


def _violates_answer_policy(answer: str) -> bool:
    return any(pattern.search(answer) for pattern in DOCUMENT_REFERENCE_PATTERNS)
