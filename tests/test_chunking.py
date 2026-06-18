from __future__ import annotations

import pytest

from trapo.ingest.chunking import chunk_text


def test_chunk_text_overlaps() -> None:
    chunks = chunk_text("abcdefghij", max_chars=6, overlap_chars=2)

    assert chunks == ["abcdef", "efghij"]


def test_chunk_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_text("abc", max_chars=3, overlap_chars=3)
