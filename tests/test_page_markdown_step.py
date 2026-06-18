from __future__ import annotations

from trapo.ingest.page_markdown_step import (
    PageMarkdownSummary,
    _combine_page_markdown_summaries,
)

LMSTUDIO_PARTIAL_PAGES = 30
MARKITDOWN_COMPLETE_PAGES = 63
COMBINED_PAGE_ROWS = LMSTUDIO_PARTIAL_PAGES + MARKITDOWN_COMPLETE_PAGES
EXPECTED_ERROR_COUNT = 3


def test_page_markdown_summary_ignores_degraded_engine_when_fallback_succeeds() -> None:
    summary = _combine_page_markdown_summaries(
        [
            PageMarkdownSummary(
                page_count=LMSTUDIO_PARTIAL_PAGES,
                error_count=33,
                errors=[{"page_no": 3, "error": "empty structured output"}],
            ),
            PageMarkdownSummary(page_count=MARKITDOWN_COMPLETE_PAGES),
        ]
    )

    assert summary.page_count == COMBINED_PAGE_ROWS
    assert summary.error_count == 0
    assert summary.errors == [{"page_no": 3, "error": "empty structured output"}]


def test_page_markdown_summary_counts_errors_without_complete_fallback() -> None:
    summary = _combine_page_markdown_summaries(
        [
            PageMarkdownSummary(page_count=LMSTUDIO_PARTIAL_PAGES, error_count=2),
            PageMarkdownSummary(page_count=0, error_count=1),
        ]
    )

    assert summary.page_count == LMSTUDIO_PARTIAL_PAGES
    assert summary.error_count == EXPECTED_ERROR_COUNT
