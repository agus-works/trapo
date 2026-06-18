from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from trapo.annotation_settings import annotation_style_lookup, resolve_annotation_style
from trapo.assets import image_page_info
from trapo.db import DuckConnection, table_exists
from trapo.ids import new_uuid7
from trapo.mineru_bbox import display_bbox_from_mineru_metadata, page_metadata
from trapo.server.models import OverlayBox, PageInfo, RawBBox
from trapo.server.provenance import (
    DoclingEvidenceIndex,
    EvidenceCandidate,
    _normalize_bbox,
    build_docling_evidence_index,
    evidence_candidates_from_chunk_metadata,
    extract_pages,
    parse_json_value,
)

REGION_KIND_BY_LABEL_FRAGMENT = (
    ("table_cell", "table_cell"),
    ("table", "table"),
    ("equation", "formula"),
    ("formula", "formula"),
    ("latex", "formula"),
    ("image", "image"),
    ("chart", "chart"),
    ("code", "code"),
    ("list", "list"),
    ("title", "title"),
    ("page_number", "page_number"),
    ("footnote", "footnote"),
    ("header", "header"),
    ("footer", "footer"),
)
ANNOTATION_ENGINE_ROW_INDEX = 6
DISPLAY_SPACE_ENGINES = frozenset({"lmstudio"})
NORMALIZED_PAGE_ENGINES = frozenset({"docling_normalized", "mineru_normalized"})


@dataclass(frozen=True)
class RegionChunkLink:
    chunk_id: int | None
    chunk_index: int | None


def rebuild_document_regions(connection: DuckConnection, file_hash: str) -> int:
    """Persist Docling page regions with bounding boxes for the given file."""
    if not table_exists(connection, "document_regions"):
        return 0
    docling_row = connection.execute(
        "SELECT docling_json FROM docling_documents WHERE file_hash = ? AND status = 'ok'",
        [file_hash],
    ).fetchone()
    if not docling_row:
        return 0
    pdf_path = _latest_file_path(connection, file_hash)
    return rebuild_docling_output_regions(
        connection,
        file_hash,
        docling_row[0],
        annotation_engine="docling",
        annotation_provider="local-docling",
        annotation_model="docling",
        pdf_path=pdf_path,
        metadata_source="docling_document",
        link_chunks=True,
    )


def rebuild_docling_output_regions(  # noqa: PLR0913
    connection: DuckConnection,
    file_hash: str,
    docling_json: object,
    *,
    annotation_engine: str,
    annotation_provider: str,
    annotation_model: str,
    pdf_path: Path | None = None,
    metadata_source: str,
    link_chunks: bool = False,
) -> int:
    if not table_exists(connection, "document_regions"):
        return 0
    _delete_region_engine(connection, file_hash, annotation_engine)
    docling_index = build_docling_evidence_index(docling_json)
    image_page = image_page_info(pdf_path) if pdf_path is not None else None
    if image_page is not None:
        pages_by_no = {image_page.page_no: image_page}
    else:
        pages_by_no = {page.page_no: page for page in extract_pages(docling_json)}

    chunk_candidates = (
        _chunk_candidates(connection, file_hash, docling_index, pdf_path, pages_by_no)
        if link_chunks
        else []
    )
    chunk_links = {
        _candidate_key(candidate): link for candidate, link in chunk_candidates
    }

    candidates = docling_index.all_candidates()
    if not candidates:
        candidates = [candidate for candidate, _link in chunk_candidates]
    else:
        seen = {_candidate_key(candidate) for candidate in candidates}
        candidates.extend(
            candidate
            for candidate, _link in chunk_candidates
            if _candidate_key(candidate) not in seen
        )

    inserted = 0
    for candidate in candidates:
        if candidate.page_no not in pages_by_no:
            continue
        key = _candidate_key(candidate)
        link = chunk_links.get(key, RegionChunkLink(chunk_id=None, chunk_index=None))
        region_id = _region_id(file_hash, annotation_engine, candidate)
        page = pages_by_no[candidate.page_no]
        connection.execute(
            """
            INSERT INTO document_regions
                (
                    region_id, file_hash, annotation_engine, annotation_provider,
                    annotation_model, chunk_id, chunk_index, page_no, source_ref,
                    parent_ref, label, text, context_text, raw_bbox_json,
                    region_kind, metadata_json
                )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?::JSON, ?, ?::JSON
            )
            ON CONFLICT (region_id) DO UPDATE SET
                chunk_id = excluded.chunk_id,
                chunk_index = excluded.chunk_index,
                annotation_engine = excluded.annotation_engine,
                annotation_provider = excluded.annotation_provider,
                annotation_model = excluded.annotation_model,
                page_no = excluded.page_no,
                source_ref = excluded.source_ref,
                parent_ref = excluded.parent_ref,
                label = excluded.label,
                text = excluded.text,
                context_text = excluded.context_text,
                raw_bbox_json = excluded.raw_bbox_json,
                region_kind = excluded.region_kind,
                metadata_json = excluded.metadata_json,
                updated_at = now()
            """,
            [
                region_id,
                file_hash,
                annotation_engine,
                annotation_provider,
                annotation_model,
                link.chunk_id,
                link.chunk_index,
                candidate.page_no,
                candidate.source_ref,
                candidate.parent_ref,
                candidate.label,
                candidate.text,
                candidate.context_text,
                json.dumps(candidate.raw_bbox.model_dump()),
                _region_kind(candidate),
                json.dumps(
                    {
                        "source": metadata_source,
                        "target_page": page_metadata(page),
                    }
                ),
            ],
        )
        inserted += 1
    rebuild_document_terms(connection, file_hash)
    return inserted


def rebuild_document_terms(connection: DuckConnection, file_hash: str) -> int:
    """Persist region-level word terms with bounding boxes for word search."""
    if not _document_terms_table_exists(connection) or not table_exists(
        connection, "document_regions"
    ):
        return 0
    connection.execute("DELETE FROM document_terms WHERE file_hash = ?", [file_hash])
    rows = connection.execute(
        """
        SELECT
            region_id, chunk_id, page_no, text, raw_bbox_json, region_kind,
            coalesce(annotation_engine, 'docling') AS annotation_engine
        FROM document_regions
        WHERE file_hash = ?
        ORDER BY page_no, region_id
        """,
        [file_hash],
    ).fetchall()
    inserted = 0
    for row in rows:
        region_id = str(row[0])
        chunk_id = int(row[1]) if row[1] is not None else None
        page_no = int(row[2]) if row[2] is not None else None
        text = str(row[3] or "")
        bbox = parse_json_value(row[4])
        if not text.strip() or not isinstance(bbox, dict):
            continue
        for token, start, end in _term_spans(text):
            connection.execute(
                """
                INSERT INTO document_terms (
                    document_term_id, file_hash, page_no, region_id, chunk_id,
                    annotation_engine, text, normalized_text, bbox_json,
                    char_start, char_end, metadata_json
                )
                VALUES (?::UUID, ?, ?, ?, ?, ?, ?, ?, ?::JSON, ?, ?, ?::JSON)
                """,
                [
                    str(new_uuid7()),
                    file_hash,
                    page_no,
                    region_id,
                    chunk_id,
                    str(row[ANNOTATION_ENGINE_ROW_INDEX])
                    if row[ANNOTATION_ENGINE_ROW_INDEX] is not None
                    else "docling",
                    token,
                    token.casefold(),
                    json.dumps(bbox),
                    start,
                    end,
                    json.dumps(
                        {
                            "bbox_granularity": "region",
                            "region_kind": str(row[5]) if row[5] is not None else None,
                        }
                    ),
                ],
            )
            inserted += 1
    return inserted


def persisted_region_overlays(
    connection: DuckConnection,
    file_hash: str,
    pages_by_no: dict[int, PageInfo],
) -> list[OverlayBox]:
    if not table_exists(connection, "document_regions"):
        return []
    rows = connection.execute(
        """
        SELECT
            r.region_id, r.chunk_id, r.chunk_index, r.page_no, r.source_ref, r.label,
            r.text, r.context_text, r.raw_bbox_json,
            coalesce(r.annotation_engine, 'docling') AS annotation_engine,
            coalesce(r.annotation_provider, 'local-docling') AS annotation_provider,
            coalesce(r.annotation_model, 'docling') AS annotation_model,
            coalesce(r.region_kind, 'text') AS region_kind,
            coalesce(v.hidden, false) AS hidden,
            r.metadata_json
        FROM document_regions r
        LEFT JOIN annotation_visibility_overrides v
            ON v.file_hash = r.file_hash
           AND v.overlay_id = concat('region:', r.region_id)
        WHERE r.file_hash = ?
        ORDER BY r.page_no, annotation_engine, r.chunk_index NULLS LAST, r.source_ref, r.region_id
        """,
        [file_hash],
    ).fetchall()
    if not rows:
        return []
    overlays: list[OverlayBox] = []
    styles = annotation_style_lookup(connection)
    for row in rows:
        page_no = int(row[3])
        page = pages_by_no.get(page_no)
        if page is None:
            continue
        raw_bbox = _raw_bbox_from_json(row[8])
        if raw_bbox is None:
            continue
        region_id = str(row[0])
        annotation_engine = str(row[9])
        annotation_provider = str(row[10])
        annotation_model = str(row[11])
        region_kind = str(row[12])
        normalization_page = page
        metadata = parse_json_value(row[14])
        if annotation_engine == "mineru":
            repaired_page = _mineru_repair_page(page)
            raw_bbox = display_bbox_from_mineru_metadata(
                raw_bbox, metadata, repaired_page
            )
            normalization_page = _mineru_normalization_page(page, repaired_page)
        elif annotation_engine in NORMALIZED_PAGE_ENGINES:
            normalization_page = _metadata_page(metadata, fallback=page)
        elif _is_display_space_engine(annotation_engine):
            normalization_page = PageInfo(
                page_no=page.page_no, width=page.width, height=page.height
            )
        overlays.append(
            OverlayBox(
                overlay_id=f"region:{region_id}",
                file_hash=file_hash,
                annotation_engine=annotation_engine,
                annotation_provider=annotation_provider,
                annotation_model=annotation_model,
                chunk_id=int(row[1]) if row[1] is not None else 0,
                chunk_index=int(row[2]) if row[2] is not None else -1,
                page_no=page_no,
                raw_bbox=raw_bbox,
                bbox=_normalize_bbox(raw_bbox, normalization_page),
                source_ref=str(row[4]) if row[4] is not None else None,
                label=str(row[5]) if row[5] is not None else None,
                region_kind=region_kind,
                text_preview=str(row[6] or row[7] or "")[:260],
                hidden=bool(row[13]),
                style=resolve_annotation_style(
                    styles,
                    annotation_engine=annotation_engine,
                    region_kind=region_kind,
                    label=str(row[5]) if row[5] is not None else None,
                ),
            )
        )
    return overlays


def _mineru_repair_page(page: PageInfo) -> PageInfo:
    return PageInfo(
        page_no=page.page_no,
        width=getattr(page, "_image_base_width", None) or page.width,
        height=getattr(page, "_image_base_height", None) or page.height,
    )


def _mineru_normalization_page(page: PageInfo, repaired_page: PageInfo) -> PageInfo:
    normalization_page = PageInfo(
        page_no=page.page_no, width=page.width, height=page.height
    )
    normalization_page._source_width = repaired_page.width
    normalization_page._source_height = repaired_page.height
    normalization_page._image_base_width = repaired_page.width
    normalization_page._image_base_height = repaired_page.height
    normalization_page._image_rotation_degrees = getattr(
        page, "_image_rotation_degrees", 0
    )
    return normalization_page


def _metadata_page(metadata: dict[str, object], *, fallback: PageInfo) -> PageInfo:
    target_page = metadata.get("target_page")
    if not isinstance(target_page, dict):
        return fallback
    width = _float_or_none(target_page.get("width"))
    height = _float_or_none(target_page.get("height"))
    page_no = _int_or_none(target_page.get("page_no")) or fallback.page_no
    if width is None or height is None or width <= 0 or height <= 0:
        return fallback
    return PageInfo(page_no=page_no, width=width, height=height)


def _is_display_space_engine(annotation_engine: str) -> bool:
    return annotation_engine in DISPLAY_SPACE_ENGINES or annotation_engine.startswith(
        "fusion"
    )


def _delete_region_engine(
    connection: DuckConnection, file_hash: str, annotation_engine: str
) -> None:
    if _document_terms_table_exists(connection):
        connection.execute(
            "DELETE FROM document_terms WHERE file_hash = ? AND annotation_engine = ?",
            [file_hash, annotation_engine],
        )
    connection.execute(
        "DELETE FROM document_regions WHERE file_hash = ? AND annotation_engine = ?",
        [file_hash, annotation_engine],
    )


def _document_terms_table_exists(connection: DuckConnection) -> bool:
    return table_exists(connection, "document_terms")


def _term_spans(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0), match.start(), match.end())
        for match in re.finditer(r"[\w]+(?:[.'_-][\w]+)*", text, flags=re.UNICODE)
    ]


def _chunk_candidates(
    connection: DuckConnection,
    file_hash: str,
    docling_index: DoclingEvidenceIndex,
    pdf_path: Path | None,
    pages_by_no: dict[int, PageInfo],
) -> list[tuple[EvidenceCandidate, RegionChunkLink]]:
    rows = connection.execute(
        """
        SELECT chunk_id, chunk_index, text, metadata_json
        FROM document_chunks
        WHERE file_hash = ?
        ORDER BY chunk_index
        """,
        [file_hash],
    ).fetchall()
    candidates: list[tuple[EvidenceCandidate, RegionChunkLink]] = []
    for row in rows:
        chunk_id = int(row[0])
        chunk_index = int(row[1])
        for candidate in evidence_candidates_from_chunk_metadata(
            chunk_text=str(row[2]),
            metadata_json=row[3],
            docling_index=docling_index,
            pdf_path=pdf_path,
            pages_by_no=pages_by_no,
        ):
            candidates.append(
                (
                    candidate,
                    RegionChunkLink(chunk_id=chunk_id, chunk_index=chunk_index),
                )
            )
    return candidates


def _latest_file_path(connection: DuckConnection, file_hash: str) -> Path | None:
    row = connection.execute(
        """
        SELECT path
        FROM file_locations
        WHERE file_hash = ?
        ORDER BY last_seen_at DESC
        LIMIT 1
        """,
        [file_hash],
    ).fetchone()
    if not row or row[0] is None:
        return None
    path = Path(str(row[0]))
    return path if path.exists() else None


def _candidate_key(
    candidate: EvidenceCandidate,
) -> tuple[str, int, float, float, float, float]:
    return (
        candidate.source_ref,
        candidate.page_no,
        round(candidate.raw_bbox.left, 3),
        round(candidate.raw_bbox.top, 3),
        round(candidate.raw_bbox.right, 3),
        round(candidate.raw_bbox.bottom, 3),
    )


def _region_id(
    file_hash: str, annotation_engine: str, candidate: EvidenceCandidate
) -> str:
    key = "|".join(
        str(part) for part in (file_hash, annotation_engine, *_candidate_key(candidate))
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _region_kind(candidate: EvidenceCandidate) -> str:
    label = (candidate.label or "").strip().lower()
    for fragment, region_kind in REGION_KIND_BY_LABEL_FRAGMENT:
        if fragment in label:
            return region_kind
    return "text"


def _raw_bbox_from_json(value: object) -> RawBBox | None:
    data = parse_json_value(value)
    if not data:
        return None
    try:
        return RawBBox.model_validate(data)
    except Exception:
        return None


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value.strip())
        except ValueError:
            result = None
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
