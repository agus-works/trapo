from __future__ import annotations

import json
import re

from rapidfuzz import fuzz

from trapo.search_models import SearchHighlight, SnippetMatch


FUZZY_HIGHLIGHT_SCORE = 0.35
GLOBAL_SCORE_DIVISOR = 5.0
SHORT_TEXT_HIGHLIGHT_LIMIT = 160
SNIPPET_LEADING_CONTEXT = 40


def highlight_text(
    query: str | None, text: str, *, field: str
) -> list[SearchHighlight]:
    normalized_query = clean_query(query)
    highlights: list[SearchHighlight] = []
    if not normalized_query or not text:
        return highlights
    phrase_spans = _exact_phrase_spans(normalized_query, text)
    if phrase_spans:
        highlights = [
            SearchHighlight(
                field=field,
                start=start,
                end=end,
                match_kind="exact_phrase",
                source="exact_phrase",
                score_contribution=1.0,
            )
            for start, end in phrase_spans
        ]
    else:
        token_spans = _exact_token_spans(normalized_query, text)
        if token_spans:
            highlights = [
                SearchHighlight(
                    field=field,
                    start=start,
                    end=end,
                    match_kind="exact_token",
                    source="exact_token",
                    score_contribution=0.75,
                )
                for start, end in token_spans
            ]
        elif len(text) <= SHORT_TEXT_HIGHLIGHT_LIMIT:
            highlights = [
                SearchHighlight(
                    field=field,
                    start=start,
                    end=end,
                    match_kind="fuzzy_character",
                    source="fuzzy_alignment",
                    score_contribution=FUZZY_HIGHLIGHT_SCORE,
                )
                for start, end in _fuzzy_character_spans(normalized_query, text)
            ]
        else:
            highlights = [
                SearchHighlight(
                    field=field,
                    start=0,
                    end=min(len(text), SHORT_TEXT_HIGHLIGHT_LIMIT),
                    match_kind="chunk_context",
                    source="chunk_fallback",
                    score_contribution=0.1,
                )
            ]
    return highlights


def global_score(query: str, label: str, text: str, *, base: float) -> float:
    return (
        base
        + max(
            float(fuzz.WRatio(query, label)),
            float(fuzz.partial_ratio(query, text)),
        )
        / GLOBAL_SCORE_DIVISOR
    )


def snippet_match(
    text: str, query: str, *, field: str, length: int = 220
) -> SnippetMatch:
    if len(text) <= length:
        snippet = text
    else:
        start, end = _snippet_bounds(text, query, length=length)
        snippet = text[start:end].strip() or text[:length].strip()
    return SnippetMatch(
        snippet=snippet,
        highlights=tuple(highlight_text(query, snippet, field=field)),
    )


def clean_query(query: str | None) -> str:
    return " ".join((query or "").strip().lower().split())


def query_tokens(query: str) -> list[str]:
    return [token for token in re.findall(r"[\w.-]+", query.lower()) if token]


def like_query(query: str) -> str:
    return f"%{query.lower()}%"


def json_dict(value: object) -> dict[str, object]:
    parsed: object | None = value
    if value is None:
        parsed = None
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
    return parsed if isinstance(parsed, dict) else {}


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | str):
        return int(value)
    return None


def overlay_id(region_id: str) -> str:
    return region_id if region_id.startswith("region:") else f"region:{region_id}"


def _snippet_bounds(text: str, query: str, *, length: int) -> tuple[int, int]:
    lowered = text.lower()
    index = _first_query_index(query, lowered)
    start = max(0, index - SNIPPET_LEADING_CONTEXT)
    end = min(len(text), start + length)
    if end - start < length:
        start = max(0, end - length)
    return start, end


def _first_query_index(query: str, lowered_text: str) -> int:
    index = lowered_text.find(query.lower())
    if index >= 0:
        return index
    token_indexes = [
        lowered_text.find(token)
        for token in query_tokens(query)
        if lowered_text.find(token) >= 0
    ]
    return min(token_indexes) if token_indexes else 0


def _exact_phrase_spans(query: str, text: str) -> list[tuple[int, int]]:
    lowered = text.lower()
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = lowered.find(query, start)
        if index < 0:
            break
        spans.append((index, index + len(query)))
        start = index + max(1, len(query))
    return spans


def _exact_token_spans(query: str, text: str) -> list[tuple[int, int]]:
    tokens = set(query_tokens(query))
    if not tokens:
        return []
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"[\w.-]+", text):
        if match.group(0).lower() in tokens:
            spans.append((match.start(), match.end()))
    return spans


def _fuzzy_character_spans(query: str, text: str) -> list[tuple[int, int]]:
    normalized_text: list[tuple[str, int]] = [
        (character.lower(), index)
        for index, character in enumerate(text)
        if character.isalnum()
    ]
    query_chars = [character for character in query.lower() if character.isalnum()]
    if not normalized_text or not query_chars:
        return []
    used: set[int] = set()
    selected: list[int] = []
    cursor = 0
    for character in query_chars:
        match_index = _find_matching_char(normalized_text, character, cursor, used)
        if match_index is None:
            match_index = _find_matching_char(normalized_text, character, 0, used)
        if match_index is None:
            continue
        used.add(match_index)
        selected.append(normalized_text[match_index][1])
        cursor = match_index + 1
    selected.sort()
    return _merge_indices(selected)


def _find_matching_char(
    normalized_text: list[tuple[str, int]],
    character: str,
    start: int,
    used: set[int],
) -> int | None:
    for index in range(start, len(normalized_text)):
        if index not in used and normalized_text[index][0] == character:
            return index
    return None


def _merge_indices(indices: list[int]) -> list[tuple[int, int]]:
    if not indices:
        return []
    spans: list[tuple[int, int]] = []
    start = indices[0]
    end = start + 1
    for index in indices[1:]:
        if index == end:
            end += 1
            continue
        spans.append((start, end))
        start = index
        end = index + 1
    spans.append((start, end))
    return spans
