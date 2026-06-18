from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


HighlightSource = Literal[
    "exact_phrase",
    "exact_token",
    "fuzzy_alignment",
    "fts_term",
    "region_fallback",
    "chunk_fallback",
]
NavigationGranularity = Literal["word", "region", "chunk", "file", "record"]
MAX_SEARCH_LIMIT = 100


@dataclass(frozen=True)
class SearchHighlight:
    field: str
    start: int
    end: int
    match_kind: str
    source: HighlightSource
    score_contribution: float = 0.0


@dataclass(frozen=True)
class SnippetMatch:
    snippet: str
    highlights: tuple[SearchHighlight, ...]


@dataclass(frozen=True)
class CommandAction:
    type: str
    route: str | None = None
    search: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandDefinition:
    command_id: str
    label: str
    description: str
    group: str
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]
    action: CommandAction
    shortcut: str | None = None

    def haystack(self) -> str:
        return " ".join(
            [
                self.command_id,
                self.label,
                self.description,
                self.group,
                self.action.route or "",
                " ".join(self.aliases),
                " ".join(self.keywords),
            ]
        )


@dataclass(frozen=True)
class CommandSearchResult:
    command_id: str
    label: str
    description: str
    group: str
    score: float
    action: CommandAction
    highlights: tuple[SearchHighlight, ...]
    shortcut: str | None = None


@dataclass(frozen=True)
class GlobalSearchResult:
    result_id: str
    source_type: str
    source_id: str
    label: str
    snippet: str
    route: dict[str, object]
    score: float
    rank_source: str
    navigation_granularity: NavigationGranularity
    highlights: tuple[SearchHighlight, ...]
    file_hash: str | None = None
    chunk_id: int | None = None
    region_id: str | None = None
    page_no: int | None = None
    word_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentChunkResultInput:
    chunk_id: int
    file_hash: str
    text: str
    filename: str
    region_id: str | None
    page_no: int | None
    score: float
    rank_source: str


@dataclass(frozen=True)
class DocumentRegionResultInput:
    region_id: str
    file_hash: str
    filename: str
    text: str
    context_text: str
    label: str
    annotation_engine: str
    chunk_id: int | None
    page_no: int
    score: float
    rank_source: str


@dataclass(frozen=True)
class PageMarkdownResultInput:
    file_hash: str
    filename: str
    page_no: int
    markdown_engine: str
    markdown_provider: str
    markdown_model: str
    markdown_text: str
    score: float
    rank_source: str
