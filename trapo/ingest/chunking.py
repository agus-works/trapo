from __future__ import annotations

from typing import Any

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer

from trapo.token_estimator import estimate_text_tokens


class HeuristicTokenizer(BaseTokenizer):
    max_tokens: int

    def count_tokens(self, text: str) -> int:
        return estimate_text_tokens(text)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> None:
        return None


def chunk_docling_document(
    document: Any,
    *,
    max_tokens: int = 1200,
    merge_peers: bool = True,
) -> list[tuple[str, dict[str, Any]]]:
    chunker = HybridChunker(
        tokenizer=HeuristicTokenizer(max_tokens=max_tokens),
        merge_peers=merge_peers,
    )
    chunks: list[tuple[str, dict[str, Any]]] = []
    for chunk in chunker.chunk(dl_doc=document):
        text = str(chunk.text).strip()
        if not text:
            continue
        metadata: dict[str, Any] = {"chunker": "docling-hybrid-v1"}
        if getattr(chunk, "meta", None) is not None:
            meta = chunk.meta
            metadata["docling_meta"] = (
                meta.model_dump(mode="json")
                if hasattr(meta, "model_dump")
                else str(meta)
            )
        for part_index, part in enumerate(
            _split_oversized_text(text, max_tokens=max_tokens)
        ):
            part_metadata = dict(metadata)
            if len(part) != len(text):
                part_metadata["split_from_docling_chunk"] = True
                part_metadata["split_part_index"] = part_index
            chunks.append((part, part_metadata))
    return chunks


def _split_oversized_text(text: str, *, max_tokens: int) -> list[str]:
    if estimate_text_tokens(text) <= max_tokens:
        return [text]

    parts: list[str] = []
    current = ""
    for block in text.splitlines():
        candidate = f"{current}\n{block}".strip() if current else block.strip()
        if not candidate:
            continue
        if estimate_text_tokens(candidate) <= max_tokens:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if estimate_text_tokens(block) <= max_tokens:
            current = block.strip()
            continue
        parts.extend(_split_long_block(block, max_tokens=max_tokens))
    if current:
        parts.append(current)
    return [part for part in parts if part.strip()]


def _split_long_block(text: str, *, max_tokens: int) -> list[str]:
    words = text.split()
    parts: list[str] = []
    current_words: list[str] = []
    for word in words:
        candidate_words = [*current_words, word]
        candidate = " ".join(candidate_words)
        if estimate_text_tokens(candidate) <= max_tokens:
            current_words = candidate_words
            continue
        if current_words:
            parts.append(" ".join(current_words))
        current_words = [word]
    if current_words:
        parts.append(" ".join(current_words))
    return parts


def chunk_text(
    text: str, *, max_chars: int = 4000, overlap_chars: int = 400
) -> list[str]:
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not normalized:
        return []
    if max_chars <= overlap_chars:
        raise ValueError("max_chars must be greater than overlap_chars.")

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]
