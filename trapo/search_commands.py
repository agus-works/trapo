from __future__ import annotations

from rapidfuzz import fuzz

from trapo.search_models import (
    MAX_SEARCH_LIMIT,
    CommandAction,
    CommandDefinition,
    CommandSearchResult,
)
from trapo.search_text import clean_query, highlight_text


COMMAND_DEFAULT_SCORE = 70.0
COMMAND_EXACT_LABEL_SCORE = 120.0
COMMAND_ALIAS_SCORE = 115.0
COMMAND_HAYSTACK_WEIGHT = 0.92
COMMAND_PARTIAL_WEIGHT = 0.86
MAX_DESCRIPTION_HIGHLIGHTS = 3
MIN_COMMAND_MATCH_SCORE = 30.0


STATIC_COMMANDS: tuple[CommandDefinition, ...] = (
    CommandDefinition(
        command_id="nav.documents",
        label="Open Documents",
        description="Open the document explorer and preview.",
        group="Navigation",
        aliases=("files", "pdfs", "sources", "documents"),
        keywords=("document", "preview", "search", "explorer"),
        action=CommandAction(type="navigate", route="/"),
    ),
)


def search_commands(query: str | None, *, limit: int = 20) -> list[CommandSearchResult]:
    normalized_query = clean_query(query)
    results: list[CommandSearchResult] = []
    for command in STATIC_COMMANDS:
        score = _command_score(normalized_query, command)
        if normalized_query and score < MIN_COMMAND_MATCH_SCORE:
            continue
        highlights = tuple(
            highlight_text(normalized_query, command.label, field="label")
        )
        if not highlights and normalized_query:
            highlights = tuple(
                highlight_text(
                    normalized_query, command.haystack(), field="description"
                )[:MAX_DESCRIPTION_HIGHLIGHTS]
            )
        results.append(
            CommandSearchResult(
                command_id=command.command_id,
                label=command.label,
                description=command.description,
                group=command.group,
                score=score,
                action=command.action,
                highlights=highlights,
                shortcut=command.shortcut,
            )
        )
    results.sort(key=lambda item: (-item.score, item.group, item.label))
    return results[: max(1, min(limit, MAX_SEARCH_LIMIT))]


def _command_score(query: str, command: CommandDefinition) -> float:
    score = COMMAND_DEFAULT_SCORE
    if query:
        label = command.label.lower()
        if label == query:
            score = COMMAND_EXACT_LABEL_SCORE
        elif any(query == alias.lower() for alias in command.aliases):
            score = COMMAND_ALIAS_SCORE
        else:
            label_score = float(fuzz.WRatio(query, command.label))
            haystack_score = float(fuzz.WRatio(query, command.haystack()))
            partial_score = float(fuzz.partial_ratio(query, command.haystack()))
            score = max(
                label_score,
                haystack_score * COMMAND_HAYSTACK_WEIGHT,
                partial_score * COMMAND_PARTIAL_WEIGHT,
            )
    return score
