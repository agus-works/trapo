from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Any

from trapo.server.models import NormalizedBBox, PageInfo, RawBBox


@dataclass(frozen=True)
class EvidenceCandidate:
    source_ref: str
    parent_ref: str | None
    label: str | None
    text: str
    context_text: str
    page_no: int
    raw_bbox: RawBBox


@dataclass(frozen=True)
class DoclingEvidenceIndex:
    by_ref: dict[str, list[EvidenceCandidate]]
    by_parent_ref: dict[str, list[EvidenceCandidate]]

    def candidates_for_ref(self, source_ref: str) -> list[EvidenceCandidate]:
        direct = self.by_ref.get(source_ref, [])
        children = self.by_parent_ref.get(source_ref, [])
        return children or direct

    def all_candidates(self) -> list[EvidenceCandidate]:
        candidates: list[EvidenceCandidate] = []
        seen: set[tuple[str, int, float, float, float, float]] = set()
        for collection in [self.by_ref, self.by_parent_ref]:
            for values in collection.values():
                for candidate in values:
                    key = (
                        candidate.source_ref,
                        candidate.page_no,
                        candidate.raw_bbox.left,
                        candidate.raw_bbox.top,
                        candidate.raw_bbox.right,
                        candidate.raw_bbox.bottom,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)
        return candidates


@dataclass(frozen=True)
class PdfToken:
    text: str
    page_no: int
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class BBoxMatch:
    bbox: RawBBox
    score: float


@dataclass(frozen=True)
class BBoxRect:
    left: float
    top: float
    width: float
    height: float


SHORT_PDF_TOKEN_TARGET_LENGTH = 3
EXIF_MIRROR_HORIZONTAL = 2
EXIF_ROTATE_180 = 3
EXIF_MIRROR_VERTICAL = 4
EXIF_TRANSPOSE = 5
EXIF_ROTATE_90_CW = 6
EXIF_TRANSVERSE = 7
EXIF_ROTATE_90_CCW = 8


def parse_json_value(value: object) -> dict[str, Any]:
    parsed: object | None = value
    if value is None:
        parsed = None
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
    return parsed if isinstance(parsed, dict) else {}


def extract_pages(docling_json: object) -> list[PageInfo]:
    data = parse_json_value(docling_json)
    pages = data.get("pages")
    results: list[PageInfo] = []
    if isinstance(pages, list):
        for fallback_page_no, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            dimensions = page.get("dimensions")
            if not isinstance(dimensions, dict):
                continue
            width = _float_or_none(dimensions.get("width"))
            height = _float_or_none(dimensions.get("height"))
            if width is None or height is None:
                continue
            results.append(
                PageInfo(page_no=fallback_page_no, width=width, height=height)
            )
        return results
    if not isinstance(pages, dict):
        return results
    for fallback_page_no, page in enumerate(pages.values(), start=1):
        if not isinstance(page, dict):
            continue
        size = page.get("size")
        if not isinstance(size, dict):
            continue
        page_no = _int_or_none(page.get("page_no")) or fallback_page_no
        width = _float_or_none(size.get("width"))
        height = _float_or_none(size.get("height"))
        if width is None or height is None:
            continue
        results.append(PageInfo(page_no=page_no, width=width, height=height))
    return sorted(results, key=lambda item: item.page_no)


def build_docling_evidence_index(docling_json: object) -> DoclingEvidenceIndex:
    data = parse_json_value(docling_json)
    by_ref: dict[str, list[EvidenceCandidate]] = {}
    by_parent_ref: dict[str, list[EvidenceCandidate]] = {}
    _add_text_candidates(data, by_ref)
    _add_table_candidates(data, by_ref, by_parent_ref)
    return DoclingEvidenceIndex(by_ref=by_ref, by_parent_ref=by_parent_ref)


def evidence_candidates_from_chunk_metadata(
    *,
    chunk_text: str,
    metadata_json: object,
    docling_index: DoclingEvidenceIndex,
    pdf_path: Path | None = None,
    pages_by_no: dict[int, PageInfo] | None = None,
) -> list[EvidenceCandidate]:
    metadata = parse_json_value(metadata_json)
    docling_meta = metadata.get("docling_meta")
    candidates: list[EvidenceCandidate] = []
    if not isinstance(docling_meta, dict):
        candidates = _candidates_from_mistral_pdf_words(
            metadata, pdf_path, pages_by_no or {}
        )
        if candidates:
            return candidates
        candidates = _candidates_from_mistral_elements(metadata)
        if not candidates:
            candidates = _fallback_candidates_from_mistral_metadata(
                chunk_text, metadata
            )
    else:
        doc_items = docling_meta.get("doc_items")
        if isinstance(doc_items, list):
            seen: set[tuple[str, int, float, float, float, float]] = set()
            for doc_item in doc_items:
                if not isinstance(doc_item, dict):
                    continue
                source_ref = str(doc_item.get("self_ref") or "")
                for candidate in docling_index.candidates_for_ref(source_ref):
                    key = (
                        candidate.source_ref,
                        candidate.page_no,
                        candidate.raw_bbox.left,
                        candidate.raw_bbox.top,
                        candidate.raw_bbox.right,
                        candidate.raw_bbox.bottom,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)

            if not candidates:
                candidates = _fallback_candidates_from_chunk_metadata(
                    chunk_text, metadata
                )
    return candidates


def _add_text_candidates(
    data: dict[str, Any],
    by_ref: dict[str, list[EvidenceCandidate]],
) -> None:
    texts = data.get("texts")
    if not isinstance(texts, list):
        return
    for text_item in texts:
        if not isinstance(text_item, dict):
            continue
        source_ref = str(text_item.get("self_ref") or "")
        text = _candidate_text(text_item)
        if not source_ref or not text:
            continue
        provs = text_item.get("prov")
        if not isinstance(provs, list):
            continue
        label = str(text_item.get("label") or "") or None
        for prov in provs:
            if not isinstance(prov, dict):
                continue
            page_no = _int_or_none(prov.get("page_no"))
            raw_bbox_data = prov.get("bbox")
            if page_no is None or not isinstance(raw_bbox_data, dict):
                continue
            raw_bbox = _raw_bbox(raw_bbox_data)
            if raw_bbox is None:
                continue
            by_ref.setdefault(source_ref, []).append(
                EvidenceCandidate(
                    source_ref=source_ref,
                    parent_ref=None,
                    label=label,
                    text=text,
                    context_text=text,
                    page_no=page_no,
                    raw_bbox=raw_bbox,
                )
            )


# Docling table JSON has separate table, row, and cell shapes that must be
# normalized together; splitting further would hide the schema relationship.
def _add_table_candidates(  # noqa: PLR0912
    data: dict[str, Any],
    by_ref: dict[str, list[EvidenceCandidate]],
    by_parent_ref: dict[str, list[EvidenceCandidate]],
) -> None:
    tables = data.get("tables")
    if not isinstance(tables, list):
        return
    for table in tables:
        if not isinstance(table, dict):
            continue
        table_ref = str(table.get("self_ref") or "")
        if not table_ref:
            continue
        page_no = _first_page_no(table.get("prov"))
        if page_no is None:
            continue
        table_bbox = _first_bbox(table.get("prov"))
        if table_bbox is not None:
            by_ref.setdefault(table_ref, []).append(
                EvidenceCandidate(
                    source_ref=table_ref,
                    parent_ref=None,
                    label=str(table.get("label") or "table"),
                    text=_table_text(table),
                    context_text=_table_text(table),
                    page_no=page_no,
                    raw_bbox=table_bbox,
                )
            )

        data_section = table.get("data")
        if not isinstance(data_section, dict):
            continue
        cells = data_section.get("table_cells")
        if not isinstance(cells, list):
            continue
        row_text_by_index: dict[int, str] = {}
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            row_index = _int_or_none(cell.get("start_row_offset_idx"))
            text = _candidate_text(cell)
            if row_index is None or not text:
                continue
            row_text_by_index[row_index] = " ".join(
                part for part in (row_text_by_index.get(row_index), text) if part
            )
        for cell_index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                continue
            text = _candidate_text(cell)
            raw_bbox_data = cell.get("bbox")
            if not text or not isinstance(raw_bbox_data, dict):
                continue
            raw_bbox = _raw_bbox(raw_bbox_data)
            if raw_bbox is None:
                continue
            row_index = _int_or_none(cell.get("start_row_offset_idx"))
            source_ref = f"{table_ref}/cells/{cell_index}"
            candidate = EvidenceCandidate(
                source_ref=source_ref,
                parent_ref=table_ref,
                label="table_cell",
                text=text,
                context_text=row_text_by_index.get(row_index or -1, text),
                page_no=page_no,
                raw_bbox=raw_bbox,
            )
            by_ref.setdefault(source_ref, []).append(candidate)
            by_parent_ref.setdefault(table_ref, []).append(candidate)


def _fallback_candidates_from_chunk_metadata(
    chunk_text: str,
    metadata: dict[str, Any],
) -> list[EvidenceCandidate]:
    docling_meta = metadata.get("docling_meta")
    if not isinstance(docling_meta, dict):
        return []
    doc_items = docling_meta.get("doc_items")
    if not isinstance(doc_items, list):
        return []
    candidates: list[EvidenceCandidate] = []
    preview = " ".join(chunk_text.split())[:260]
    for item_index, doc_item in enumerate(doc_items):
        if not isinstance(doc_item, dict):
            continue
        source_ref = str(doc_item.get("self_ref") or f"chunk-item-{item_index}")
        label = str(doc_item.get("label") or "") or None
        provs = doc_item.get("prov")
        if not isinstance(provs, list):
            continue
        for prov_index, prov in enumerate(provs):
            if not isinstance(prov, dict):
                continue
            page_no = _int_or_none(prov.get("page_no"))
            raw_bbox_data = prov.get("bbox")
            if page_no is None or not isinstance(raw_bbox_data, dict):
                continue
            raw_bbox = _raw_bbox(raw_bbox_data)
            if raw_bbox is None:
                continue
            candidates.append(
                EvidenceCandidate(
                    source_ref=f"{source_ref}:prov:{prov_index}",
                    parent_ref=source_ref or None,
                    label=label,
                    text=preview,
                    context_text=preview,
                    page_no=page_no,
                    raw_bbox=raw_bbox,
                )
            )
    return candidates


def _fallback_candidates_from_mistral_metadata(
    chunk_text: str,
    metadata: dict[str, Any],
) -> list[EvidenceCandidate]:
    candidates = _candidates_from_mistral_elements(metadata)
    if candidates:
        return candidates
    pages = metadata.get("mistral_pages")
    if not isinstance(pages, list):
        return []
    preview = " ".join(chunk_text.split())[:260]
    candidates: list[EvidenceCandidate] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_no = _int_or_none(page.get("page_no"))
        bbox_data = page.get("bbox")
        if page_no is None or not isinstance(bbox_data, dict):
            continue
        raw_bbox = _raw_bbox(bbox_data)
        if raw_bbox is None:
            continue
        source_ref = str(page.get("source_ref") or f"mistral-page-{page_no}")
        candidates.append(
            EvidenceCandidate(
                source_ref=source_ref,
                parent_ref=None,
                label="mistral_ocr_page",
                text=preview,
                context_text=preview,
                page_no=page_no,
                raw_bbox=raw_bbox,
            )
        )
    return candidates


def _candidates_from_mistral_elements(
    metadata: dict[str, Any],
) -> list[EvidenceCandidate]:
    elements = metadata.get("mistral_elements")
    if not isinstance(elements, list):
        return []
    candidates: list[EvidenceCandidate] = []
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            continue
        page_no = _int_or_none(element.get("page_no"))
        bbox_data = element.get("bbox")
        if page_no is None or not isinstance(bbox_data, dict):
            continue
        raw_bbox = _raw_bbox(bbox_data)
        if raw_bbox is None:
            continue
        text = str(element.get("text") or "").strip()
        context_text = str(element.get("context_text") or text).strip()
        if not text and not context_text:
            continue
        candidates.append(
            EvidenceCandidate(
                source_ref=str(element.get("source_ref") or f"mistral-element-{index}"),
                parent_ref=str(element.get("parent_ref"))
                if element.get("parent_ref")
                else None,
                label=str(element.get("label") or "mistral_ocr_element"),
                text=text,
                context_text=context_text,
                page_no=page_no,
                raw_bbox=raw_bbox,
            )
        )
    return candidates


def _candidates_from_mistral_pdf_words(
    metadata: dict[str, Any],
    pdf_path: Path | None,
    pages_by_no: dict[int, PageInfo],
) -> list[EvidenceCandidate]:
    elements = metadata.get("mistral_elements")
    if not isinstance(elements, list) or pdf_path is None or not pdf_path.exists():
        return []
    tokens_by_page = _pdf_tokens_by_page(pdf_path, pages_by_no)
    if not tokens_by_page:
        return []

    rows = [
        element
        for element in elements
        if _mistral_label(element) == "mistral_ocr_table_row"
    ]
    cells = [
        element
        for element in elements
        if _mistral_label(element) == "mistral_ocr_table_cell"
    ]
    tables = [
        element
        for element in elements
        if _mistral_label(element) == "mistral_ocr_table"
    ]
    others = [
        element
        for element in elements
        if _mistral_label(element)
        not in {"mistral_ocr_table", "mistral_ocr_table_row", "mistral_ocr_table_cell"}
    ]

    candidates_by_ref: dict[str, EvidenceCandidate] = {}
    for element in [*rows, *cells, *others]:
        candidate = _candidate_from_mistral_pdf_element(
            element,
            tokens_by_page,
            row_candidates=candidates_by_ref,
        )
        if candidate is not None:
            candidates_by_ref[candidate.source_ref] = candidate

    for element in tables:
        source_ref = str(element.get("source_ref") or "")
        if not source_ref or source_ref in candidates_by_ref:
            continue
        child_candidates = [
            candidate
            for candidate in candidates_by_ref.values()
            if candidate.source_ref.startswith(f"{source_ref}/")
        ]
        union = _union_candidate_bbox(child_candidates)
        if union is None:
            continue
        candidates_by_ref[source_ref] = _mistral_element_candidate(
            element,
            union,
            text_override=str(element.get("text") or ""),
        )

    return list(candidates_by_ref.values())


# This parser intentionally uses guard clauses for untrusted OCR element data.
def _candidate_from_mistral_pdf_element(  # noqa: PLR0911
    element: object,
    tokens_by_page: dict[int, list[PdfToken]],
    *,
    row_candidates: dict[str, EvidenceCandidate],
) -> EvidenceCandidate | None:
    if not isinstance(element, dict):
        return None
    page_no = _int_or_none(element.get("page_no"))
    source_ref = str(element.get("source_ref") or "")
    if page_no is None or not source_ref:
        return None
    page_tokens = tokens_by_page.get(page_no, [])
    if not page_tokens:
        return None
    text = str(element.get("text") or "").strip()
    text_tokens = _normalized_tokens(text)
    if not text_tokens:
        return None
    estimate = (
        _raw_bbox(element.get("bbox"))
        if isinstance(element.get("bbox"), dict)
        else None
    )
    within: RawBBox | None = None
    parent_ref = str(element.get("parent_ref") or "")
    if _mistral_label(element) == "mistral_ocr_table_cell" and parent_ref:
        parent_candidate = row_candidates.get(parent_ref)
        within = parent_candidate.raw_bbox if parent_candidate is not None else None
    match = _best_pdf_token_match(
        page_tokens,
        text_tokens,
        estimate=estimate,
        within=within,
    )
    if match is None:
        return None
    return _mistral_element_candidate(element, match.bbox, text_override=text)


def _mistral_element_candidate(
    element: dict[str, Any],
    bbox: RawBBox,
    *,
    text_override: str,
) -> EvidenceCandidate:
    page_no = _int_or_none(element.get("page_no")) or 1
    text = text_override.strip()
    context_text = str(element.get("context_text") or text).strip()
    return EvidenceCandidate(
        source_ref=str(element.get("source_ref") or ""),
        parent_ref=str(element.get("parent_ref"))
        if element.get("parent_ref")
        else None,
        label=str(element.get("label") or "mistral_ocr_element"),
        text=text,
        context_text=context_text,
        page_no=page_no,
        raw_bbox=bbox,
    )


def _pdf_tokens_by_page(
    pdf_path: Path, pages_by_no: dict[int, PageInfo]
) -> dict[int, list[PdfToken]]:
    try:
        import pdfplumber  # noqa: PLC0415
    except Exception:
        return {}
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    tokens_by_page: dict[int, list[PdfToken]] = {}
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                page_info = pages_by_no.get(index)
                if page_info is None:
                    continue
                page_width = _float_or_none(getattr(page, "width", None))
                page_height = _float_or_none(getattr(page, "height", None))
                if not page_width or not page_height:
                    continue
                scale_x = page_info.width / page_width
                scale_y = page_info.height / page_height
                words = page.extract_words(
                    x_tolerance=2,
                    y_tolerance=3,
                    keep_blank_chars=False,
                )
                page_tokens: list[PdfToken] = []
                for word in words:
                    if not isinstance(word, dict):
                        continue
                    raw_text = str(word.get("text") or "")
                    for token in _normalized_tokens(raw_text):
                        x0 = _float_or_none(word.get("x0"))
                        top = _float_or_none(word.get("top"))
                        x1 = _float_or_none(word.get("x1"))
                        bottom = _float_or_none(word.get("bottom"))
                        if x0 is None or top is None or x1 is None or bottom is None:
                            continue
                        page_tokens.append(
                            PdfToken(
                                text=token,
                                page_no=index,
                                left=x0 * scale_x,
                                top=top * scale_y,
                                right=x1 * scale_x,
                                bottom=bottom * scale_y,
                            )
                        )
                if page_tokens:
                    tokens_by_page[index] = page_tokens
    except Exception:
        return {}
    return tokens_by_page


def _best_pdf_token_match(
    page_tokens: list[PdfToken],
    target_tokens: list[str],
    *,
    estimate: RawBBox | None,
    within: RawBBox | None,
) -> BBoxMatch | None:
    if within is not None:
        page_tokens = [
            token
            for token in page_tokens
            if _vertical_overlap(token, within, tolerance=8.0)
        ]
    match: BBoxMatch | None = None
    if page_tokens and target_tokens:
        candidates = _pdf_token_matches(page_tokens, target_tokens)
        if candidates:
            if estimate is None:
                match = max(candidates, key=lambda item: item.score)
            else:
                match = min(
                    candidates,
                    key=lambda item: (
                        -item.score,
                        _bbox_center_distance(item.bbox, estimate),
                        item.bbox.top,
                        item.bbox.left,
                    ),
                )
    return match


def _pdf_token_matches(
    page_tokens: list[PdfToken], target_tokens: list[str]
) -> list[BBoxMatch]:
    target_len = len(target_tokens)
    if target_len == 0:
        return []
    window_lengths = sorted(
        {target_len, max(1, target_len - 1), target_len + 1, target_len + 2}
    )
    matches: list[BBoxMatch] = []
    for window_len in window_lengths:
        if window_len > len(page_tokens):
            continue
        for start in range(0, len(page_tokens) - window_len + 1):
            window = page_tokens[start : start + window_len]
            window_text = [token.text for token in window]
            score = _ordered_token_score(target_tokens, window_text)
            minimum_score = 1.0 if target_len <= SHORT_PDF_TOKEN_TARGET_LENGTH else 0.72
            if score < minimum_score:
                continue
            bbox = _union_tokens(window)
            if bbox is not None:
                matches.append(BBoxMatch(bbox=bbox, score=score))
    return matches


def _ordered_token_score(target_tokens: list[str], window_tokens: list[str]) -> float:
    if not target_tokens or not window_tokens:
        return 0.0
    matched = _lcs_length(target_tokens, window_tokens)
    ordered_score = matched / len(target_tokens)
    position_penalty = abs(len(window_tokens) - len(target_tokens)) / max(
        len(target_tokens), 1
    )
    return max(0.0, ordered_score - (position_penalty * 0.12))


def _lcs_length(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for left_token in left:
        current = [0]
        for right_index, right_token in enumerate(right, start=1):
            if left_token == right_token:
                current.append(previous[right_index - 1] + 1)
            else:
                current.append(max(previous[right_index], current[-1]))
        previous = current
    return previous[-1]


def _union_tokens(tokens: list[PdfToken]) -> RawBBox | None:
    if not tokens:
        return None
    return RawBBox(
        left=min(token.left for token in tokens),
        top=min(token.top for token in tokens),
        right=max(token.right for token in tokens),
        bottom=max(token.bottom for token in tokens),
        coord_origin="TOPLEFT",
    )


def _union_candidate_bbox(candidates: list[EvidenceCandidate]) -> RawBBox | None:
    if not candidates:
        return None
    return RawBBox(
        left=min(candidate.raw_bbox.left for candidate in candidates),
        top=min(candidate.raw_bbox.top for candidate in candidates),
        right=max(candidate.raw_bbox.right for candidate in candidates),
        bottom=max(candidate.raw_bbox.bottom for candidate in candidates),
        coord_origin="TOPLEFT",
    )


def _vertical_overlap(token: PdfToken, bbox: RawBBox, *, tolerance: float) -> bool:
    top = min(bbox.top, bbox.bottom) - tolerance
    bottom = max(bbox.top, bbox.bottom) + tolerance
    return token.bottom >= top and token.top <= bottom


def _bbox_center_distance(left: RawBBox, right: RawBBox) -> float:
    left_x = (left.left + left.right) / 2
    left_y = (left.top + left.bottom) / 2
    right_x = (right.left + right.right) / 2
    right_y = (right.top + right.bottom) / 2
    return ((left_x - right_x) ** 2 + (left_y - right_y) ** 2) ** 0.5


def _mistral_label(element: object) -> str:
    return str(element.get("label") or "") if isinstance(element, dict) else ""


def _normalized_tokens(text: str) -> list[str]:
    return [
        token.strip("._").casefold()
        for token in re.findall(r"[$€£₱]|[A-Za-z0-9]+(?:[./:_-][A-Za-z0-9]+)*", text)
        if token.strip("._")
    ]


def _candidate_text(item: dict[str, object]) -> str:
    for key in ("text", "orig"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _table_text(table: dict[str, object]) -> str:
    data = table.get("data")
    if not isinstance(data, dict):
        return ""
    cells = data.get("table_cells")
    if not isinstance(cells, list):
        return ""
    return " ".join(_candidate_text(cell) for cell in cells if isinstance(cell, dict))


def _first_page_no(provs: object) -> int | None:
    if not isinstance(provs, list):
        return None
    for prov in provs:
        if not isinstance(prov, dict):
            continue
        page_no = _int_or_none(prov.get("page_no"))
        if page_no is not None:
            return page_no
    return None


def _first_bbox(provs: object) -> RawBBox | None:
    if not isinstance(provs, list):
        return None
    for prov in provs:
        if not isinstance(prov, dict):
            continue
        raw_bbox_data = prov.get("bbox")
        if isinstance(raw_bbox_data, dict):
            return _raw_bbox(raw_bbox_data)
    return None


def _raw_bbox(value: dict[str, object]) -> RawBBox | None:
    left = _float_or_none(value.get("left", value.get("l")))
    top = _float_or_none(value.get("top", value.get("t")))
    right = _float_or_none(value.get("right", value.get("r")))
    bottom = _float_or_none(value.get("bottom", value.get("b")))
    if left is None or top is None or right is None or bottom is None:
        return None
    return RawBBox(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        coord_origin=str(value.get("coord_origin") or "BOTTOMLEFT"),
    )


def _normalize_bbox(bbox: RawBBox, page: PageInfo) -> NormalizedBBox:
    source_width = getattr(page, "_source_width", None) or page.width
    source_height = getattr(page, "_source_height", None) or page.height
    orientation = getattr(page, "_image_orientation", None)
    left = min(bbox.left, bbox.right)
    width = abs(bbox.right - bbox.left)
    origin = bbox.coord_origin.upper()
    if origin == "TOPLEFT":
        top = min(bbox.top, bbox.bottom)
        height = abs(bbox.bottom - bbox.top)
    else:
        top = source_height - max(bbox.top, bbox.bottom)
        height = abs(bbox.top - bbox.bottom)

    rect = _orient_bbox_rect(
        BBoxRect(left=left, top=top, width=width, height=height),
        source_width=source_width,
        source_height=source_height,
        orientation=orientation,
    )
    base_width, base_height = _oriented_size(source_width, source_height, orientation)
    rect = _rotate_bbox_rect_clockwise(
        rect,
        source_width=getattr(page, "_image_base_width", None) or base_width,
        source_height=getattr(page, "_image_base_height", None) or base_height,
        degrees=getattr(page, "_image_rotation_degrees", 0),
    )

    return NormalizedBBox(
        left_pct=_pct(rect.left, page.width),
        top_pct=_pct(rect.top, page.height),
        width_pct=_pct(rect.width, page.width),
        height_pct=_pct(rect.height, page.height),
    )


def _orient_bbox_rect(
    rect: BBoxRect,
    *,
    source_width: float,
    source_height: float,
    orientation: int | None,
) -> BBoxRect:
    if orientation is None:
        return rect
    right_offset = source_width - rect.left - rect.width
    bottom_offset = source_height - rect.top - rect.height
    oriented_rects = {
        EXIF_MIRROR_HORIZONTAL: BBoxRect(
            right_offset, rect.top, rect.width, rect.height
        ),
        EXIF_ROTATE_180: BBoxRect(right_offset, bottom_offset, rect.width, rect.height),
        EXIF_MIRROR_VERTICAL: BBoxRect(
            rect.left, bottom_offset, rect.width, rect.height
        ),
        EXIF_TRANSPOSE: BBoxRect(rect.top, rect.left, rect.height, rect.width),
        EXIF_ROTATE_90_CW: BBoxRect(bottom_offset, rect.left, rect.height, rect.width),
        EXIF_TRANSVERSE: BBoxRect(bottom_offset, right_offset, rect.height, rect.width),
        EXIF_ROTATE_90_CCW: BBoxRect(rect.top, right_offset, rect.height, rect.width),
    }
    return oriented_rects.get(orientation, rect)


def _oriented_size(
    source_width: float,
    source_height: float,
    orientation: int | None,
) -> tuple[float, float]:
    return (
        (source_height, source_width)
        if orientation
        in {EXIF_TRANSPOSE, EXIF_ROTATE_90_CW, EXIF_TRANSVERSE, EXIF_ROTATE_90_CCW}
        else (source_width, source_height)
    )


def _rotate_bbox_rect_clockwise(
    rect: BBoxRect,
    *,
    source_width: float,
    source_height: float,
    degrees: int,
) -> BBoxRect:
    normalized = degrees % 360
    right_offset = source_width - rect.left - rect.width
    bottom_offset = source_height - rect.top - rect.height
    rotated_rects = {
        0: rect,
        90: BBoxRect(bottom_offset, rect.left, rect.height, rect.width),
        180: BBoxRect(right_offset, bottom_offset, rect.width, rect.height),
        270: BBoxRect(rect.top, right_offset, rect.height, rect.width),
    }
    return rotated_rects.get(normalized, rect)


def _pct(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, value / total * 100.0))


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    return result


def _float_or_none(value: object) -> float | None:
    result: float | None = None
    if isinstance(value, int | float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            result = None
    return result
